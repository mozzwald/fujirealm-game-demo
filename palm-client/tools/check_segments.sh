#!/bin/sh
# Fails the build if any object reads another object's code-section data.
#
# m68k-palmos-gcc keeps const data in .text, reachable PC-relative from its
# own file only. A reference from another file is compiled A5-relative (an
# END16 relocation, meant for .data/.bss), so on the Palm it reads unrelated
# memory -- this once garbled every tile and every step the player took.
# Usage: check_segments.sh <objects...>   (inside the palmdev image)
status=0
text_syms=$(for o in "$@"; do
    m68k-palmos-objdump -t "$o" | awk '$0 ~ /\(sec  1\)/ && $0 ~ /\(scl   2\)/ {print $NF}'
done | sort -u)
for o in "$@"; do
    for sym in $(m68k-palmos-objdump -r "$o" | awk '$2 == "END16" {print $3}' | sort -u); do
        case "$sym" in .*) continue ;; esac
        if echo "$text_syms" | grep -qx "$sym"; then
            echo "check_segments: $o reads $sym, which is const data in another file's .text" >&2
            status=1
        fi
    done
done
exit $status
