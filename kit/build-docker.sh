#!/bin/bash
# Genera la ISO dentro un container Ubuntu (serve Docker).
# Utile su Fedora, Arch, WSL o qualsiasi Linux.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

docker run --rm --privileged \
  -v "$PWD:/nido" \
  -v nido-build:/build \
  -e NIDO_WORK=/build/work \
  -e NIDO_CACHE=/build/cache \
  ubuntu:26.04 \
  bash -c "tr -d '\r' < /nido/build.sh > /tmp/build.sh && NIDO_ROOT=/nido bash /tmp/build.sh"
