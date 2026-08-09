# Vendored Netstream handler

`src/` is a verbatim copy of the MADS build of the FujiNet Netstream handler.
It is vendored rather than fetched so that a plain `git clone && make` builds the
Atari client with nothing but `mads` installed.

| | |
| --- | --- |
| Upstream | https://github.com/mozzwald/fujinet-atari-netstream |
| Path | `handler/mads/` |
| Commit | `b1db8295adc401851454e82b50eb7a372aa35a7c` (2026-07-13) |
| Files | `netstream.s`, `include/{hardware,kerneldb,sio}.inc`, `include/sio.s` |

## Licensing

Every one of these files is derived from **Altirra**, © 2008–2019 Avery Lee, and
carries this notice in its header — leave it intact:

```
Copying and distribution of this file, with or without modification,
are permitted in any medium without royalty provided the copyright
notice and this notice are preserved.  This file is offered as-is,
without any warranty.
```

`netstream.s` is a strip-down of Altirra's replacement 850 interface firmware:
it keeps the concurrent-mode serial engine and its IRQ handlers, and drops the
device handler glue, the auto-install chain, and non-concurrent I/O. See
`THIRD-PARTY-NOTICES.md` at the repository root.

## Re-syncing with upstream

```sh
git clone https://github.com/mozzwald/fujinet-atari-netstream /tmp/netstream
cp /tmp/netstream/handler/mads/netstream.s        src/
cp /tmp/netstream/handler/mads/include/*.inc      src/include/
cp /tmp/netstream/handler/mads/include/sio.s      src/include/
make -C .. clean all
```

Then update the commit hash in the table above. The build assembles this source
with `BASEADDR=$9000` and `INPUT_BUFSIZE=1024`; `$9000` is chosen because the
handler's own `$2800` default overlaps the game's main segment. See
`docs/MEMORY_LAYOUT.md`.
