#!/bin/sh
# Palm playtest rig: CloudpilotEmu <-> socat pty pair <-> FujiNet-PC.
#   rig.sh <rom-or-image> [cloudpilot options]
# Drive the emulator with:  echo "<cli command>" > cmd
# Logs: emu.log, socat.log (hex dump of every cradle byte), ../fnpc/fujinet.log
cd "$(dirname "$0")"
RUN=$PWD
pkill -9 -f "cloudpilot/cloudpilot-emu" 2>/dev/null
pkill -f "fujinet -c fnconfig.ini" 2>/dev/null
pkill -f "link=$RUN/palm-tty" 2>/dev/null
sleep 0.5
socat -d -d -x pty,raw,echo=0,link=$RUN/palm-tty pty,raw,echo=0,link=$RUN/fn-tty \
    > socat.log 2>&1 &
sleep 0.5
(cd ../fnpc && ./fujinet -c fnconfig.ini -s SD -u http://0.0.0.0:8001 > fujinet.log 2>&1 &)
sleep 1
exec ./emu.sh "$@" --serial "$RUN/palm-tty"
