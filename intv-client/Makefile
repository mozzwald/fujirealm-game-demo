# FujiRealm Intellivision client -- IntyBASIC build.
#
# Tools: intybasic (compiler) + as1600 (from jzIntv's SDK-1600), both on PATH.
# LIBDIR must hold intybasic_prologue.asm / intybasic_epilogue.asm.
#
# The server endpoint is baked at build time like the other clients:
#   make SERVER_HOST=192.168.1.100
# or copy config.mk.example to config.mk and edit (config.mk is git-ignored).
# The default localhost only works under emulation.

INTYBASIC ?= intybasic
AS1600    ?= as1600
LIBDIR    ?= $(HOME)/Workspace/IntyBASIC/intybasic/

-include config.mk
SERVER_HOST        ?= localhost
HYBRID_SERVER_PORT ?= 9000
LOGIN_SERVER_PORT  ?= 9010

PRODUCT = fujirealm

# Every .bas that participates in the build, listed explicitly: relying on a
# wildcard or a partial list means editing one file alone doesn't trigger a
# rebuild.
SOURCES = fujirealm.bas frconst.bas vars.bas fujinet.bas server_cfg.bas crc_tab.bas \
          gfx.bas testmap.bas rt.bas bootstrap.bas cache.bas state.bas \
          render.bas input.bas login.bas sound.bas

.PHONY: all clean run

all: $(PRODUCT).bin $(PRODUCT).rom

# Endpoint DATA tables; regenerated whenever config.mk (if present) or the
# generator changes, so a host change always relinks.
server_cfg.bas: $(wildcard config.mk) tools/gen_server_cfg.py Makefile
	python3 tools/gen_server_cfg.py "$(SERVER_HOST)" "$(HYBRID_SERVER_PORT)" "$(LOGIN_SERVER_PORT)" > $@
	@echo "Baked endpoint: $(SERVER_HOST):$(HYBRID_SERVER_PORT) (login :$(LOGIN_SERVER_PORT))"

$(PRODUCT).asm: $(SOURCES)
	$(INTYBASIC) fujirealm.bas $(PRODUCT).asm $(LIBDIR)

# .bin + .cfg -- for loading from SD via the PiRTO II menu.
$(PRODUCT).bin: $(PRODUCT).asm
	$(AS1600) -o $(PRODUCT).bin -l $(PRODUCT).lst $(PRODUCT).asm

# .rom -- Intellicart format, for jzIntv.
$(PRODUCT).rom: $(PRODUCT).asm
	$(AS1600) -o $(PRODUCT).rom $(PRODUCT).asm

run: $(PRODUCT).rom
	./run.sh

clean:
	rm -f $(PRODUCT).asm $(PRODUCT).bin $(PRODUCT).cfg $(PRODUCT).rom $(PRODUCT).lst server_cfg.bas
