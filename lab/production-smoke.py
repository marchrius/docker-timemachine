#!/usr/bin/env python3
"""Exercise the production default entrypoint using private synthetic fixtures."""
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "timemachine-samba:trial-4.23.13"


def docker(*args, **kwargs):
    result = subprocess.run(
        ["docker", "--context", "colima", *args],
        text=True, capture_output=True, **kwargs,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout


def main():
    info = json.loads(docker("image", "inspect", IMAGE))[0]
    assert info["Config"]["Entrypoint"] == ["/entrypoint.sh"]
    assert info["Architecture"] == "arm64"
    image = info["Id"]
    docker("run", "--rm", "--network", "none", "--entrypoint", "sh", image,
           "-ec", "test ! -e /lab; test ! -d /users; test ! -e /root/.abuild; test ! -e /root/.gnupg")
    name = "tm-production-smoke-" + uuid.uuid4().hex[:12]
    fixture = Path(tempfile.mkdtemp(prefix="timemachine-production-smoke-", dir="/private/tmp"))
    users = fixture / "users"
    users.mkdir(mode=0o700)
    for user, uid, limit in (("matteo", 1001, "1300G"), ("anna", 1002, "500G")):
        password = secrets.token_hex(32)
        config = users / f"{user}.conf"
        config.write_text(
            f"TM_USERNAME={user}\nTM_GROUPNAME=timemachine\nPASSWORD={password}\n"
            f"SHARE_NAME='Time Machine di {user.title()}'\nVOLUME_SIZE_LIMIT={limit}\n"
            f"TM_UID={uid}\nTM_GID=1000\n"
        )
        config.chmod(0o600)
        auth = fixture / f"{user}.auth"
        auth.write_text(f"username = {user}\npassword = {password}\n")
        auth.chmod(0o600)
    try:
        docker("network", "create", "--internal", name)
        docker("volume", "create", name)
        docker("run", "--rm", "--network", "none", "--entrypoint", "sh",
               "--mount", f"type=volume,src={name},dst=/opt", image, "-ec",
               "mkdir /opt/anna /opt/matteo; chown 1002:1000 /opt/anna; "
               "chown 1001:1000 /opt/matteo; chmod 2755 /opt/anna /opt/matteo")
        docker("create", "--name", name, "--hostname", "tm-production-smoke",
               "--network", name, "--mount", f"type=volume,src={name},dst=/opt",
               "--tmpfs", "/run/samba", "--tmpfs", "/run/dbus",
               "-e", "EXTERNAL_CONF=/users", "-e", "SET_PERMISSIONS=false",
               "-e", "HIDE_SHARES=yes", "-e", "TIMEMACHINE_ISOLATED_LAB=yes",
               "-e", "EXPECTED_SAMBA_VERSION=4.23.13", image)
        docker("cp", str(users), f"{name}:/users")
        docker("cp", str(fixture), f"{name}:/run/lab")
        docker("start", name)
        result = docker("exec", "-i", name, "sh", input=(ROOT / "lab/smoke.sh").read_text())
        print(result)
        print(f"PASS: production default entrypoint; image={image}; fixtures={fixture}")
    finally:
        for args in (("rm", "-f", name), ("volume", "rm", name), ("network", "rm", name)):
            subprocess.run(["docker", "--context", "colima", *args],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
