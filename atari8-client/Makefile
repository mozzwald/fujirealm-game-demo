MADS ?= mads
RELEASE_DIR ?= ../release
NETSTREAM_HANDLER_BASE ?= 36864
NETSTREAM_INPUT_BUFSIZE ?= 1024
SERVER_HOST ?= localhost
HYBRID_SERVER_PORT ?= 9000
LOGIN_SERVER_PORT ?= 9010
REMOTE_PLAYER_SLOTS ?= 12
# 1: local player drawn with Player/Missile Graphics (PM RAM at $A000).
# 0: local player drawn with the original 2x2 character sprite.
PMG_PLAYER ?= 1

# Set these once in an untracked config.mk instead of passing them every time:
#   cp config.mk.example config.mk
-include config.mk

TOOLS := ../tools
XEX := fujirealm.xex
GAME_XEX := build/fujirealm_game.xex
GAME_LST := build/fujirealm_game.lst
GAME_LAB := build/fujirealm_game.lab
SRC := fujirealm.asm
ART_INC := generated/fujirealm_art.inc
PM_ART_INC := generated/fujirealm_pm_art.inc
CHARSETTER_BASE := art/fujirealm_charsetter
CHARSETTER_PROJECT ?= $(CHARSETTER_BASE).json
CHARSETTER_FONT ?= $(CHARSETTER_BASE).fnt
SERVER_HOST_INC := generated/server_host_default.inc
BUILD_OPTIONS_INC := generated/build_options.inc
REMOTE_PLAYER_ARRAYS_INC := generated/remote_player_arrays.inc
ART_FILE ?= art/fujirealm_tiles.map
NETSTREAM_SRC := netstream/src/netstream.s
NETSTREAM_INC := netstream/src/include
NETSTREAM_HANDLER := netstream/NSENGINE.OBX
NETSTREAM_LST := netstream/NSENGINE.lst
NETSTREAM_LAB := netstream/NSENGINE.lab
DIR2ATR ?= dir2atr
ATR := fujirealm.atr
ATR_DOS ?= MyPicoDos406N
ATR_STAGING := build/atr
ATR_GAME_FILE := FUJIREAL.XEX

.PHONY: all clean copy-release copy-nettest export-art import-art \
	export-charsetter-art import-charsetter-art check-charsetter-art \
	netstream-handler atr nettest endpoint FORCE

all: $(XEX)

build generated:
	mkdir -p $@

endpoint:
	@printf 'server: %s  realtime port %s  login port %s\n' \
		'$(SERVER_HOST)' '$(HYBRID_SERVER_PORT)' '$(LOGIN_SERVER_PORT)'

$(SERVER_HOST_INC): FORCE | generated
	python3 $(TOOLS)/write_server_host_default.py "$(SERVER_HOST)" "$(HYBRID_SERVER_PORT)" "$(LOGIN_SERVER_PORT)" $@

$(BUILD_OPTIONS_INC) $(REMOTE_PLAYER_ARRAYS_INC): FORCE | generated
	python3 $(TOOLS)/write_remote_player_options.py "$(REMOTE_PLAYER_SLOTS)" "$(BUILD_OPTIONS_INC)" "$(REMOTE_PLAYER_ARRAYS_INC)" "$(PMG_PLAYER)"

# The tile-editor project is the art source of truth, so the assembly include
# is derived rather than checked in -- a fresh clone builds without first
# having to run an art command by hand.
# Depends on the importer as well as the project: a change to how the art is
# converted has to regenerate the include, or a stale one silently survives.
$(ART_INC) $(PM_ART_INC): $(CHARSETTER_PROJECT) $(TOOLS)/import_charsetter.py $(TOOLS)/charsetter.py | generated
	python3 $(TOOLS)/import_charsetter.py $(CHARSETTER_PROJECT) \
		--output $(ART_INC) --pm-output $(PM_ART_INC)

$(GAME_XEX): $(SRC) $(ART_INC) $(PM_ART_INC) $(SERVER_HOST_INC) $(BUILD_OPTIONS_INC) $(REMOTE_PLAYER_ARRAYS_INC) | build
	$(MADS) $(SRC) -l:$(GAME_LST) -t:$(GAME_LAB) -o:$(GAME_XEX)

netstream:
	mkdir -p $@

