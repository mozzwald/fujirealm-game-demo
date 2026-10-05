# FujiRealm CoCo 3 client -- standalone Makefile (cmoc), same shape as
# lynx-client/Makefile and intv-client/Makefile. `defoogi` wraps the outer
# `make` invocation (see top-level Makefile); this file just calls `cmoc`
# and `decb` as ordinary PATH tools.
#
#   defoogi make coco     (from the repo root)
#   defoogi make          (from here)

# Two programs share the disk. PRODUCT is the setup program AUTOEXEC.BAS runs
# (display target, host, login); once a login exists it launches PLAY, the
# game, which is kept free of login/bootstrap/printf code to leave room.
DISK = FUJIRLM3
PRODUCT = $(DISK)
PLAY = FRPLAY
VIEW = ARTVIEW
SNDT = SNDTEST

CMOC ?= cmoc
DECB ?= decb

-include config.mk
SERVER_HOST        ?= localhost
HYBRID_SERVER_PORT ?= 9000
LOGIN_SERVER_PORT  ?= 9010

# FujiNet calls go through fujinet-lib-experimental, not the stable
# fujinet-lib. fnlib.py (copied unmodified from MekkoGX) clones it into
# _cache/, inside this tree so defoogi's container can see it, builds it, and
# reports the include/lib variables below.
FUJINET_LIB ?= https://github.com/RichStephens/fujinet-lib-experimental.git

define _newline


endef
# Not for a bare `make clean`, which would otherwise fetch the library first.
ifneq ($(MAKECMDGOALS),clean)
$(eval $(subst |,$(_newline),$(shell PLATFORM=coco ./fnlib.py $(FUJINET_LIB) | tr '\n' '|')))
ifeq ($(strip $(FUJINET_LIB_LDLIB)),)
  $(error fujinet-lib not available for coco -- check $(FUJINET_LIB))
endif
endif

SETUP_SRC = src/setup.c src/runm.c src/gime.c src/display.c \
	src/displayinit.c src/host.c \
	src/hostedit.c src/net.c src/input.c src/bf_proto.c src/login.c \
	src/identity.c src/itemseen.c src/ovlstore.c src/ovl_image.c \
	src/art_image.c
# redraw.c, sprites.c and hwscroll.c must stay last, in that order: their
# code is the overlay region (see ovl_api.h), and CMOC lays code out in
# command-line order.
PLAY_SRC = src/play.c src/gime.c src/palette.c src/ram.c \
	src/display.c src/rt_state.c src/terrain.c \
	src/live.c src/player.c src/controls.c src/prefs.c src/hud.c \
	src/sound.c src/sound_data.c src/redraw.c src/sprites.c src/hwscroll.c
# The art viewer (make artview, not part of all), on its own boot disk: every
# image with its use, and a sample scene.
VIEW_SRC = tools/artview/artview.c src/gime.c src/palette.c src/art_image.c
# The sound test (make sndtest, not part of all), on its own boot disk.
SNDT_SRC = tools/sndtest/sndtest.c src/sound.c src/sound_data.c
HEADERS = src/gime.h src/tiles.h src/palette.h src/ram.h \
	src/display.h src/host.h src/net.h src/input.h src/bf_proto.h \
	src/login.h src/identity.h src/runm.h src/rt_state.h src/terrain.h \
	src/live.h src/player.h src/controls.h src/hwscroll.h src/prefs.h \
	src/hud.h src/ovl_api.h src/art.h src/sound.h \
	src/server_host_default.h

# src/rt_state.c/.h started as lynx-client's realtime v3 codec. rt_crc16
# computes bit by bit instead of using 512 bytes of tables.
# src/bootstrap.c/.h are NOT built: the game attaches without a bootstrap and
# the server streams the terrain window in-band. Kept for reference.

# Compiled-in connection default (overridden at runtime by appkey key_id 3
# if the user has saved a host) -- mirrors tools/write_server_host_default.py
# for the Atari client, in header form for CMOC.
src/server_host_default.h: tools/gen_server_host_default.py
	./tools/gen_server_host_default.py "$(SERVER_HOST)" "$(HYBRID_SERVER_PORT)" "$(LOGIN_SERVER_PORT)" $@

# HDB-DOS's file buffers end at $0DD5, so the game loads from $0E00; setup
# keeps $1000. The stack starts at GFX_WINDOW (gime.h): task1 replaces
# everything at and above it while drawing. LIMIT caps program_end, leaving
# 512 bytes for the stack (the game measured a 252-byte peak).
ORG = 1000
PLAY_ORG = 0E00
LIMIT = 7E00
STACK = 8000

CFLAGS = --coco -Wno-assign-in-condition --no-relocate --intermediate \
	--limit=$(LIMIT) --initial-s=$(STACK) \
	-DBUILD_COCO -I$(FUJINET_LIB_INCLUDE)

# Must come after the source files on the cmoc command line.
LDLIBS = -L$(FUJINET_LIB_DIR) -l$(FUJINET_LIB_LDLIB)

