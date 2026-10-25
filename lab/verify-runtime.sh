#!/bin/sh
set -eu
test "$(uname -m)" = aarch64
test "$(smbd --version)" = 'Version 4.23.13'
smbd --version
for package in samba-server samba-common-tools samba-client; do
  apk info -e "$package" >/dev/null
done
packages=$(apk info -v | grep -E '^(samba-|libauth-samba-|libwbclient-|libsmbclient-|ldb-)')
printf '%s\n' "$packages"
if printf '%s\n' "$packages" | grep -v -- '-4.23.13-r0$'; then
  echo 'FAIL: mixed Samba package versions' >&2
  exit 1
fi
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
