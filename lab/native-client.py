#!/usr/bin/env python3
"""Native macOS SMB client qualification against a loopback-only synthetic lab."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile
from urllib.parse import quote
import uuid

ROOT = Path(__file__).resolve().parents[1]
DOCKER = ["docker", "--context", "colima"]
IMAGE = "timemachine-samba-lab:candidate-4.23.13"
FINDER_INFO = b"TEXTttxt" + bytes(24)
RESOURCE_FORK = b"Synthetic SMB resource fork.\n" * 64
XATTR_NAME = "com.example.timemachine_lab"
XATTR_DATA = b"synthetic-macOS-attribute"


class Lab:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        info = self.directory.stat()
        if (self.directory.parent != Path("/private/tmp") or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise RuntimeError("Use the private directory printed by prepare")
        self.manifest = json.loads((self.directory / "manifest.json").read_text())
        self.project = self.manifest["project"]
        if not re.fullmatch(r"tm-native-lab-[0-9a-f]{12}", self.project):
            raise RuntimeError("Invalid native-client lab project")
        self.compose = DOCKER + ["compose", "-p", self.project,
                                 "-f", str(ROOT / "lab/compose.native.yaml")]
        self.container = self.project + "-candidate-1"
        self.secrets = []

    def redact(self, text):
        if isinstance(text, bytes):
            text = text.decode(errors="replace")
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "<synthetic-password-redacted>")
        return text

    def run(self, command, *, text=True, check=True, timeout=45):
        try:
            result = subprocess.run(command, capture_output=True, text=text, timeout=timeout)
        except subprocess.TimeoutExpired:
            # Never stringify a mount command: it can contain a fake password.
            raise RuntimeError("Lab command timed out; inspect the local lab before retrying") from None
        if check and result.returncode:
            raise RuntimeError(self.redact(result.stderr or result.stdout))
        return result

    def execute(self, *command, **kwargs):
        return self.run(self.compose + ["exec", "-T", "candidate", *command], **kwargs)

    def save(self, stage):
        self.manifest["stage"] = stage
        (self.directory / "manifest.json").write_text(json.dumps(self.manifest, indent=2) + "\n")
        print(f"PASS: {stage}; artifacts: {self.directory}", flush=True)

    def require(self, stage):
        if self.manifest["stage"] != stage:
            raise RuntimeError(f"Expected stage {stage}; found {self.manifest['stage']}")

    def inspect(self, service="candidate"):
        if service not in ("candidate", "proxy"):
            raise RuntimeError("Invalid lab service")
        name = self.project + "-" + service + "-1"
        item = json.loads(self.run(DOCKER + ["inspect", name]).stdout)[0]
        if item["Config"]["Labels"].get("com.docker.compose.project") != self.project:
            raise RuntimeError("Container does not belong to this synthetic lab")
        image = self.manifest["image" if service == "candidate" else "proxy_image"]
        if item["Image"] != image:
            raise RuntimeError("Candidate image changed after prepare")
        return item

    def start(self):
        self.require("prepared")
        try:
            result = self.run(self.compose + ["up", "-d", "candidate", "proxy"])
            print(self.redact(result.stderr), end="", flush=True)
            item = self.inspect()
            if item["NetworkSettings"]["Ports"]:
                raise RuntimeError("The Samba container must not publish ports directly")
            if set(item["NetworkSettings"]["Networks"]) != {self.project + "_isolated"}:
                raise RuntimeError("Samba must remain exclusively on its internal network")
            proxy = self.inspect("proxy")
            if proxy["Mounts"]:
                raise RuntimeError("The TCP proxy must not mount any data or credentials")
            ports = proxy["NetworkSettings"]["Ports"]
            bindings = ports.get("1445/tcp") or []
            if (set(ports) != {"1445/tcp"} or len(bindings) != 1
                    or bindings[0]["HostIp"] != "127.0.0.1"):
                raise RuntimeError("SMB must be published exclusively on 127.0.0.1")
            network = json.loads(self.run(DOCKER + ["network", "inspect",
                                                    self.project + "_isolated"]).stdout)[0]
            if network["Driver"] != "bridge" or not network["Internal"]:
                raise RuntimeError("The candidate network must be an internal bridge")
            self.manifest["port"] = int(bindings[0]["HostPort"])
            print(self.execute("sh", "/lab/smoke.sh").stdout, end="", flush=True)
            with socket.create_connection(("127.0.0.1", self.manifest["port"]), timeout=10):
                pass
        except Exception:
            self.run(self.compose + ["stop", "proxy", "candidate"], check=False)
            raise
        print(f"Mac loopback endpoint verified: 127.0.0.1:{self.manifest['port']}", flush=True)
        self.save("started")

    def mounted(self, path):
        # Read the mount table without stat'ing a potentially unreachable share.
        return f" on {path} (" in self.run(["/sbin/mount"]).stdout

    def unmount(self, path):
        if self.mounted(path):
            self.run(["/sbin/umount", str(path)])

    def mount_share(self, username, password, share, path, *, denied=False):
        path.mkdir(exist_ok=True)
        port = int(self.manifest["port"])
        if not 1 <= port <= 65535:
            raise RuntimeError("Invalid loopback port")
        url = (f"//{quote(username, safe='')}:{quote(password, safe='')}"
               f"@127.0.0.1:{port}/{quote(share, safe='')}")
        self.secrets.extend([password, quote(password, safe="")])
        marker = None
        before_denials = 0
        if denied:
            actor = "guest user" if username == "guest" else f"user '{username}'"
            marker = f"{actor} (from session setup) not permitted to access this share ({share})"
            before_denials = self.denial_count(marker)
        result = self.run(["/sbin/mount", "-t", "smbfs", "-o",
                           "nobrowse,soft,nopassprompt,forcenewsession", url, str(path)], check=False)
        if denied:
            if result.returncode == 0 or self.mounted(path):
                raise RuntimeError("Unauthorized synthetic share mount unexpectedly succeeded")
            error = self.redact(result.stderr + result.stdout)
            after_denials = self.denial_count(marker)
            explicit_client_denial = bool(re.search(
                r"permission denied|authentication|access denied|logon", error, re.I))
            explicit_server_denial = after_denials > before_denials
            if not explicit_client_denial and not explicit_server_denial:
                raise RuntimeError("Negative authentication test returned an unrelated error: " + error)
            report = self.directory / ("denied-" + username + ".json")
            report.write_text(json.dumps({
                "synthetic_user": username, "share": share, "client_error": error,
                "explicit_client_denial": explicit_client_denial,
                "new_explicit_server_denial": explicit_server_denial,
            }, indent=2) + "\n")
            return
        if result.returncode:
            raise RuntimeError("Native SMB mount failed: " + self.redact(result.stderr + result.stdout))
        if not self.mounted(path):
            raise RuntimeError("Native SMB mount did not appear in mount table")

    def denial_count(self, marker):
        result = self.run(DOCKER + ["logs", self.container])
        return (result.stdout + result.stderr).count(marker)

    def credentials(self):
        auth = self.execute("cat", "/run/lab/matteo.auth").stdout
        fields = dict(line.split("=", 1) for line in auth.splitlines() if "=" in line)
        fields = {key.strip(): value.strip() for key, value in fields.items()}
        if fields.get("username") != "matteo" or not re.fullmatch(r"[0-9a-f]{64}", fields.get("password", "")):
            raise RuntimeError("Expected generated synthetic credentials")
        self.secrets.append(fields["password"])
        return fields["username"], fields["password"]

    def verify_file(self, path, payload):
        if path.read_bytes() != payload:
            raise RuntimeError("Native SMB data differs")
        if self.get_xattr(path, XATTR_NAME) != XATTR_DATA:
            raise RuntimeError("Native macOS extended attribute differs")
        observed_finder = self.get_xattr(path, "com.apple.FinderInfo")
        # AAPL directory enumeration synthesizes Finder date-added from btime.
        # macOS may return this view instead of the raw AFP_AfpInfo bytes.
        # Accept only that specific field, with the exact expected timestamp;
        # independently require the on-disk 32-byte FinderInfo to be unchanged.
        birth_seconds = int(path.stat().st_birthtime) - 946684800
        date_view = FINDER_INFO[:24] + birth_seconds.to_bytes(4, "big") + FINDER_INFO[28:]
        if observed_finder not in (FINDER_INFO, date_view):
            (self.directory / "finderinfo-mismatch.json").write_text(json.dumps({
                "file": path.name, "expected_hex": FINDER_INFO.hex(),
                "observed_hex": observed_finder.hex(), "aapl_date_view_hex": date_view.hex(),
            }, indent=2) + "\n")
            raise RuntimeError("FinderInfo differs")
        backend_info = self.execute(
            "getfattr", "--only-values", "-n", "user.DosStream.AFP_AfpInfo:$DATA",
            "/opt/matteo/" + path.name, text=False,
        ).stdout
        if len(backend_info) < 48 or backend_info[16:48] != FINDER_INFO:
            raise RuntimeError("Stored FinderInfo bytes differ")
        if (path / "..namedfork" / "rsrc").read_bytes() != RESOURCE_FORK:
            raise RuntimeError("Resource fork differs")

    def get_xattr(self, path, name):
        return bytes.fromhex(self.run(["/usr/bin/xattr", "-px", name, str(path)]).stdout)

    def set_xattr(self, path, name, value):
        self.run(["/usr/bin/xattr", "-wx", name, value.hex(), str(path)])

    def probe(self):
        self.require("started")
        if not self.inspect()["State"]["Running"]:
            raise RuntimeError("Start the isolated candidate first")
        username, password = self.credentials()
        share = self.directory / "share"
        denied = self.directory / "denied"
        guest = self.directory / "guest"
        if any(self.mounted(path) for path in (share, denied, guest)):
            raise RuntimeError("A previous test mount remains; unmount it before retrying")
        payload = os.urandom(1048576)
        basename = "native-" + uuid.uuid4().hex[:12]
        (self.directory / "payload.bin").write_bytes(payload)
        try:
            self.mount_share(username, password, "Time Machine di Matteo", share)
            info = self.run(["/usr/bin/smbutil", "statshares", "-m", str(share)]).stdout
            (self.directory / "statshares.txt").write_text(self.redact(info))
            for line in info.splitlines():
                if re.search(r"SMB_VERSION|SMB_CURR_SIGN_ALGORITHM|OS_X_SERVER|FILE_LEASING_SUPPORTED", line):
                    print(self.redact(line.strip()), flush=True)
            path = share / (basename + ".bin")
            with path.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self.set_xattr(path, XATTR_NAME, XATTR_DATA)
            self.set_xattr(path, "com.apple.FinderInfo", FINDER_INFO)
            before_fork = self.get_xattr(path, "com.apple.FinderInfo")
            (path / "..namedfork" / "rsrc").write_bytes(RESOURCE_FORK)
            after_fork = self.get_xattr(path, "com.apple.FinderInfo")
            (self.directory / "finderinfo-sequence.json").write_text(json.dumps({
                "expected_hex": FINDER_INFO.hex(), "before_resource_fork_hex": before_fork.hex(),
                "after_resource_fork_hex": after_fork.hex(),
            }, indent=2) + "\n")
            self.verify_file(path, payload)
            renamed = share / (basename + "-renamed.bin")
            path.rename(renamed)
            self.verify_file(renamed, payload)
            print("PASS: native data, xattr, FinderInfo, resource fork and rename", flush=True)
            self.unmount(share)
            self.mount_share(username, password, "Time Machine di Matteo", share)
            self.verify_file(renamed, payload)
            print("PASS: metadata and data preserved across unmount/new SMB session", flush=True)
            self.mount_share(username, password, "Time Machine di Anna", denied, denied=True)
            self.mount_share("guest", "", "Time Machine di Matteo", guest, denied=True)
            print("PASS: native cross-user and guest mounts denied", flush=True)
            backend = "/opt/matteo/" + renamed.name
            if self.execute("cat", backend, text=False).stdout != payload:
                raise RuntimeError("Backend data differs from native client payload")
            owner = self.execute("stat", "-c", "%u:%g", backend).stdout.strip()
            if owner != "1001:1000":
                raise RuntimeError("Unexpected backend file ownership")
            names = self.execute("getfattr", "-m", "^user\\.DosStream\\.", backend).stdout
            (self.directory / "backend-xattr-names.txt").write_text(names)
            print("PASS: payload verified directly on synthetic backend; owner 1001:1000", flush=True)
            self.manifest["verified_file"] = renamed.name
        finally:
            for path in (guest, denied, share):
                self.unmount(path)
        self.save("probed")

    def stop(self):
        for name in ("share", "denied", "guest"):
            if self.mounted(self.directory / name):
                raise RuntimeError("Unmount the synthetic client share before stopping this lab")
        self.inspect()
        print(self.run(self.compose + ["stop", "proxy", "candidate"]).stderr, end="", flush=True)
        self.save("stopped")


def prepare():
    if sys.platform != "darwin":
        raise RuntimeError("Run this native-client test on the Mac")
    result = subprocess.run(DOCKER + ["image", "inspect", IMAGE],
                            check=True, capture_output=True, text=True)
    image = json.loads(result.stdout)[0]
    if image["Os"] != "linux" or image["Architecture"] != "arm64":
        raise RuntimeError("The local ARM64 candidate image is required")
    result = subprocess.run(DOCKER + ["image", "inspect", "timemachine-samba-lab:loopback-proxy"],
                            check=True, capture_output=True, text=True)
    proxy = json.loads(result.stdout)[0]
    if proxy["Os"] != "linux" or proxy["Architecture"] != "arm64":
        raise RuntimeError("The local ARM64 proxy image is required")
    directory = Path(tempfile.mkdtemp(prefix="timemachine-native-lab-", dir="/private/tmp"))
    (directory / "manifest.json").write_text(json.dumps({
        "project": "tm-native-lab-" + uuid.uuid4().hex[:12],
        "image": image["Id"], "proxy_image": proxy["Id"], "stage": "prepared",
    }, indent=2) + "\n")
    lab = Lab(directory)
    lab.run(lab.compose + ["config", "--quiet"])
    print(f"Mac / Colima native-client lab prepared: {directory}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "start", "probe", "stop"))
    parser.add_argument("--directory")
    args = parser.parse_args()
    os.umask(0o077)
    if args.phase == "prepare":
        if args.directory:
            parser.error("prepare creates its own private directory")
        prepare()
    else:
        if not args.directory:
            parser.error("provide the private directory printed by prepare")
        getattr(Lab(args.directory), args.phase)()


if __name__ == "__main__":
    main()
