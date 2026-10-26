# Raspberry Pi production deployment

As of **2026-10-26**, Portainer stack `timemachine` (ID 29, environment 3)
uses [rupert.compose.yaml](rupert.compose.yaml), service `core`, container
`timemachine-core-1`, and the published GHCR image. This supersedes the initial
local-image deployment using service `samba` and Portainer file version 42.

The owner explicitly waived client verification on Anna's Mac. There is no
remaining requirement to perform that test.

## Image and persistent identity

- Samba **4.23.13**, ARM64, image `ghcr.io/marchrius/timemachine:4.23.13`.
- Published manifest digest:
  `sha256:1e12757108c7e4cbf79c7f3a3dce4ed4f0c7ca9e3d1aa844dcfa7e57fd176f79`.
- The previously qualified local image `timemachine-samba:4.23.13-r0` is retained:
  `sha256:8a8fffb9c9ff5721562ab220fad54720ad1a460efebd1bba4d481028d55fe1e4`.
- `pull_policy: missing` permits pulling the pinned version if it is not cached.
  GHCR publication does not automatically change the running Pi version.
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

After the initial production boot: container healthy, expected persistent mount verified,
original SID/accounts and Unix UID/GID matched. Authentication/share listings
passed for both server accounts. Portainer also visibly reports `healthy`.

The **Mac** completed its initial production verification backup at **10:34:30 local**,
logging `Successfully completed backing up 1.53 GB` to
`2026-10-26-103414.backup`, on the existing APFS volume
`B6685763-598A-4D0D-97FB-D6F5A6DFD08C` and existing destination ID
`E4AF5718-A455-4E52-876E-CE2EF1A21993`. Automatic backups were verified still
enabled afterwards (`AutoBackup=1`). The earlier qualified-image trial also
passed a one-file restore; see [PI_TRIAL.md](../lab/PI_TRIAL.md).

Initial local-image container ID (historical, no longer the running server):
`2512cca66f94d60ee97b7af6b87ce2bcb6153bcc4ebe81017834429284ae350f`.

## LAN configuration and deployment-error recovery

The Compose file explicitly creates a macvlan network named `timemachine_lan`
on `end0`, subnet `192.168.3.0/24`, gateway `192.168.3.254`, with an allocation
range restricted to **`192.168.3.54/32`**. The service retains that static IP and
MAC `02:42:c0:a8:03:36`.

Do not replace this definition with an empty `networks: {lan: {}}`: Docker
creates a bridge with an unrelated automatic subnet, rejecting the static LAN
address with `no configured subnet contains IP address 192.168.3.54`.

The restricted range is also required to coexist with rupert's other macvlan
network, `ps5_lan`, which reserves `192.168.3.201/32` on the same physical LAN.
Requesting the entire LAN pool again caused `Pool overlaps with other one on
this address space`. The `.54/32` configuration was tested with an empty
temporary network before production deployment. The other service/network was
not modified.

During the 2026-10-26 repair, only the incorrect **empty** Time Machine bridge
was removed. Original failed Compose files (v45/v46) and a coherent, read-only
offline archive of the existing Samba volume were saved privately under
`/home/matteo/timemachine-trial-20261026`. Database presence was checked before
startup. The service was recovered with Compose over SSH; Portainer's stored
file was aligned, then a successful Portainer update completed the repair.
Portainer's resulting v46 file matched the repository Compose byte for byte.
Final checks confirmed `healthy`, the expected macvlan/pool/IP/MAC, and the
original SID/accounts using the existing state volume. After final Portainer
reconciliation, the Mac completed a backup at **18:57:07 local**, logging
`Successfully completed backing up 783.2 MB` to `2026-10-26-185552.backup` on
the original APFS backup volume. Automatic backups remained enabled.

If a conflicting `timemachine_lan` already exists, inspect its driver, IPAM and
attached containers first. A network's subnet/driver cannot be repaired by
changing an image tag. Remove only an unused incorrect network; preserve any
network serving other containers. Keep the external Samba state volume.

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

Verify the local qualified image ID above before selecting that image as a
fallback. For the normal GHCR deployment, Compose creates the dedicated
macvlan itself. The external state volume must already be initialized;
declaring it external prevents Compose from silently substituting a new one.

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
docker stop --timeout 60 timemachine-core-1
```

Set restrictive archive permissions in that same Pi shell:

```sh
umask 077
```

Choose a new timestamped filename, then archive the stopped container's mounted
state, preserving archive ownership and modes:

```sh
docker cp -a timemachine-core-1:/var/lib/samba - > /home/matteo/timemachine-trial-20261026/samba-state-YYYYMMDD-HHMMSS.tar
```

Check the command succeeded before restarting the server:

```sh
docker start timemachine-core-1
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

The name `timemachine-core-1` now belongs to production, not the original 4.23.8
container. The original container and the initial `timemachine-samba-1` no
longer existed when the network-repair preflight ran. Do not apply the old
container-name rollback procedure from the historical trial document.

The stopped, disconnected `timemachine-samba-trial` and private image/state
archives remain available. Never start a second server on the same identity
or backup data concurrently.

For an image fallback **within the currently deployed Samba 4.23.13 version**,
quiesce the Mac, archive the current state offline, select the retained
`timemachine-samba:4.23.13-r0` image in the same Compose service, and redeploy
with the existing dedicated network and state volume. Verify identity,
authentication and backup access afterwards. Keep Portainer's file aligned
with the selected image.

Returning to the original Samba 4.23.8 requires rebuilding its configuration
from `original-image.tar` and restoring the matching **pre-upgrade** `state.tar`
into a separate new state volume. Do not mount the upgraded production state
into an older server. Neither image fallback nor server rollback rewinds the
shared backup data filesystem.