# Vendored Altirra-derived handler; see netstream/UPSTREAM.md. The handler's
# own $2800 default overlaps the game's main segment, hence BASEADDR $9000.
$(NETSTREAM_HANDLER): $(NETSTREAM_SRC) | netstream
	$(MADS) $(NETSTREAM_SRC) \
		-i:$(NETSTREAM_INC) \
		-d:BASEADDR=$(NETSTREAM_HANDLER_BASE) \
		-d:INPUT_BUFSIZE=$(NETSTREAM_INPUT_BUFSIZE) \
		-d:HIBUILD=0 -s -p -l:$(NETSTREAM_LST) -t:$(NETSTREAM_LAB) -o:$@

netstream-handler: $(NETSTREAM_HANDLER)

$(XEX): $(NETSTREAM_HANDLER) $(GAME_XEX)
	python3 $(TOOLS)/combine_xex.py -o $(XEX) $(NETSTREAM_HANDLER) $(GAME_XEX)
	@$(MAKE) --no-print-directory endpoint

# Standalone serial-integrity test client (links the same handler). Pairs
# with tools/serial_test_server.py. Build: make nettest SERVER_HOST=<ip>
NETTEST_SRC := nettest/nettest_client.asm
NETTEST_GAME := nettest/nettest_client.xex
NETTEST_XEX := nettest/nettest.xex

$(NETTEST_GAME): $(NETTEST_SRC) $(SERVER_HOST_INC)
	$(MADS) $(NETTEST_SRC) -l:nettest/nettest_client.lst -o:$(NETTEST_GAME)

$(NETTEST_XEX): $(NETSTREAM_HANDLER) $(NETTEST_GAME)
	python3 $(TOOLS)/combine_xex.py -o $(NETTEST_XEX) $(NETSTREAM_HANDLER) $(NETTEST_GAME)

nettest: $(NETTEST_XEX)

copy-nettest: $(NETTEST_XEX)
	install -d $(RELEASE_DIR)
	cp $(NETTEST_XEX) $(RELEASE_DIR)/nettest.xex

atr: $(ATR)

# Full MyPicoDOS 4.06 with highspeed SIO off and autorun enabled. MyPicoDOS
# disables BASIC before launching the XEX on XL/XE, so no OPTION hold is
# needed at boot. MyPicoDOS is separately licensed -- see THIRD-PARTY-NOTICES.md.
$(ATR): $(XEX)
	rm -rf $(ATR_STAGING)
	mkdir -p $(ATR_STAGING)
	cp $(XEX) $(ATR_STAGING)/$(ATR_GAME_FILE)
	$(DIR2ATR) -a -b $(ATR_DOS) $@ $(ATR_STAGING)
	rm -rf $(ATR_STAGING)

copy-release: $(XEX) $(ATR) $(NETSTREAM_HANDLER)
	install -d $(RELEASE_DIR)
	cp $(XEX) $(RELEASE_DIR)/fujirealm.xex
	cp $(ATR) $(RELEASE_DIR)/fujirealm.atr
	cp $(NETSTREAM_HANDLER) $(RELEASE_DIR)/

clean:
	rm -f $(XEX)
	rm -f $(ATR)
	rm -f $(NETSTREAM_HANDLER)
	rm -f $(NETSTREAM_LST) $(NETSTREAM_LAB)
	rm -f $(NETTEST_GAME) $(NETTEST_XEX) nettest/nettest_client.lst
	rm -rf build generated

# --- art pipeline -----------------------------------------------------------
#
# The tile editor (tools/tile-editor/index.html) edits
# art/fujirealm_charsetter.json, which `make` turns into the assembly include.
# The .map targets are an alternative route through the EnvisionPC tile-mode
# format, kept for interoperability with other Atari art tools.

export-art:
	python3 $(TOOLS)/export_tile_map.py --source $(SRC) --output $(ART_FILE)

import-art:
	python3 $(TOOLS)/import_tile_map.py $(ART_FILE) --source $(SRC) --output $(ART_INC)

# A bootstrap/recovery operation: this intentionally overwrites both editable
# tile-editor assets with the art currently assembled into the game source.
export-charsetter-art:
	python3 $(TOOLS)/export_charsetter.py --source $(SRC) --project $(CHARSETTER_PROJECT) --font $(CHARSETTER_FONT) --force

import-charsetter-art: $(ART_INC)

check-charsetter-art:
	python3 $(TOOLS)/import_charsetter.py $(CHARSETTER_PROJECT) --check
