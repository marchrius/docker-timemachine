#!/bin/sh
set -eu
[ "${TIMEMACHINE_ISOLATED_LAB:-}" = yes ]
[ "${STATE_TRANSFER_LAB:-}" = yes ]
[ "$(hostname)" = tm-state-lab ]
smb() {
  smbclient '//127.0.0.1/Time Machine di Matteo' -A /run/lab/matteo.auth -c "$1" >/dev/null
}
expected() {
  printf 'Synthetic baseline data, preserved across Samba upgrade.\n' > /run/lab/state-expected
  printf 'Synthetic named stream, preserved across Samba upgrade.\n' > /run/lab/stream-expected
  printf 'Synthetic data written by Samba 4.23.13.\n' > /run/lab/upgraded-expected
}
expected
case "${1:?seed, verify, identity, write-upgraded or verify-upgraded}" in
  seed)
    smb 'put /run/lab/state-expected state-origin'
    smb 'put /run/lab/stream-expected state-origin:migration-check'
    setfattr -n user.migration_lab -v synthetic-only /opt/matteo/state-origin
    setfacl -m u:1002:r-- /opt/matteo/state-origin
    ;;
  verify)
    smb 'get state-origin /run/lab/state-returned'
    smb 'get state-origin:migration-check /run/lab/stream-returned'
    cmp /run/lab/state-expected /run/lab/state-returned
    cmp /run/lab/stream-expected /run/lab/stream-returned
    test "$(getfattr --only-values -n user.migration_lab /opt/matteo/state-origin 2>/dev/null)" = synthetic-only
    echo 'PASS: original synthetic data, named stream and xattr'
    ;;
  identity)
    net getlocalsid
    for user in anna matteo; do
      printf '%s UID=%s GID=%s\n' "$user" "$(id -u "$user")" "$(id -g "$user")"
      # Only account SIDs, never password hashes or a TDB dump.
      pdbedit -L -v -u "$user" | grep -E '^User SID:|^Primary Group SID:'
    done
    stat -c '%n %u:%g %a' /opt/anna /opt/matteo /opt/matteo/state-origin
    getfacl -c -n /opt/matteo/state-origin
    ;;
  write-upgraded)
    test "$(smbd --version)" = 'Version 4.23.13'
    smb 'put /run/lab/upgraded-expected state-upgraded'
    smb 'put /run/lab/stream-expected state-upgraded:migration-check'
    ;;
  verify-upgraded)
    smb 'get state-upgraded /run/lab/upgraded-returned'
    smb 'get state-upgraded:migration-check /run/lab/upgraded-stream-returned'
    cmp /run/lab/upgraded-expected /run/lab/upgraded-returned
    cmp /run/lab/stream-expected /run/lab/upgraded-stream-returned
    echo 'PASS: data and stream written by upgraded server are readable'
    ;;
  *) exit 2 ;;
esac
