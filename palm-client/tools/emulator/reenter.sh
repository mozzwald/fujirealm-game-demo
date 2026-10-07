#!/bin/sh
# Soft-reset the running emulator, install a .prc, launch FN Realm and press
# Play. Usage: reenter.sh <prc>
cd "$(dirname "$0")"
echo 'reset-soft' > cmd; sleep 8
echo "install $1" > cmd; sleep 2
echo 'launch "FN Realm"' > cmd; sleep 3
echo 'tap 12 152' > cmd; sleep 18
