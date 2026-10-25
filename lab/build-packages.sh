#!/bin/sh
set -eu

# The source is authenticated in the preceding Docker stage. Keep Alpine's
# existing patch/file checksums; replace only the verified release checksum.
test "$(uname -m)" = aarch64
test -f /work/main/samba/ORIGIN
source_sha=$(cut -d ' ' -f 1 /source/source.sha512)
test "${#source_sha}" = 128
sed -i \
  -e 's/^pkgver=4\.23\.8$/pkgver=4.23.13/' \
  -e "s/^[0-9a-f]*  samba-4\.23\.8\.tar\.gz$/$source_sha  samba-4.23.13.tar.gz/" \
  APKBUILD
grep -qx 'pkgver=4.23.13' APKBUILD
grep -qx "$source_sha  samba-4.23.13.tar.gz" APKBUILD
musl_sha=61e95b1908f3453e8f80655f846b995748d57418ef08d87358ac7fd11f1d5a9dd212b79b19a73ca091dab3179db6ce9df7cb4f170d1dff88b6f139c91c7093a6
echo "$musl_sha  /adaptations/musl_uintptr.patch" | sha512sum -c -
cp /adaptations/musl_uintptr.patch musl_uintptr.patch
sed -i "s/^[0-9a-f]*  musl_uintptr\.patch$/$musl_sha  musl_uintptr.patch/" APKBUILD
mkdir -p /var/cache/distfiles
cp /source/samba-4.23.13.tar.gz /var/cache/distfiles/

# The builder's preceding layer generated its ephemeral signing key and
# installed the public key into /etc/apk/keys before compiling anything.
abuild -F -r
