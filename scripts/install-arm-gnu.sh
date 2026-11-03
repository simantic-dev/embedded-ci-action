#!/usr/bin/env bash
# Installs Arm GNU Toolchain release $1 for this runner into $2, checked
# against the .sha256asc Arm publishes beside each tarball. The docs are
# dropped, as review-image/Dockerfile does, so the cache is smaller.
set -euo pipefail
version=$1
dest=$2

case "$RUNNER_OS-$RUNNER_ARCH" in
  Linux-X64) host=x86_64 ;;
  Linux-ARM64) host=aarch64 ;;
  macOS-ARM64) host=darwin-arm64 ;;
  macOS-X64) host=darwin-x86_64 ;;
  *) echo "::error::no Arm GNU Toolchain download for $RUNNER_OS $RUNNER_ARCH: install it yourself and leave out the setup step"; exit 1 ;;
esac

name="arm-gnu-toolchain-${version}-${host}-arm-none-eabi"
url="https://developer.arm.com/-/media/Files/downloads/gnu/${version}/binrel/${name}.tar.xz"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# developer.arm.com can be slow and drop connections partway: a download
# that stalls (under 10 KB/s for 30 s) or breaks is picked up where it
# left off (-C -), up to 6 times, rather than hanging or starting over.
fetch() {
  local n
  for n in 1 2 3 4 5 6; do
    curl -fsSL -C - --connect-timeout 30 --speed-limit 10240 --speed-time 30 -o "$1" "$2" && return 0
    [ "$n" = 6 ] || { echo "Download interrupted, resuming ($n of 5)"; sleep 5; }
  done
  return 1
}

echo "Downloading $url"
if ! fetch "$tmp/$name.tar.xz" "$url"; then
  echo "::error::could not download Arm GNU Toolchain $version for $host from $url"
  exit 1
fi
fetch "$tmp/$name.tar.xz.sha256asc" "$url.sha256asc"
(cd "$tmp" && shasum -a 256 -c "$name.tar.xz.sha256asc")

mkdir -p "$dest"
tar -xJf "$tmp/$name.tar.xz" -C "$dest" --strip-components=1
rm -rf "$dest/share/doc" "$dest/share/info" "$dest/share/man"
