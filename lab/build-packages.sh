#!/bin/sh
set -eu

test "$(uname -m)" = aarch64
test -f /work/main/samba/ORIGIN
sh /prepare-packages.sh APKBUILD /source /adaptations
version=$(cat /source/version)
mkdir -p /var/cache/distfiles
cp "/source/samba-$version.tar.gz" /var/cache/distfiles/

# The builder's preceding layer generated its ephemeral signing key and
# installed the public key into /etc/apk/keys before compiling anything.
abuild -F -r
