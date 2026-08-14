#!/bin/sh
# Build (if stale) and launch under jzIntv with the FujiNet mailbox peripheral.
#
# Needs the FujiNet-patched jzIntv (--fujinet relays the $9C00 mailbox over
# TCP to a fujinet-firmware RS232/BoIP build, default localhost:9995) plus
# EXEC/GROM BIOS images. Without a running fujinet-pc the client boots to the
# offline demo mode.
set -e
cd "$(dirname "$0")"
SDL_AUDIODRIVER=pulseaudio
JZINTV_DIR=${JZINTV_DIR:-$HOME/Workspace/jzintv-20200712-src}
JZINTV=${JZINTV:-$JZINTV_DIR/bin/jzintv}
EXEC_BIN=${EXEC_BIN:-$JZINTV_DIR/rom/exec.bin}
GROM_BIN=${GROM_BIN:-$JZINTV_DIR/rom/grom.bin}
FUJINET_TARGET=${FUJINET_TARGET:-localhost:9995}

if [ ! -x "$JZINTV" ]; then
    echo "jzintv not found at $JZINTV (set JZINTV or JZINTV_DIR)" >&2
    exit 1
fi
for f in "$EXEC_BIN" "$GROM_BIN"; do
    if [ ! -f "$f" ]; then
        echo "BIOS image missing: $f" >&2
        exit 1
    fi
done

# Rebuild only if the ROM is missing or any source is newer than it.
if [ ! -f fujirealm.rom ] || [ -n "$(find . -maxdepth 1 -name '*.bas' -newer fujirealm.rom)" ]; then
    make
fi

exec "$JZINTV" \
    -z 4 \
    -e "$EXEC_BIN" \
    -g "$GROM_BIN" \
    --fujinet="$FUJINET_TARGET" \
    "$@" \
    fujirealm.rom