SETUP_BIN = $(PRODUCT).bin
PLAY_BIN = $(PLAY).bin
VIEW_BIN = $(VIEW).bin
DSK = $(DISK).dsk
VIEW_DSK = $(VIEW).dsk
SNDT_BIN = $(SNDT).bin
SNDT_DSK = $(SNDT).dsk

.PHONY: all disk artview sndtest clean size

all: disk

$(SETUP_BIN): $(SETUP_SRC) $(HEADERS)
	$(CMOC) $(CFLAGS) --org=$(ORG) -DPLAY_PROGRAM=\"$(PLAY)\" -o $@ $(SETUP_SRC) $(LDLIBS)

$(PLAY_BIN): $(PLAY_SRC) $(HEADERS)
	$(CMOC) $(CFLAGS) --org=$(PLAY_ORG) -o $@ $(PLAY_SRC) $(LDLIBS)

$(VIEW_BIN): $(VIEW_SRC) $(HEADERS)
	$(CMOC) $(CFLAGS) -Isrc --org=$(ORG) -o $@ $(VIEW_SRC)

src/sound_data.c: tools/sound_gen.py
	./tools/sound_gen.py $@

$(SNDT_BIN): $(SNDT_SRC) src/sound.h src/gime.h
	$(CMOC) $(CFLAGS) -Isrc --org=$(ORG) -o $@ $(SNDT_SRC)

# The overlay (ovl_api.h) is linked into the game's renderer region, so it is
# built after the game, and the setup program carries its image.
OVL = FROVL
OVL_SRC = src/ovl_help.c src/ovl_dialogue.c

$(OVL).raw: $(OVL_SRC) src/ovl_api.h src/rt_state.h $(PLAY_BIN)
	./tools/ovl_region.py check128k $(PLAY).map
	$(CMOC) --coco --no-relocate --raw --intermediate -nodefaultlibs \
		--org=$$(./tools/ovl_region.py start $(PLAY).map) \
		-o $@ $(OVL_SRC) -lcmoc-std-ecb

# ovl_pack.py also fails the build if the overlay overruns the region.
src/ovl_image.c: $(OVL).raw tools/ovl_pack.py
	./tools/ovl_pack.py $(OVL).raw $(OVL).map \
		$$(./tools/ovl_region.py end $(PLAY).map) $@

src/art_image.c: art/coco_tileset.json src/palette.c tools/art_pack.py
	./tools/art_pack.py art/coco_tileset.json src/palette.c $@

# RUNM, not LOADM:EXEC: the load overwrites this BASIC program ($2601), so
# nothing after it can be parsed.
AUTOEXEC.BAS: Makefile
	@printf '10 RUNM"%s"\n' $(PRODUCT) > $@

$(DSK): $(SETUP_BIN) $(PLAY_BIN) AUTOEXEC.BAS
	rm -f $@
	$(DECB) dskini $@
	$(DECB) copy -b -2 $(SETUP_BIN) $@,$(PRODUCT).BIN
	$(DECB) copy -b -2 $(PLAY_BIN) $@,$(PLAY).BIN
	$(DECB) copy -t -0 AUTOEXEC.BAS $@,AUTOEXEC.BAS
	@$(DECB) dir $@

disk: $(DSK)

artview: $(VIEW_DSK)

$(VIEW_DSK): $(VIEW_BIN)
	rm -f $@ view_autoexec.bas
	@printf '10 RUNM"%s"\n' $(VIEW) > view_autoexec.bas
	$(DECB) dskini $@
	$(DECB) copy -b -2 $(VIEW_BIN) $@,$(VIEW).BIN
	$(DECB) copy -t -0 view_autoexec.bas $@,AUTOEXEC.BAS
	@$(DECB) dir $@

sndtest: $(SNDT_DSK)

$(SNDT_DSK): $(SNDT_BIN)
	rm -f $@ sndtest_autoexec.bas
	@printf '10 RUNM"%s"\n' $(SNDT) > sndtest_autoexec.bas
	$(DECB) dskini $@
	$(DECB) copy -b -2 $(SNDT_BIN) $@,$(SNDT).BIN
	$(DECB) copy -t -0 sndtest_autoexec.bas $@,AUTOEXEC.BAS
	@$(DECB) dir $@

# How far each program's program_end reached (limit $(LIMIT)).
size: $(SETUP_BIN) $(PLAY_BIN)
	@for p in $(PRODUCT) $(PLAY); do \
	  printf '%s: ' $$p; grep -m1 'Symbol: program_end' $$p.map || echo "program_end not found"; \
	done

clean:
	rm -f $(SETUP_BIN) $(PLAY_BIN) $(VIEW_BIN) $(SNDT_BIN) $(DSK) $(VIEW_DSK) $(SNDT_DSK) view_autoexec.bas sndtest_autoexec.bas AUTOEXEC.BAS *.map *.asm *.lst *.link *.o *.s src/*.o src/server_host_default.h \
		$(OVL).raw src/ovl_image.c src/art_image.c src/sound_data.c
