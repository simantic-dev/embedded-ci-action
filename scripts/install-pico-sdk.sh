#!/usr/bin/env bash
# Installs the pico-sdk at tag $1 into $2/sdk, with tinyusb (USB console
# projects), and for pico-sdk 2.x builds picotool into $2/picotool so a
# project's configure finds it instead of fetching and building it each
# time. The same steps as review-image/Dockerfile's pico stage.
set -euo pipefail
tag=$1
dest=$2
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

git clone --quiet --depth 1 --branch "$tag" https://github.com/raspberrypi/pico-sdk "$dest/sdk"
git -C "$dest/sdk" submodule update --quiet --init --depth 1 lib/tinyusb
rm -rf "$dest/sdk/.git" "$dest/sdk/lib/tinyusb/.git"

# pico-sdk 1.x converts to UF2 with its own elf2uf2 and has no picotool.
if [ "${tag%%.*}" -ge 2 ]; then
  if git clone --quiet --depth 1 --branch "$tag" https://github.com/raspberrypi/picotool "$tmp/picotool"; then
    cmake -S "$tmp/picotool" -B "$tmp/picotool-build" -DCMAKE_BUILD_TYPE=Release \
      -DPICO_SDK_PATH="$dest/sdk" -DPICOTOOL_NO_LIBUSB=1 -DCMAKE_INSTALL_PREFIX="$dest/picotool"
    cmake --build "$tmp/picotool-build" --parallel "$(getconf _NPROCESSORS_ONLN)"
    cmake --install "$tmp/picotool-build"
  else
    echo "::notice::picotool has no $tag tag: the pico-sdk will fetch and build picotool during your build"
  fi
fi
