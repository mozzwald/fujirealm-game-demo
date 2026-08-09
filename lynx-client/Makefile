TARGET := fujirealm.lnx
SRC := src/main.c src/bootstrap.c src/rt_state.c src/predict.c src/render.c \
	src/blit.s src/hudtext.c src/dlgmodal.c art/lynx_art.c
HEADERS := src/bootstrap.h src/rt_state.h src/predict.h src/render.h \
	src/hudtext.h src/dlgmodal.h art/lynx_art.h
HOST_SRC := tools/host_tests.c src/bootstrap.c src/rt_state.c src/predict.c \
	src/hudtext.c src/dlgmodal.c art/lynx_art.c
HOST_TEST := build/host_tests
# render.c is Lynx-only, so it needs the cc65 header stubs and a couple of
# hardware hooks redirected; see tools/host_stubs/README.md.
RENDER_TEST := build/render_tests
RENDER_TEST_SRC := tools/render_tests.c src/render.c src/rt_state.c \
	src/hudtext.c art/lynx_art.c
RENDER_TEST_FLAGS := -Isrc -Itools/host_stubs \
	-include tools/host_stubs/render_test_hooks.h
ART_TOOL := tools/import_lynx_art.py

CL65 ?= cl65
CC ?= cc

CC65_ROOT ?= /usr/share/cc65
MAPFILE := build/fujirealm.map

# Server endpoint, baked into the cart at build time. Same variable names the
# Atari client's Makefile uses:
#
#   make SERVER_HOST=192.168.1.120
#   make SERVER_HOST=myhost.local HYBRID_SERVER_PORT=9000 LOGIN_SERVER_PORT=9010
#
# The token FujiNet caches in its appkey is tagged with the host that issued it,
# so switching hosts re-logs in automatically instead of reusing a token the new
# server has never seen.
# Set these once in an untracked config.mk instead of passing them every time:
#   cp config.mk.example config.mk    # then edit it
# A plain `make` then keeps building for your server rather than silently
# relinking against the default.
-include config.mk

SERVER_HOST ?= localhost
HYBRID_SERVER_PORT ?= 9000
LOGIN_SERVER_PORT ?= 9010
SERVER_DEFINES := -D 'SERVER_HOST="$(SERVER_HOST)"' \
	-D HYBRID_SERVER_PORT=$(HYBRID_SERVER_PORT) \
	-D LOGIN_SERVER_PORT=$(LOGIN_SERVER_PORT)
ENDPOINT := $(SERVER_HOST):$(HYBRID_SERVER_PORT):$(LOGIN_SERVER_PORT)
ENDPOINT_STAMP := build/endpoint.stamp

CFLAGS := -t lynx -O -I $(CC65_ROOT)/include --asm-include-dir $(CC65_ROOT)/asminc -L $(CC65_ROOT)/lib -C src/lynx.cfg -m $(MAPFILE) $(SERVER_DEFINES)

.PHONY: all art check-art clean test lint room endpoint FORCE

all: $(TARGET)

# Make dependencies track files, not variables, so a bare `make SERVER_HOST=...`
# after a previous build would otherwise be a no-op and quietly leave a cart
# pointing at the old server. This stamp holds the endpoint and is rewritten
# only when it actually changes, so it forces exactly the rebuilds it should.
$(ENDPOINT_STAMP): FORCE
	@mkdir -p build
	@printf '%s\n' '$(ENDPOINT)' > $@.new
	@cmp -s $@.new $@ || mv -f $@.new $@
	@rm -f $@.new

endpoint:
	@printf 'server: %s  realtime port %s  login port %s\n' \
		'$(SERVER_HOST)' '$(HYBRID_SERVER_PORT)' '$(LOGIN_SERVER_PORT)'

$(TARGET): $(SRC) $(HEADERS) src/lynx.cfg $(ENDPOINT_STAMP)
	mkdir -p build
	$(CL65) $(CFLAGS) -o $@ $(SRC)
	@$(MAKE) --no-print-directory endpoint
	@$(MAKE) --no-print-directory room

# How much of MAIN is left. Without this the only signal that the segment is
# full is a link error, which says nothing about how close the previous build
# was -- and the framebuffers live outside MAIN (the TGI driver puts them at
# $C038/$E018), so the .lnx size does not tell you either.
#
# MAIN is $0200 .. $0200 + ($BE38 - stack), i.e. it ends at $B837 with the
# default 2K stack; BSS is the last segment loaded into it.
room:
	@awk '/^Segment list:/ { in_list = 1; next } \
	     in_list && $$1 == "BSS" { print strtonum("0x" $$3); exit }' \
	     $(MAPFILE) | \
	  awk '{ end = 0xB837; \
	         printf "MAIN: %d bytes used, %d free (%.1f%%)\n", \
	                $$1 - 0x200, end - $$1, ($$1 - 0x200) * 100.0 / (end - 0x200) }'

$(HOST_TEST): $(HOST_SRC) $(HEADERS)
	mkdir -p build
	$(CC) -std=c99 -Wall -Wextra -Werror -Isrc -o $@ $(HOST_SRC)

$(RENDER_TEST): $(RENDER_TEST_SRC) $(HEADERS) tools/host_stubs/render_test_hooks.h
	mkdir -p build
	$(CC) -std=c99 -Wall -Wextra -Werror $(RENDER_TEST_FLAGS) -o $@ $(RENDER_TEST_SRC)

art:
	python3 $(ART_TOOL)

check-art:
	python3 $(ART_TOOL) --check

test: check-art $(HOST_TEST) $(RENDER_TEST)
	./$(HOST_TEST)
	./$(RENDER_TEST)
	@$(MAKE) --no-print-directory lint

# gcc sees far more than cc65 does, and these two files are Lynx-only so nothing
# else ever type-checks them.
lint:
	@$(CC) -fsyntax-only -O2 -Wall -Wextra -Werror -Isrc -Itools/host_stubs \
		src/render.c
	@$(CC) -fsyntax-only -O2 -Wall -Wextra -Werror -Wno-main -Isrc \
		-Itools/host_stubs $(SERVER_DEFINES) src/main.c
	@echo "lint: ok"

clean:
	rm -rf build $(TARGET) src/*.o *.s
