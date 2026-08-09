# Third-Party Notices

FujiRealm itself; the game, the two clients, the server, the tools and the art,  
is MIT licensed; see `LICENSE`. This file records the third-party work it  
builds on, and what each piece asks of you if you redistribute it.

None of it imposes copyleft on your own game if you use this repository as a  
starting point.

---

## Altirra — Netstream handler (vendored source)

`atari8-client/netstream/src/` is a strip-down of Altirra's replacement 850  
interface firmware, keeping the concurrent-mode POKEY serial engine and its IRQ  
handlers. It is assembled into `NSENGINE.OBX` and combined into the shipped  
`fujirealm.xex`, so **the notice below travels with the released binary as well**  
**as the source**.

> Altirra - Atari 800/800XL/5200 emulator  
> Copyright (C) 2008-2019 Avery Lee
> Copying and distribution of this file, with or without modification, are  
> permitted in any medium without royalty provided the copyright notice and  
> this notice are preserved. This file is offered as-is, without any warranty.

Files: `netstream.s`, `include/hardware.inc`, `include/kerneldb.inc`,  
`include/sio.inc`, `include/sio.s`. Each carries the notice in its own header;  
leave those headers intact.

Reached this repository by way of  
[https://github.com/mozzwald/fujinet-atari-netstream](https://github.com/mozzwald/fujinet-atari-netstream), which packages the  
handler for FujiNet. That repository carries a GPL-2.0 `LICENSE` at its root,  
but these specific files are governed by Avery Lee's all-permissive notice  
above, which is what allows them to be vendored here under MIT. See  
`atari8-client/netstream/UPSTREAM.md` for the exact commit and how to re-sync.

## cc65 — Lynx runtime and libraries

The Lynx cartridge (`lynx-client/fujirealm.lnx`) links the cc65 C runtime, its  
Lynx target support, the TGI graphics driver, and the ComLynx serial driver.  
cc65 is distributed under a zlib-derived license:

> This software is provided 'as-is', without any express or implied warranty.  
> In no event will the authors be held liable for any damages arising from the  
> use of this software.
> Permission is granted to anyone to use this software for any purpose,  
> including commercial applications, and to alter it and redistribute it  
> freely, subject to the following restrictions:
> 1. The origin of this software must not be misrepresented; you must not claim
>   that you wrote the original software.
> 2. Altered source versions must be plainly marked as such, and must not be
>   misrepresented as being the original software.
> 3. This notice may not be removed or altered from any source distribution.

No cc65 source is redistributed here; it is a build dependency.  
[https://cc65.github.io/](https://cc65.github.io/)

## Charsetter — the tile editor this one grew from

`tools/tile-editor/` began as **Charsetter**, the Atari 8-bit font and map  
editor by Dely, and was reworked into FujiRealm's  
tile-model editor with the author's express permission. Our thanks to them.

[https://www.atari.org.pl/charsetter/](https://www.atari.org.pl/charsetter/)

## Bootstrap Icons — tile editor UI

`tools/tile-editor/icons.css` contains 19 icons from Bootstrap Icons v1.11.3,  
inlined as CSS masks so the editor needs no network access.

> The MIT License (MIT)  
> Copyright (c) 2019-2024 The Bootstrap Authors
> Permission is hereby granted, free of charge, to any person obtaining a copy  
> of this software and associated documentation files (the "Software"), to deal  
> in the Software without restriction... The above copyright notice and this  
> permission notice shall be included in all copies or substantial portions of  
> the Software.

[https://github.com/twbs/icons](https://github.com/twbs/icons)

## MyPicoDos — bootable ATR images only

`make -C atari8-client atr` asks `dir2atr` to write MyPicoDOS 4.06 boot sectors  
into `fujirealm.atr`, so that the disk autoruns the game and disables BASIC on  
XL/XE. MyPicoDos is by Matthias Reichl and ships as part of AtariSIO, which is  
**GPL-2.0**.

This affects the generated disk image only — not this repository's source, and  
not the plain `fujirealm.xex`. `fujirealm.atr` is deliberately not committed. If  
you distribute a built ATR (for example as a release asset), you are  
distributing an aggregate that includes MyPicoDos: credit it and point users at  
AtariSIO for its source, and confirm its current terms before you do.

[https://github.com/HiassofT/MyPicoDOS](https://github.com/HiassofT/MyPicoDOS)  
[https://www.horus.com/~hias/atari/](https://www.horus.com/~hias/atari/)

## Build-time tools

Not linked into any shipped artifact and not redistributed here:

- **MADS** (Mad Assembler) — assembles the Atari client.
- **dir2atr** (AtariSIO) — builds the ATR.
- **Pillow** — used only by the optional Lynx art/mockup scripts.
- **node** — runs the tile editor's model tests.
