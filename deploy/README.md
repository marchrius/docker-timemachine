# Raspberry Pi production deployment

As of **2026-10-26**, Portainer stack `timemachine` (ID 29, environment 3)
uses [rupert.compose.yaml](rupert.compose.yaml), service `samba`, container
`timemachine-samba-1`. Portainer version **42** of the stack file was compared
byte for byte with this file after deployment. Prune and image repull were off.

The owner explicitly waived client verification on Anna's Mac. There is no
remaining requirement to perform that test.

## Image and persistent identity

- Samba **4.23.13**, ARM64, local image `timemachine-samba:4.23.13-r0`.
- Qualified image ID:
  `sha256:8a8fffb9c9ff5721562ab220fad54720ad1a460efebd1bba4d481028d55fe1e4`.
- `pull_policy: never` prevents silently replacing it with a registry image.
  The image is local to rupert; recovering another Docker host requires loading
  the archived image or building the pinned production target first.
- Samba state is in external Docker volume `timemachine_samba_state`, mounted
  at `/var/lib/samba` with `nocopy`. It must be retained during replacements.
- Data remains `/mnt/timemachine:/opt`; original user configs are mounted
  read-only from `/home/matteo/timemachine/users`.
- Original hostname, IP, MAC, share names, account IDs, Unix UID/GID, SID and
  `fruit streams_xattr` configuration are preserved.
- Only `/run/samba` is tmpfs. Do not persist or import live lock/cache state.
- Health checks verify all four service processes and valid Samba config;
  client authentication and backup success are separate checks.

The volume was initialized using [persist-state.py](persist-state.py), after
normal Mac image/share unmount and zero SMB sessions/open files. Both earlier
servers were stopped. The script archived the qualified 4.23.13 trial's
`/var/lib/samba`, imported it via a temporary stopped helper, and compared all
file contents, UID/GID, modes and link targets before the production server
started. The helper was removed; the external volume was retained and reused
by the production container. No backup data file was deleted or renamed.

After production boot: container healthy, expected persistent mount verified,
original SID/accounts and Unix UID/GID matched. Authentication/share listings
passed for both server accounts. Portainer also visibly reports `healthy`.

The **Mac** completed its production verification backup at **10:34:30 local**,
logging `Successfully completed backing up 1.53 GB` to
`2026-10-26-103414.backup`, on the existing APFS volume
`B6685763-598A-4D0D-97FB-D6F5A6DFD08C` and existing destination ID
`E4AF5718-A455-4E52-876E-CE2EF1A21993`. Automatic backups were verified still
enabled afterwards (`AutoBackup=1`). The earlier qualified-image trial also
passed a one-file restore; see [PI_TRIAL.md](../lab/PI_TRIAL.md).

Production container ID:
`2512cca66f94d60ee97b7af6b87ce2bcb6153bcc4ebe81017834429284ae350f`.

## Build / recover the image

On **Mac / Colima**, use the production target explicitly:

```sh
docker --context colima build --target production -f lab/Dockerfile.candidate -t timemachine-samba:4.23.13-r0 .
```

The default final target is for synthetic laboratory use. Do not deploy it on
real data. Source, base and packaging recipe are pinned; dependency repositories
are not fully archived, so a future rebuild need not have the same image ID.
Review and qualify a changed image before replacing the current release tag.

The original candidate archive already on **Pi** can recover the qualified
image without rebuilding. Run each command separately:

```sh
docker image load -i /home/matteo/timemachine-trial-20261026/candidate.tar
```

```sh
docker image tag timemachine-samba:trial-4.23.13 timemachine-samba:4.23.13-r0
```

Verify the resulting image ID above before deploying. Do not enable image
repull. The external network `timemachine_lan` must already exist with rupert's
original macvlan configuration. The state volume must already be initialized;
an external volume prevents Compose from silently substituting a new one.

## State backups and restore

The Docker volume is persistence, not a second backup of Samba state. Private
archives from this migration are in `/home/matteo/timemachine-trial-20261026`
(0700). `qualified-trial-state.tar` is the offline 4.23.13 state just before
production. `state.tar` and `original-image.tar` preserve the original 4.23.8
rollback. Configurations and the original Portainer stack are there too.
Never publish those files: they contain credentials or authentication state.

For another state backup, first stop active backups normally on **Mac** and
normally detach the identified disk image and SMB share. Check `smbstatus` on
**Pi** for zero open files. Never use force unmount as a shortcut.

On **Pi**, stop the production server normally:

```sh
docker stop --timeout 60 timemachine-samba-1
```

Set restrictive archive permissions in that same Pi shell:

```sh
umask 077
```

Choose a new timestamped filename, then archive the stopped container's mounted
state, preserving archive ownership and modes:

```sh
docker cp -a timemachine-samba-1:/var/lib/samba - > /home/matteo/timemachine-trial-20261026/samba-state-YYYYMMDD-HHMMSS.tar
```

Check the command succeeded before restarting the server:

```sh
docker start timemachine-samba-1
```

Keep private state/config/image archives in a separately protected backup as
well. Copying them off the Pi is not part of this deployment.

To restore state, stop all servers using the shares, retain the current volume
and create a **new** empty external volume. Import the selected offline archive
through a stopped helper mounting the new volume at `/var/lib/samba`, as in
`persist-state.py`. Verify the archive inventory before boot. Point Compose's
external volume name at the restored volume, then verify SID/account IDs,
authentication, Bonjour and a backup. Never overwrite live databases, import
cache/lease directories, or import upgraded state into an older Samba version.

## Rollback

Both `timemachine-core-1` (original 4.23.8) and `timemachine-samba-trial`
(qualified 4.23.13) are retained stopped, restart `no`, disconnected from LAN.
Do not prune them or start either alongside production.

For original-server rollback, first quiesce the Mac as above. On **Pi**, execute
each command separately:

```sh
docker update --restart=no timemachine-samba-1
```

```sh
docker stop --timeout 60 timemachine-samba-1
```

```sh
docker network disconnect timemachine_lan timemachine-samba-1
```

```sh
python3 /home/matteo/timemachine-trial-20261026/pi-trial.py restore-network
```

```sh
docker start timemachine-core-1
```

After verifying identity and client access, restore its original restart policy:

```sh
docker update --restart=always timemachine-core-1
```

This uses the original untouched container databases; the backup data remains
shared and is not rewound. The current Portainer definition still describes
production: reconcile it with the chosen rollback before any later deployment
or stack start. Keep pruning off while retaining `core` as an orphan rollback.
