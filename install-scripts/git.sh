#!/bin/bash
set -euo pipefail

dnf install -y git-core --setopt=install_weak_deps=False --nodocs
cp "$(which git)" /opt/tools/bin/git

mkdir -p /opt/tools/lib64
ldd "$(which git)" | awk '/=>/ {print $3}' | while read -r lib; do
  base="$(basename "$lib")"
  case "$base" in
    libc.so.*|libpthread.so.*|libdl.so.*|libm.so.*|ld-linux*|librt.so.*|libresolv.so.*) continue ;;
  esac
  [ -f "$lib" ] && cp "$lib" /opt/tools/lib64/
done
