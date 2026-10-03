# FujiRealm Amiga client: Workbench/Kickstart 1.3 and later, over FujiNet NIO.
#
#   make                        build/FujiRealm (+ .info icon), build/netprobe
#   make SERVER_HOST=my.host    bake another server in (same variables as the
#                               Atari and Lynx clients)
#   make test                   host tests (any C compiler)
#
# Needs bebbo's m68k-amigaos-gcc and a fujinet-nio-workspace checkout for
# fujinet-nio-lib (NIO_WORKSPACE). The protocol, bootstrap, terrain-cache,
# prediction and dialogue code is compiled straight from ../lynx-client/src,
# so both clients always share one copy of it.

-include config.mk

SERVER_HOST ?= fujinet.online
HYBRID_SERVER_PORT ?= 9000
LOGIN_SERVER_PORT ?= 9010
NIO_WORKSPACE ?= $(HOME)/code/FujiBerryNIO/workspace
NIO_LIB ?= $(NIO_WORKSPACE)/repos/fujinet-nio-lib

CC := m68k-amigaos-gcc
HOST_CC ?= cc
SHARED := ../lynx-client/src
ART_JSON := ../lynx-client/art/lynx_tileset.json

SERVER_DEFINES := -D'SERVER_HOST="$(SERVER_HOST)"' \
	-DHYBRID_SERVER_PORT=$(HYBRID_SERVER_PORT) \
	-DLOGIN_SERVER_PORT=$(LOGIN_SERVER_PORT)
# -mcrt=nix13 puts the 1.3 NDK headers first, so a call that needs
# Kickstart 2.0 fails to compile instead of crashing on an A500.
CFLAGS := -std=c99 -Wall -Wextra -O2 -mcpu=68000 -msoft-float -mcrt=nix13 \
	-D__AMIGA__ -Isrc -I$(SHARED) -Ibuild/art -I$(NIO_LIB)/include
LDFLAGS := -mcpu=68000 -msoft-float -mcrt=nix13

AMIGA_SRCS := src/main.c src/net.c src/gfx.c src/input.c src/identity.c \
	src/splash.c
SHARED_SRCS := $(SHARED)/bootstrap.c $(SHARED)/rt_state.c \
	$(SHARED)/predict.c $(SHARED)/dlgmodal.c
OBJS := $(AMIGA_SRCS:src/%.c=build/obj/%.o) \
	$(SHARED_SRCS:$(SHARED)/%.c=build/obj/shared/%.o) build/obj/amiga_art.o
NIO_LIB_FILE := $(NIO_LIB)/build/fujinet-nio-amiga.a
# Every object depends on every header: a struct change must rebuild all of
# them, or objects disagree about the layout (this bit us once).
HEADERS := $(wildcard src/*.h) $(wildcard $(SHARED)/*.h) build/art/amiga_art.h
ENDPOINT_STAMP := build/endpoint-$(subst :,_,$(SERVER_HOST))-$(HYBRID_SERVER_PORT)-$(LOGIN_SERVER_PORT)

all: build/FujiRealm build/FujiRealm.info build/netprobe
	@echo "FujiRealm -> $(SERVER_HOST):$(HYBRID_SERVER_PORT) (login $(LOGIN_SERVER_PORT))"

build/FujiRealm: $(OBJS) $(NIO_LIB_FILE)
	$(CC) -o $@ $(OBJS) $(NIO_LIB_FILE) $(LDFLAGS) -lamiga

build/netprobe: tools/netprobe.c $(NIO_LIB_FILE)
	@mkdir -p build
	$(CC) $(CFLAGS) -o $@ $< $(NIO_LIB_FILE) -lamiga

build/FujiRealm.info: tools/mkicon.py tools/amiga_art.py $(ART_JSON)
	@mkdir -p build
	python3 tools/mkicon.py $@ >/dev/null

# Changing the endpoint must relink, not silently keep the old address.
$(ENDPOINT_STAMP):
	@mkdir -p build
	@rm -f build/endpoint-*
	@touch $@

build/obj/main.o: src/main.c $(ENDPOINT_STAMP) $(HEADERS)
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $(SERVER_DEFINES) -c -o $@ $<

build/obj/%.o: src/%.c $(HEADERS)
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

build/obj/shared/%.o: $(SHARED)/%.c $(HEADERS)
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

build/art/amiga_art.c build/art/amiga_art.h: tools/amiga_art.py $(ART_JSON) \
		../lynx-client/tools/import_lynx_art.py
	python3 tools/amiga_art.py build/art/amiga_art.c build/art/amiga_art.h

build/obj/amiga_art.o: build/art/amiga_art.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

$(NIO_LIB_FILE):
	$(MAKE) -C $(NIO_LIB) amiga

test: build/host-test
	./build/host-test

build/host-test: tests/host_test.c src/identity.c src/identity.h
	@mkdir -p build
	$(HOST_CC) -std=c99 -Wall -Wextra -Werror -Isrc -o $@ tests/host_test.c \
		src/identity.c

clean:
	rm -rf build

.PHONY: all test clean
