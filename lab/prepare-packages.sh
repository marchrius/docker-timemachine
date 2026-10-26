#!/bin/sh
set -eu
recipe=${1:-APKBUILD}
source_dir=${2:-/source}
adaptations=${3:-/adaptations}
version=$(cat "$source_dir/version")
printf '%s\n' "$version" | grep -Eq '^4\.23\.[0-9]+$'
source_line=$(cat "$source_dir/source.sha512")
source_sha=${source_line%% *}
printf '%s\n' "$source_sha" | grep -Eq '^[0-9a-f]{128}$'
test "$source_line" = "$source_sha  samba-$version.tar.gz"
grep -Fxq 'pkgver=4.23.8' "$recipe"
musl_sha=61e95b1908f3453e8f80655f846b995748d57418ef08d87358ac7fd11f1d5a9dd212b79b19a73ca091dab3179db6ce9df7cb4f170d1dff88b6f139c91c7093a6
echo "$musl_sha  $adaptations/musl_uintptr.patch" | sha512sum -c -
cp "$adaptations/musl_uintptr.patch" "$(dirname "$recipe")/musl_uintptr.patch"
sed \
  -e "s/^pkgver=4\\.23\\.8$/pkgver=$version/" \
  -e "s/^[0-9a-f]*  samba-4\\.23\\.8\\.tar\\.gz$/$source_sha  samba-$version.tar.gz/" \
  -e "s/^[0-9a-f]*  musl_uintptr\\.patch$/$musl_sha  musl_uintptr.patch/" \
  "$recipe" > "$recipe.updated"
mv "$recipe.updated" "$recipe"
grep -Fxq "pkgver=$version" "$recipe"
grep -Fxq "$source_sha  samba-$version.tar.gz" "$recipe"
