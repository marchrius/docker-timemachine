#!/usr/bin/env python3
"""Offline synthetic Samba upgrade/rollback lab, one explicit phase at a time."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
DOCKER = ["docker", "--context", "colima"]


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


class Lab:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        info = self.directory.stat()
        if (self.directory.parent != Path("/private/tmp")
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise RuntimeError("Use the private directory created by prepare")
        self.manifest = json.loads((self.directory / "manifest.json").read_text())
        self.project = self.manifest["project"]
        if not re.fullmatch(r"tm-state-lab-[0-9a-f]{12}", self.project):
            raise RuntimeError("Invalid synthetic project")
        self.compose = DOCKER + ["compose", "-p", self.project,
                                 "-f", str(ROOT / "lab/compose.state.yaml")]

    def container(self, service):
        if service not in ("reference", "candidate"):
            raise RuntimeError("Invalid lab service")
        return f"{self.project}-{service}-1"

    def quiet(self):
        for service in ("reference", "candidate"):
            result = subprocess.run(DOCKER + ["inspect", self.container(service)],
                                    capture_output=True, text=True)
            if result.returncode:
                # Distinguish an absent container from a broken daemon.
                run(DOCKER + ["info", "--format", "{{.ServerVersion}}"],
                    stdout=subprocess.DEVNULL)
                if "no such" in result.stderr.casefold():
                    continue
                raise RuntimeError(result.stderr)
            item = json.loads(result.stdout)[0]
            if item["Config"]["Labels"].get("com.docker.compose.project") != self.project:
                raise RuntimeError("Container does not belong to this lab")
            if item["State"]["Running"]:
                raise RuntimeError(f"Stop the lab server before proceeding: {service}")

    def execute(self, service, *command, **kwargs):
        return run(self.compose + ["exec", "-T", service, *command], **kwargs)

    def export_state(self, service, filename):
        self.quiet()  # Mandatory: no Samba process may write during export.
        with (self.directory / filename).open("xb") as stream:
            run(DOCKER + ["cp", "-a", self.container(service) + ":/var/lib/samba", "-"],
                stdout=stream)

    def fixture(self, service):
        run(DOCKER + ["cp", str(self.directory / "fixture.tar"),
                      self.container(service) + ":/lab/state-fixture.tar"])

    def identity(self, service):
        return self.execute(service, "sh", "/lab/state-probe.sh", "identity",
                            capture_output=True).stdout

    def verify(self, service):
        self.execute(service, "sh", "/lab/smoke.sh")
        self.execute(service, "sh", "/lab/state-probe.sh", "verify")
        expected = (self.directory / "identity.txt").read_bytes()
        if self.identity(service) != expected:
            raise RuntimeError("SID, account SID, UID/GID, mode or ACL changed")
        print("PASS: server/account SIDs, UID/GID, mode and POSIX ACL preserved", flush=True)

    def stage(self, required):
        if self.manifest["stage"] != required:
            raise RuntimeError(f"Expected stage {required}; found {self.manifest['stage']}")
        self.quiet()

    def finish(self, stage):
        self.manifest["stage"] = stage
        (self.directory / "manifest.json").write_text(json.dumps(self.manifest, indent=2) + "\n")
        print(f"PASS: {stage}; both lab servers stopped; artifacts: {self.directory}", flush=True)

    def baseline(self):
        self.stage("prepared")
        try:
            run(self.compose + ["up", "-d", "reference"])
            self.execute("reference", "sh", "/lab/smoke.sh")
            self.execute("reference", "sh", "/lab/state-probe.sh", "seed")
            self.execute("reference", "sh", "/lab/state-probe.sh", "verify")
            # Only generated lab credentials; never production /users.
            with (self.directory / "fixture.tar").open("xb") as stream:
                self.execute("reference", "tar", "-C", "/run/lab", "-cf", "-",
                             "users", "anna.auth", "matteo.auth", stdout=stream)
            self.fixture("reference")
            (self.directory / "identity.txt").write_bytes(self.identity("reference"))
        finally:
            run(self.compose + ["stop", "reference"])
        self.export_state("reference", "original-state.tar")
        self.finish("baseline")

    def upgrade(self):
        self.stage("baseline")
        run(self.compose + ["create", "candidate"])
        with (self.directory / "original-state.tar").open("rb") as stream:
            run(DOCKER + ["cp", "-a", "-", self.container("candidate") + ":/var/lib"],
                stdin=stream)
        self.export_state("candidate", "imported-state.tar")
        compare_archives(self.directory / "original-state.tar", self.directory / "imported-state.tar")
        print("PASS: offline import preserves state file content, ownership and mode", flush=True)
        self.fixture("candidate")
        try:
            self.quiet()
            run(self.compose + ["start", "candidate"])
            self.execute("candidate", "sh", "/lab/verify-runtime.sh")
            self.verify("candidate")
            self.execute("candidate", "sh", "/lab/state-probe.sh", "write-upgraded")
            self.execute("candidate", "sh", "/lab/state-probe.sh", "verify-upgraded")
        finally:
            run(self.compose + ["stop", "candidate"])
        self.export_state("reference", "original-state-after-upgrade.tar")
        compare_archives(self.directory / "original-state.tar",
                         self.directory / "original-state-after-upgrade.tar")
        print("PASS: original 4.23.8 database files remain unchanged", flush=True)
        self.finish("upgraded")

    def rollback(self):
        self.stage("upgraded")
        try:
            run(self.compose + ["start", "reference"])
            self.verify("reference")
            self.execute("reference", "sh", "/lab/state-probe.sh", "verify-upgraded")
        finally:
            run(self.compose + ["stop", "reference"])
        self.finish("rollback")


def archive_content(path):
    result = {}
    with tarfile.open(path) as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not name.parts or name.parts[0] != "samba":
                raise RuntimeError("Unexpected state archive member")
            payload = archive.extractfile(member).read() if member.isfile() else None
            # Compare internally; never print password hashes or database data.
            result[str(name)] = (member.type, member.uid, member.gid, member.mode,
                                 member.linkname, payload)
    if "samba/private/passdb.tdb" not in result or "samba/private/secrets.tdb" not in result:
        raise RuntimeError("State archive missing passdb/secrets")
    return result


def compare_archives(first, second):
    if archive_content(first) != archive_content(second):
        raise RuntimeError("State archive content, ownership or mode differs")


def prepare():
    for image in ("reference-4.23.8", "candidate-4.23.13"):
        result = run(DOCKER + ["image", "inspect", "--format", "{{.Os}}/{{.Architecture}}",
                              "timemachine-samba-lab:" + image], capture_output=True, text=True)
        if result.stdout.strip() != "linux/arm64":
            raise RuntimeError("The existing local ARM64 lab images are required")
    directory = Path(tempfile.mkdtemp(prefix="timemachine-state-lab-", dir="/private/tmp"))
    (directory / "manifest.json").write_text(json.dumps({
        "project": "tm-state-lab-" + uuid.uuid4().hex[:12], "stage": "prepared",
    }, indent=2) + "\n")
    lab = Lab(directory)
    run(lab.compose + ["config", "--quiet"])
    print(f"Mac / Colima lab prepared. Private synthetic artifacts: {directory}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "baseline", "upgrade", "rollback"))
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
        lab = Lab(args.directory)
        getattr(lab, args.phase)()


if __name__ == "__main__":
    main()
