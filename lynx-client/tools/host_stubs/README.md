# Host stubs

Just enough of the cc65 Lynx target (`lynx.h`, `tgi.h`, `joystick.h`,
`serial.h`) for a host compiler to build `src/render.c`.

`render.c` and `main.c` are Lynx-only, so for a long time nothing but cc65 ever
compiled them -- and cc65 warns about very little. These stubs let gcc's
`-Wall -Wextra` (and the render host test) see that code too. The Phase 13
sprite-trail bug lived in `render.c`'s double-buffer bookkeeping, which nothing
could test.

They are deliberately minimal: types and prototypes only, no behaviour. The
test that uses them supplies its own tgi implementation.

Lint both Lynx-only files with:

    gcc -fsyntax-only -O2 -Wall -Wextra -Isrc -Itools/host_stubs src/render.c
