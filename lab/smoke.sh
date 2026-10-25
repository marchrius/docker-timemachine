#!/bin/sh
set -eu
[ "${TIMEMACHINE_ISOLATED_LAB:-}" = yes ] || exit 1
fail() { echo "FAIL: $*" >&2; exit 1; }
smb() { smbclient "//127.0.0.1/$1" -A "/run/lab/$2.auth" -c "$3"; }

smbd --version
test "$(smbd --version)" = "Version ${EXPECTED_SAMBA_VERSION:?}"
testparm -s /etc/samba/smb.conf >/dev/null
test "$(id -u anna)" = 1002
test "$(id -u matteo)" = 1001
test "$(id -g anna)" = 1000
test "$(id -g matteo)" = 1000
# Account names and IDs only; never hashes.
pdbedit -L
attempt=0
until smb 'Time Machine di Matteo' matteo 'ls' >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  [ "$attempt" -lt 20 ] || fail 'SMB readiness/authentication'
  sleep 1
done
for process in smbd nmbd dbus-daemon avahi-daemon; do
  pidof "$process" >/dev/null || fail "process $process"
done
smb 'Time Machine di Anna' anna 'ls' >/dev/null
if smbclient '//127.0.0.1/Time Machine di Matteo' -N -c ls >/dev/null 2>&1; then
  fail 'guest access allowed'
fi
if smb 'Time Machine di Anna' matteo 'ls' >/dev/null 2>&1; then
  fail 'Matteo can access Anna share'
fi
if smb 'Time Machine di Matteo' anna 'ls' >/dev/null 2>&1; then
  fail 'Anna can access Matteo share'
fi

head -c 1048576 /dev/urandom > /run/lab/payload
printf 'synthetic alternate stream\n' > /run/lab/stream-payload
for user in anna matteo; do
  case "$user" in anna) share='Time Machine di Anna' ;; matteo) share='Time Machine di Matteo' ;; esac
  smb "$share" "$user" 'put /run/lab/payload lab-payload' >/dev/null
  smb "$share" "$user" "get lab-payload /run/lab/returned-$user" >/dev/null
  cmp /run/lab/payload "/run/lab/returned-$user"
  test "$(stat -c %u "/opt/$user/lab-payload")" = "$(id -u "$user")"
  setfattr -n user.lab -v synthetic "/opt/$user/lab-payload"
  test "$(getfattr --only-values -n user.lab "/opt/$user/lab-payload" 2>/dev/null)" = synthetic
  smb "$share" "$user" 'put /run/lab/stream-payload lab-payload:labmeta' >/dev/null
  smb "$share" "$user" "get lab-payload:labmeta /run/lab/returned-stream-$user" >/dev/null
  cmp /run/lab/stream-payload "/run/lab/returned-stream-$user"
  getfattr -m '^user\.DosStream\.' "/opt/$user/lab-payload" 2>/dev/null | grep -qi labmeta
  smb "$share" "$user" 'rename lab-payload lab-renamed' >/dev/null
  smb "$share" "$user" 'del lab-renamed' >/dev/null
done
# Validate advertisement content and registration inside the isolated bridge.
grep -q '_smb._tcp' /etc/avahi/services/smbd.service
grep -q '_device-info._tcp' /etc/avahi/services/smbd.service
grep -q '_adisk._tcp' /etc/avahi/services/smbd.service
grep -q 'adVN=Time Machine di Anna,' /etc/avahi/services/smbd.service
grep -q 'adVN=Time Machine di Matteo,' /etc/avahi/services/smbd.service
avahi-browse --resolve --terminate --parsable _adisk._tcp > /run/lab/avahi-browse
grep -qiF "$(hostname)" /run/lab/avahi-browse
grep -q 'adVN=Time Machine di Anna,' /run/lab/avahi-browse
grep -q 'adVN=Time Machine di Matteo,' /run/lab/avahi-browse
echo 'PASS: isolated synthetic laboratory (not proof of existing backup compatibility)'
