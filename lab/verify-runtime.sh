#!/bin/sh
set -eu
test "$(uname -m)" = aarch64
expected=${EXPECTED_SAMBA_VERSION:-4.23.13}
test "$(smbd --version)" = "Version $expected"
smbd --version
for package in samba-server samba-common-tools samba-client; do
  apk info -e "$package" >/dev/null
done
packages=$(apk info -v | grep -E '^(samba-|libauth-samba-|libwbclient-|libsmbclient-|ldb-)')
printf '%s\n' "$packages"
printf '%s\n' "$packages" | while IFS= read -r package; do
  case "$package" in
    *-"$expected"-r0) ;;
    *) echo 'FAIL: mixed Samba package versions' >&2; exit 1 ;;
  esac
done
test -f /usr/lib/samba/vfs/fruit.so
test -f /usr/lib/samba/vfs/streams_xattr.so
ldd /usr/sbin/smbd
smbd -b | grep -E 'CONFIGFILE:|LOCKDIR:|CACHEDIR:|STATEDIR:|PRIVATE_DIR:|HAVE_.*(XATTR|ACL|AVAHI)'
if command -v gcc >/dev/null 2>&1; then
  echo 'FAIL: compiler included in runtime' >&2
  exit 1
fi
test ! -d /root/.abuild
test ! -d /root/.gnupg
echo 'PASS: clean ARM64 candidate runtime'
