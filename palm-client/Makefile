# FujiRealm Palm client (FN Realm): FujiNet N1: over a selected Palm link.
#
#   make                        build/FujiRealm.prc
#   make SERVER_HOST=my.host    bake another default server in (same variables
#                               as the other clients; the server can also be
#                               changed on the Palm)
#   make install FUJINET=ip     queue the .prc on FujiNet's SD card over WebDAV;
#                               the next HotSync installs it
#
# Builds in a Palm toolchain Docker image with the FujiBus code from
# Texas Hold'em and the selectable port driver in src/fnlink.c. The protocol,
# bootstrap, terrain-cache, prediction and dialogue code is compiled straight
# from ../lynx-client/src and the identity record from ../amiga-client/src,
# so the clients share one copy of it. Art is converted on the host (the
# image has no Python).

-include config.mk

SERVER_HOST ?= fujinet.online
HYBRID_SERVER_PORT ?= 9000
LOGIN_SERVER_PORT ?= 9010
FUJINET_HOLDEM ?= $(abspath ../../../fujinet-texasHoldEm)
FUJINET ?= fujinet.local
# 2: four greys (any Palm OS 3.x device: III, IIIx, V, m100...);
# 1: the 1-bit tileset on the default black-and-white screen;
# 8: the Lynx's colour art on a colour Palm (OS 3.5 and later: IIIc, m505...).
# The .prc is also copied to build/FujiRealm-<depth>bpp.prc.
GFX_DEPTH ?= 2
IMAGE ?= fujinet-palm-toolchain

APP := FujiRealm
NAME := "FN Realm"
CREATOR := ADFR

REPO := $(abspath ..)
ART_JSON := ../lynx-client/art/lynx_tileset.json
GENERATED := build/art/palm_art.c build/art/palm_art.h build/icon.bmp \
	build/icon-small.bmp

DOCKER := docker run --rm --platform linux/amd64 -v $(REPO):/src \
	-v $(abspath $(FUJINET_HOLDEM)):/fnlegacy:ro -w /src/palm-client $(IMAGE)

all: build/$(APP).prc
	@cp build/$(APP).prc build/$(APP)-$(GFX_DEPTH)bpp.prc
	@echo "$(APP).prc ($(GFX_DEPTH) bpp) -> $(SERVER_HOST):$(HYBRID_SERVER_PORT) (login $(LOGIN_SERVER_PORT))"

# Always rebuilt: the whole app compiles in seconds, and this way a changed
# SERVER_HOST or the transport checkout can never leave a stale binary.
build/$(APP).prc: $(GENERATED) FORCE
	$(DOCKER) make --no-print-directory palm SERVER_HOST=$(SERVER_HOST) \
		HYBRID_SERVER_PORT=$(HYBRID_SERVER_PORT) \
		LOGIN_SERVER_PORT=$(LOGIN_SERVER_PORT) GFX_DEPTH=$(GFX_DEPTH)

build/art/palm_art.c build/art/palm_art.h: tools/palm_art.py $(ART_JSON) \
		../lynx-client/tools/import_lynx_art.py
	python3 tools/palm_art.py build/art/palm_art.c build/art/palm_art.h

build/icon.bmp build/icon-small.bmp: tools/mkicon.py tools/palm_art.py $(ART_JSON)
	@mkdir -p build
	python3 tools/mkicon.py build/icon.bmp build/icon-small.bmp

# FujiNet's WebDAV can acknowledge the first PUT into an emptied folder
# without keeping the file, so read it back and retry until it matches.
install: build/$(APP).prc
	@for try in 1 2 3; do \
		curl -fsS -o /dev/null -T build/$(APP).prc \
			http://$(FUJINET)/dav/palm/install/$(APP).prc && sleep 2 && \
		curl -fsS -o build/readback.prc \
			'http://$(FUJINET)/files/download?path=/palm/install/$(APP).prc' && \
		cmp -s build/readback.prc build/$(APP).prc && \
		{ echo "Queued on $(FUJINET) (verified); HotSync the Palm to install it."; \
		  exit 0; }; \
		echo "Upload not kept, retrying..."; \
	done; echo "Could not queue $(APP).prc on $(FUJINET)"; exit 1

clean:
	rm -rf build

# ---- Inside the Palm toolchain image ---------------------------------
COMMON := /fnlegacy/palm/common
SHARED := ../lynx-client/src
CC := m68k-palmos-gcc
CFLAGS := -Os -Wall -palmos3.5 -Isrc -I$(SHARED) -I../amiga-client/src \
	-Ibuild/art -I$(COMMON) \
	'-DAPP_CREATOR_STR="$(CREATOR)"' \
	-D'SERVER_HOST="$(SERVER_HOST)"' -DHYBRID_SERVER_PORT=$(HYBRID_SERVER_PORT) \
	-DLOGIN_SERVER_PORT=$(LOGIN_SERVER_PORT) -DGFX_DEPTH=$(GFX_DEPTH)
SOURCES := src/$(APP).c src/gfx.c src/net.c src/fnlink.c \
	$(SHARED)/bootstrap.c $(SHARED)/rt_state.c $(SHARED)/predict.c \
	$(SHARED)/dlgmodal.c ../amiga-client/src/identity.c \
	$(COMMON)/fujibus.c $(COMMON)/fnnet.c

palm:
	mkdir -p build/rsc build/obj
	@for f in $(SOURCES); do \
		$(CC) $(CFLAGS) -c $$f -o build/obj/$$(basename $$f .c).o || exit 1; \
	done
	sh tools/check_segments.sh build/obj/*.o
	$(CC) $(CFLAGS) -o build/$(APP) build/obj/*.o
	cd build/rsc && rm -f *.bin && pilrc -q -I ../../src -I .. ../../src/$(APP).rcp .
	build-prc -n $(NAME) -c $(CREATOR) -o build/$(APP).prc build/$(APP) build/rsc/*.bin
	m68k-palmos-size build/$(APP)

.PHONY: all install clean palm FORCE
