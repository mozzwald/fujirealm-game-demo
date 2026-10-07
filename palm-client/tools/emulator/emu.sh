#!/bin/sh
# Run CloudpilotEmu with its CLI fed from the ./cmd FIFO; send commands with
#   echo "screenshot shot.png" > cmd
# Usage: emu.sh <rom-or-image> [extra cloudpilot-emu options]
cd "$(dirname "$0")"
EMU=../cloudpilot-emu/src/cloudpilot/cloudpilot-emu
[ -p cmd ] || mkfifo cmd
# Hold the FIFO open so each echo does not end the CLI's input.
exec 3<>cmd
exec "$EMU" "$@" < cmd
