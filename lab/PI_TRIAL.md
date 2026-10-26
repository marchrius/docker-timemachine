# Authorized Raspberry Pi trial — 2026-10-26

The owner authorized testing on the real service and accepts possible loss of
both Matteo's and Anna's backups. No existing backup was deleted or renamed.
This is a live trial, not yet a permanent Portainer stack deployment.

## Image

Build on **Mac / Colima**:

```sh
docker --context colima build --target production -f lab/Dockerfile.candidate -t timemachine-samba:trial-4.23.13 .
```

The `production` target uses the original `/entrypoint.sh`. It contains neither
`/lab` scripts nor fixture users/passwords. The default final `runtime` target
remains the synthetic laboratory image and must not be used on real data.
`python3 lab/production-smoke.py` tests the production default entrypoint in an
internal network with private, generated users and disposable data. It passed.
Colima does not expose Mac temporary paths as bind mounts, so fixtures are
transferred with `docker cp`; no Colima sharing configuration is changed.

## Actual deployment

On **Raspberry Pi / rupert.local**:

- Original container: `timemachine-core-1`, ID `34f6fe971983…`, retained stopped,
  restart policy `no`, disconnected from `timemachine_lan`.
- Original image: `sha256:0abac372d73223e96677add0a3071735e15640fc7d8ae14f042ad41d63eda440`.
- Trial: `timemachine-samba-trial`, ID `5d5a77b19134…`, Samba **4.23.13**,
  restart policy `unless-stopped`.
- Hostname `Time-Capsule`, network `timemachine_lan`, IP `192.168.3.54`,
  MAC `02:42:c0:a8:03:36`, aliases `core` and `timemachine-core-1` preserved.
- Existing `/mnt/timemachine:/opt` retained, without recursive permission changes.
- A private copy of the original users configuration is mounted read-only at
  `/users`. `SET_PERMISSIONS=false` and existing environment are preserved.
- Original SID, Samba accounts, share names, UID/GID, limits and effective
  `fruit streams_xattr` configuration verified after boot.
- `smbd`, `nmbd`, Avahi and D-Bus running. Authentication and share listings
  verified for both real users without displaying passwords.

Private Pi artifacts are under `/home/matteo/timemachine-trial-20261026` (0700):
original inspect/environment, users configuration, Samba/Avahi configuration,
identity references, original image archive, candidate archive and offline
Samba state archive. Never commit or publish those artifacts.

Before cutover, **Mac** reported `Running=0`; `hdiutil detach /dev/disk4`
successfully closed the identified Time Machine image, and the Pi then reported
zero open SMB files. Automatic backups remained enabled (`AutoBackup=1`).
The original server was stopped before archiving `/var/lib/samba`. No active
cache/lock directory was copied. Before candidate boot, every archived state
file's contents, owner, group, mode and link target matched the imported copy.

The Mac's existing destination ID `E4AF5718-A455-4E52-876E-CE2EF1A21993` was
retained. `tmutil startbackup` succeeded and completed at **09:55:32 local**.
Time Machine logged `Successfully completed backing up 613.8 MB` to
`2026-10-26-095522.backup`. `tmutil listbackups` lists that backup alongside the
seven earlier backups, and `diskutil apfs listSnapshots` confirms its snapshot:
`com.apple.TimeMachine.2026-10-26-095522.backup`, UUID
`7C6F3465-A055-4EB3-814D-0F94D4C9D231`, on the same existing APFS volume.
This was an incremental continuation, not a replacement backup from scratch.

A restore from this new snapshot **passed**. After the owner mounted it with
sudo, `mount` confirmed the exact `095522.backup` snapshot at
`/private/tmp/timemachine-trial-readonly.c0n6zW`, read-only. `tmutil restore -v`
restored `Data/Users/matteo/github/docker-timemachine/entrypoint.sh` into
`/private/tmp/timemachine-trial-restore.196Uc5/entrypoint.sh` (19,148 bytes).
Both byte comparisons passed: restored file against the snapshot source and
against the current repository file. `diskutil unmount` then successfully
unmounted only the temporary snapshot. The restored temporary file is retained.
This proves recovery of that file from the new backup, not every file in the
archive or a full-system restore. Anna's Mac has not been tested.

During the backup macOS logged missing checkpoint markers and transient local
file/xattr lookups; these did not prevent the explicit successful result. Do not
describe the session as free of all logged warnings/errors.

## Rollback, one command at a time

First stop any active backup normally on the **Mac**, then detach the currently
identified Time Machine disk image normally. Re-identify its device with
`hdiutil info`; do not assume it is still `/dev/disk4`. Verify no open backup
files on the **Pi** before stopping the trial. No force detach or TDB cleanup.

On **Pi**, run and inspect each step separately:

```sh
docker update --restart=no timemachine-samba-trial
```

```sh
docker stop --timeout 60 timemachine-samba-trial
```

```sh
docker network disconnect timemachine_lan timemachine-samba-trial
```

```sh
python3 /home/matteo/timemachine-trial-20261026/pi-trial.py restore-network
```

The last step uses Docker's local API to restore the saved per-endpoint MAC,
static IP and aliases; it does not start the original container.
The same API operation passed a disposable internal-network test on the Pi,
preserving the requested IP, MAC and alias without touching the live network.

```sh
docker start timemachine-core-1
```

Verify original network, SID/accounts, shares and client access, then restore
its original restart policy:

```sh
docker update --restart=always timemachine-core-1
```

The original container's databases were never modified by the candidate. This
rollback restores the server, not an earlier copy of the backup data: both
servers use the same data filesystem. Do not import upgraded databases back
into the original. Keep the stopped trial and artifacts for diagnosis.

Before making this permanent, update the Portainer stack, define persistent
Samba state for future replacements, and document backup/restore of that state.
Do not redeploy the old Portainer stack while the trial owns its network identity.
