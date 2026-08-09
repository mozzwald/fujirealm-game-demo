; FujiRealm Demo - Atari 8-bit FujiNet MORPG demo
; Build with: make
;
; A small ANTIC text-mode game using a custom character set. Move the hunter
; with joystick port 1. Stop sick beavers before they destroy the forest.

        org $2000

        icl "generated/build_options.inc"

SDLSTL  = $0230
VDSLST  = $0200
CHBAS   = $02F4
OS_FONT_PAGE = $E0
COLOR0  = $02C4
COLOR1  = $02C5
COLOR2  = $02C6
COLOR3  = $02C7
COLOR4  = $02C8
STICK0  = $0278
STRIG0  = $0284
KEY     = $02FC
RTCLOK  = $0014
ATRACT  = $004D
RANDOM  = $D20A
CONSOL  = $D01F
AUDF1   = $D200
AUDC1   = $D201
AUDF2   = $D202
AUDC2   = $D203
AUDF3   = $D204
AUDC3   = $D205
AUDF4   = $D206
AUDC4   = $D207
AUDCTL  = $D208
SKCTL   = $D20F
SKSTAT  = $D20F
WSYNC   = $D40A
CHBASE  = $D409
DLISTL  = $D402
DLISTH  = $D403
VCOUNT  = $D40B
NMIEN   = $D40E
; CRITIC=1 makes the OS skip the deferred (stage-2) VBI. Stage-2 runs with
; IRQs masked for ~1200-2200 cycles -- 2-4 serial byte times at the
; netstream baud rate -- so on real hardware it eats incoming FujiNet bytes
; whenever a packet burst crosses a VBI (a 64-byte realtime packet takes
; ~20ms on the wire, longer than a frame, so every packet crosses one).
; Holding CRITIC=1 during realtime play keeps the VBI to stage-1 only
; (~300 cycles, under one byte time). Everything stage-2 did for us is
; done directly instead: display list/font via apply_display_now + the
; DLI, colors via sync_colors_hw, joystick via PORTA/TRIG0 hardware
; reads, and KEYDEL zeroed each frame (see main_loop_os_sync).
CRITIC  = $42
KEYDEL  = $02F1
PORTA   = $D300
TRIG0   = $D010
COLPF0  = $D016
COLPF1  = $D017
COLPF2  = $D018
COLPF3  = $D019
COLBK   = $D01A

SCREEN  = $4680
SCREEN_BACK = $4A40
FONT    = $5000
; Phase 57: the cave now shares the overworld FONT page, so $7C00-$8000 (the
; former cave-font copy) is reclaimed as the paged-dialogue code/data region.
DIALOGUE_CODE = $7C00
WORLD   = $6000
WORLD_PENDING = $7000
NET_PACKET_PAYLOAD_BUFFER = $8F00
NET_REALTIME_PACKET_BUFFER = $8E80
; TX packets must be built in their own buffer: net_realtime_packet is a
; stateful RX accumulator (net_rt_rx_index persists across frames while a
; packet trickles in at line rate), so building outgoing packets there
; destroys partially received server packets on real hardware.
NET_REALTIME_TX_PACKET_BUFFER = $8EC0
; Phase 7.6 login/appkey scratch buffers live in the free $8C00 page
; (write-before-read; no init needed) to keep the main $2000 code segment
; below the SCREEN buffer at $4680.
APPKEY_DATA_BUFFER = $8C00
LOGIN_PKT_BUFFER = $8C48
USERNAME_BUFFER = $8C70
TOKEN_BUFFER = $8C90
APPKEY_OPEN_BUFFER = $8CA0
N_STATUS_BUFFER = $8CA8
TOKEN_TMP_BUFFER = $8CB0
TOKEN_BIN_BUFFER = $8CB8
NET_RT_STATE_BUFFER = $8CC0
LOGIN_STATE_BUFFER = $8CD0
SERVER_HOST_BUFFER = $8E00
NETSTREAM_HOST_BUFFER = $8E40
N_DEVICESPEC_BUFFER = $8D00
SFX_CODE = $9A00
NETSTREAM_HANDLER_BASE = $9000
NETSTREAM_BEGIN_STREAM = NETSTREAM_HANDLER_BASE+0
NETSTREAM_END_STREAM = NETSTREAM_HANDLER_BASE+3
NETSTREAM_SEND_BYTE = NETSTREAM_HANDLER_BASE+12
NETSTREAM_RECV_BYTE = NETSTREAM_HANDLER_BASE+15
NETSTREAM_BYTES_AVAIL = NETSTREAM_HANDLER_BASE+18
NETSTREAM_GET_STATUS = NETSTREAM_HANDLER_BASE+21
NETSTREAM_GET_VIDEO_STD = NETSTREAM_HANDLER_BASE+24
NETSTREAM_INIT = NETSTREAM_HANDLER_BASE+27
NETSTREAM_GET_FINAL_FLAGS = NETSTREAM_HANDLER_BASE+30
NETSTREAM_GET_FINAL_AUDF3 = NETSTREAM_HANDLER_BASE+33
NETSTREAM_GET_FINAL_AUDF4 = NETSTREAM_HANDLER_BASE+36
; Clock routing: POKEY has ONE internal serial clock (ch3+4), so full-duplex
; concurrent I/O needs an EXTERNAL clock on one direction to free that timer
; for the other -- both-internal ($03) kills TX (POKEY can't transmit while
; async receive resyncs the shared clock). External RX ($0B) worked but the
; high-volume downlink suffered CKI clock/data phase corruption.
; This mode ($07) flips the roles: RX internal async (clean, per-byte resync)
; on the high-volume downlink, TX external clock on the low-volume, recoverable
; uplink. Still full-duplex (RX uses ch3+4, TX uses external CKI -- no
; contention). Bit 2 ($04) = TX external; bit 3 clear = RX internal.
NETSTREAM_FLAGS = $07        ; TCP + REGISTER + TX external clock, RX internal
NETSTREAM_REALTIME_FLAGS = NETSTREAM_FLAGS ; Same clock mode for realtime reconnects
NETSTREAM_BAUD_DEFAULT = 31250
NETSTREAM_PROTOCOL_VERSION = 1
NETSTREAM_PROBE_BYTE = $42
NET_PACKET_MAGIC = $BF
NET_PKT_HELLO = $01
NET_PKT_INPUT = $02
NET_PKT_WINDOW = $80
NET_PKT_WELCOME = $81
NET_PKT_SNAPSHOT = $82
NET_INPUT_PAYLOAD_LEN = 7
NET_HELLO_PAYLOAD_LEN = 7
NET_SNAPSHOT_PAYLOAD_LEN = 23
NET_WINDOW_HEAD_LEN = 12
NET_PACKET_MAX_PAYLOAD = 255
NET_REALTIME_MAGIC = $AD
NET_REALTIME_VERSION = 2
; Realtime v3: COBS-framed (zero delimiter), CRC-16/CCITT-FALSE protected.
; Raw frame keeps the v2 header offsets (type +2, status +3, seq +4/5,
; payload +6); the magic byte became the payload length.
NET_REALTIME_V3_VERSION = 3
NET_REALTIME_V3_HEAD_BYTES = 6
NET_REALTIME_V3_MAX_PAYLOAD = 54
NET_REALTIME_SMALL_PACKET_BYTES = 32
NET_REALTIME_SMALL_CHECKSUM_OFFSET = 30
NET_REALTIME_PACKET_BYTES = 64
NET_REALTIME_CHECKSUM_OFFSET = 62
NET_REALTIME_PATTERN = $5A
NET_REALTIME_STALE_TIMEOUT = 180
ENABLE_DIRTY_CELL_REDRAW = 0
ENABLE_WORLDSTATE_PARTIAL = 1
NET_RT_PLAYER_STATE = 1
NET_RT_WORLD_STATE = 2
NET_RT_TERRAIN_EDGE = 3
NET_RT_BYE = 4
NET_RT_MAP_CHANGE = 5
NET_RT_ENTITY_DELTA = 6
NET_RT_HUD_UPDATE = 7
NET_RT_MESSAGE = 8
NET_RT_QUEST_UPDATE = 9
NET_RT_INVENTORY = 10
NET_RT_RESPAWN = 11
NET_RT_PLAYER_COMMAND = 12
NET_RT_AUTH = 13
NET_RT_REMOTE_PLAYERS = 14
NET_RT_RESYNC_REQUEST = 15
NET_RT_WINDOW_ROW = 16
NET_RT_ITEM_DROPS = 17
NET_RT_MAP_SUMMARY = 18
NET_RT_MAP_READY = 19
NET_RT_WINDOW_COMMIT = 20
NET_RT_CACHE_STEP_ACK = 21
NET_RT_WINDOW_COMMIT_ACK = 22
NET_RT_NET_STATS = 23
; Phase 40: TERRAIN_EDGE carries a 16-bit cache-step revision in its two
; formerly reserved payload bytes.
NET_RT_TERRAIN_REV_LO_OFFSET = 10
NET_RT_TERRAIN_REV_HI_OFFSET = 11
NET_RT_TYPE_COUNT = 19
NET_RT_MAP_SUMMARY_MAP_ID_OFFSET = 6
NET_RT_MAP_SUMMARY_ORIGIN_X_OFFSET = 7
NET_RT_MAP_SUMMARY_ORIGIN_Y_OFFSET = 8
NET_RT_MAP_SUMMARY_WIDTH_OFFSET = 9
NET_RT_MAP_SUMMARY_HEIGHT_OFFSET = 10
NET_RT_MAP_SUMMARY_CELLS_OFFSET = 12
MAP_SUMMARY_CELL_COUNT = 48
MAP_SUMMARY_W = 8
MAP_SUMMARY_H = 6
MAP_CELL_VISITED = $10
MAP_CELL_CURRENT = $20
MAP_CELL_MARKER_MASK = $C0
MAP_CELL_MARKER_TOWN = $40
MAP_CELL_MARKER_GRAVE = $80
MAP_CELL_MARKER_CAVE = $C0
NET_RT_AUTH_TOKEN_OFFSET = 6
NET_RT_REMOTE_COUNT_OFFSET = 3
NET_RT_REMOTE_PAYLOAD_OFFSET = 6
NET_RT_ITEM_COUNT_OFFSET = 3
NET_RT_ITEM_PAYLOAD_OFFSET = 6
NET_MAX_ITEM_DROPS = 4
NET_RT_MESSAGE_ID_OFFSET = 6
NET_RT_MESSAGE_TEXT_LEN_OFFSET = 7
NET_RT_MESSAGE_TEXT_OFFSET = 8
NET_RT_QUEST_ID_OFFSET = 6
NET_RT_QUEST_STATE_OFFSET = 7
NET_RT_QUEST_TEXT_LEN_OFFSET = 8
NET_RT_QUEST_TEXT_OFFSET = 9
; Phase 57: server-driven paged dialogue modal.
NET_RT_DIALOGUE_PAGE = 24
NET_RT_DLG_SPEAKER_OFFSET = 7
NET_RT_DLG_PAGE_IDX_OFFSET = 8
NET_RT_DLG_PAGE_CNT_OFFSET = 9
NET_RT_DLG_FLAGS_OFFSET = 10
NET_RT_DLG_CHUNK_IDX_OFFSET = 11
NET_RT_DLG_TEXT_LEN_OFFSET = 12
; Each packet carries one <=47-char chunk; a display page reassembles up to
; DIALOGUE_PAGE_MAX chars from several chunks before it is word-wrapped/shown.
NET_RT_DIALOGUE_CHUNK_MAX = 47
DIALOGUE_PAGE_MAX = 141
DLG_FLAG_QUEST_OFFER = 1
DLG_FLAG_ACK_ONLY = 2
DLG_FLAG_LAST_PAGE = 4
DLG_FLAG_CHUNK_END = 8
; Spare outbound button bit flagging a "decline" ack (matches the server's
; PLAYER_DIALOGUE_DECLINE_BUTTON). NET_BUTTON_FIRE = 1 is the other bit.
NET_BUTTON_DIALOGUE_DECLINE = 2
MODAL_REQ_DIALOGUE = 5
DLG_LEFT_MARGIN = 3
DLG_WRAP_WIDTH = 34
DLG_BODY_ROW = 8
DLG_SPEAKER_ROW = 4
DLG_PROMPT_ROW = 20
DLG_PAGE_ROW = 22
DLG_SHOWN_NONE = $FF
NET_RT_TEXT_MAX_LEN = 39
; HudUpdatePacket layout: hp(6),max_hp(7),level(8),xp(9-10),xp_next(11-12),
; gold(13-14),flags(15),pvp_kills(16-17) -- hp itself still comes from WORLD_STATE
; (player_health), not this packet.
NET_RT_HUD_MAXHP_OFFSET = 7
NET_RT_HUD_LEVEL_OFFSET = 8
NET_RT_HUD_GOLD_LO_OFFSET = 13
NET_RT_HUD_GOLD_HI_OFFSET = 14
NET_RT_HUD_FLAGS_OFFSET = 15
NET_RT_HUD_KILLS_LO_OFFSET = 16
NET_RT_HUD_KILLS_HI_OFFSET = 17
HUD_FLAG_PVP_ENABLED = 1
; RemotePlayerRecord.state bits (remote_alive,x stores the raw byte, not
; just a 0/1 flag -- see netstream_remote_copy_loop).
REMOTE_PLAYER_STATE_PVP_ENABLED = 2
REMOTE_STATE_FIRE_MASK = %00001100
RBULLET_SLOTS = 3
NET_RT_WINDOW_ROW_OX_OFFSET = 6
NET_RT_WINDOW_ROW_OY_OFFSET = 7
NET_RT_WINDOW_ROW_INDEX_OFFSET = 8
NET_RT_WINDOW_ROW_FILL_ID_OFFSET = 9
NET_RT_WINDOW_ROW_TILES_OFFSET = 10
NET_RT_RESYNC_FILL_ID_OFFSET = 13
NET_RT_RESYNC_FLAGS_OFFSET = 14
NET_RT_INVENTORY_COUNT_OFFSET = 6
NET_RT_INVENTORY_GOLD_LO_OFFSET = 7
NET_RT_INVENTORY_GOLD_HI_OFFSET = 8
NET_RT_INVENTORY_SLOT_OFFSET = 9
ITEM_GOLD = 1
ITEM_STICKS = 2
ITEM_WARDEN_KEY = 5
; Frames of fill SILENCE before re-requesting: every staged WINDOW_ROW
; re-stamps net_resync_request_clk, so this measures a stalled/broken fill
; (rows arrive ~6 frames apart while one streams), not time since the last
; request. 45 frames = ~0.75 s NTSC / ~0.9 s PAL.
NET_RESYNC_RETRY_DELAY = 45
; Frames between retries of a pending WINDOW_COMMIT. A commit lost in
; transit would otherwise leave the server waiting forever with all edge
; streaming blocked.
NET_COMMIT_RETRY_DELAY = 30
; Frames between CLIENT_NET_STATS telemetry reports (~4 s NTSC).
NET_STATS_DELAY = 240
; Consecutive silence retries with no row progress before the staged fill
; is declared dead and abandoned (the active cache stays valid); the next
; request then asks the server for a clean fill via flags bit 1.
NET_FILL_RETRY_LIMIT = 3
; RESYNC_REQUEST flags bits (byte 14).
NET_RESYNC_FLAG_FILL_ACTIVE = 1
NET_RESYNC_FLAG_NEW_FILL = 2
NET_MAX_REMOTE_PLAYERS = BUILD_REMOTE_PLAYER_SLOTS
NET_RT_PLAYER_PAYLOAD_OFFSET = 6
NET_RT_WORLD_PAYLOAD_OFFSET = 6
NET_RT_WORLD_CORRECTION_OFFSET = 9
NET_RT_WORLD_ECHO_SEQ_LO_OFFSET = 10
NET_RT_WORLD_ECHO_SEQ_HI_OFFSET = 11
NET_RT_WORLD_TILE_ID_OFFSET = 12
NET_RT_WORLD_TILE_X_OFFSET = 13
NET_RT_WORLD_TILE_Y_OFFSET = 14
NET_RT_WORLD_BEAVER_OFFSET = 15
NET_RT_TERRAIN_ORIGIN_X_OFFSET = 6
NET_RT_TERRAIN_ORIGIN_Y_OFFSET = 7
NET_RT_TERRAIN_WIDTH_OFFSET = 8
NET_RT_TERRAIN_HEIGHT_OFFSET = 9
NET_RT_TERRAIN_TILE_OFFSET = 12
NET_RT_MAP_ID_OFFSET = 6
NET_RT_MAP_SPAWN_X_OFFSET = 7
NET_RT_MAP_SPAWN_Y_OFFSET = 8
NET_RT_MAP_TILESET_OFFSET = 9
NET_RT_MAP_PALETTE_OFFSET = 10
NET_RT_MAP_FLAGS_OFFSET = 11
NET_WINDOW_TILE_OFFSET = 12
NET_WINDOW_W = 32
NET_WINDOW_H = 24
NET_VIEW_MAX_OFFSET_X = 12
NET_VIEW_MAX_OFFSET_Y = 14
NET_MAX_BEAVERS = 6
NET_BUTTON_FIRE = 1
MAP_OVERWORLD = 0
MAP_STARTER_CAVE = 1
TILESET_OVERWORLD = 0
TILESET_CAVE = 1
PALETTE_OVERWORLD = 0
PALETTE_CAVE = 1
; Phase 8 terrain ids shared with server world.py; the blocking ones must
; also be checked in move_if_clear.
TILE_WATER = 11
TILE_BUILDING = 12
TILE_CAVE_ENTRANCE = 13
TILE_CAVE_WALL = 16
TILE_CAVE_EXIT = 17
TILE_FARMER = 37
TILE_GOBLIN_NPC = 38

; --- Phase 7.6: FujiNet AppKey identity + N: device login/resume ---
FUJINET_CREATOR_ID = $3022
FUJINET_APP_ID     = $02
FUJINET_APPKEY_IDENTITY = 0
FUJINET_APPKEY_HOST     = 1

DDEVIC = $0300
DUNIT  = $0301
DCOMND = $0302
DSTATS = $0303
DBUFLO = $0304
DBUFHI = $0305
DBYTLO = $0308
DBYTHI = $0309
DAUX1  = $030A
DAUX2  = $030B
SIOV   = $E459

FUJI_DEVICE = $70
FUJI_UNIT   = $01
FUJICMD_OPEN_APPKEY  = $DC
FUJICMD_READ_APPKEY  = $DD
FUJICMD_WRITE_APPKEY = $DE
FUJICMD_ENABLE_UDPSTREAM = $F0
APPKEY_MODE_READ  = 0
APPKEY_MODE_WRITE = 1

N_DEVICE = $71
N_UNIT   = 1
N_CMD_OPEN   = $4F
N_CMD_STATUS = $53
N_CMD_READ   = $52
N_CMD_WRITE  = $57
N_CMD_CLOSE  = $43
N_OPEN_MODE_RW    = $0C
N_OPEN_TRANS_NONE = $00

CIOV  = $E456
; IOCB1, not IOCB0: IOCB0 is the OS's own screen-editor channel, already
; open to E: at coldstart, and fighting over its open/close state is
; fragile. IOCB1 starts closed, so opening it fresh is unremarkable.
ICCMD = $0352
ICBAL = $0354
ICBAH = $0355
ICBLL = $0358
ICBLH = $0359
ICAX1 = $035A
ICAX2 = $035B
IOCB1_X = $10
CIO_OPEN = $03
CIO_GET_RECORD = $05
CIO_PUT_RECORD = $09
CIO_CLOSE = $0C
; E: (screen editor) needs read+write on the channel even for input-only
; use: GET_RECORD's line editing echoes through the same IOCB internally.
; Opening it read-only ($04) makes the OPEN itself fail on real/emulated OS.
CIO_OPEN_RW = $0C

LOGIN_PKT_LOGIN_REQUEST   = $A0
LOGIN_PKT_LOGIN_RESPONSE  = $A1
LOGIN_PKT_RESUME_REQUEST  = $A2
LOGIN_PKT_RESUME_RESPONSE = $A3
LOGIN_PKT_RENAME_REQUEST  = $A4
LOGIN_PKT_RENAME_RESPONSE = $A5
LOGIN_PKT_BUF_SIZE = 40
LOGIN_STATUS_OK = 0
LOGIN_STATUS_RENAME_TAKEN = 1
LOGIN_STATUS_RENAME_TOKEN_UNKNOWN = 2
USERNAME_MAX_LEN = 10
TOKEN_MAX_LEN = 10
SERVER_HOST_MAX_LEN = 32
server_host_buf = SERVER_HOST_BUFFER
netstream_host = NETSTREAM_HOST_BUFFER
n_devicespec_buf = N_DEVICESPEC_BUFFER

SCREEN_W = 40
SCREEN_H = 23
SCREEN_ROWS = 24
HUD_LINE1_Y = 21
HUD_LINE2_Y = 22
HUD_LINE3_Y = 23
HUD_MESSAGE_TIMEOUT_FRAMES = 1800
HUD_QUEST_DONE_TIMEOUT_FRAMES = 600
WORLD_W = 128
WORLD_H = 96
TILE_CHARS_W = 2
TILE_CHARS_H = 2
CAVE_TILE_TABLE_LEN = 51
VIEW_TILE_W = 20
VIEW_TILE_H = 10
VIEW_SCREEN_W = 40
VIEW_SCREEN_H = 20
VIEW_SEPARATOR_Y = 20
VIEW_MAX_X = 108
VIEW_MAX_Y = 86
SCROLL_LEFT_EDGE = 6
SCROLL_RIGHT_EDGE = 13
SCROLL_TOP_EDGE = 4
SCROLL_BOTTOM_EDGE = 6

GRASS   = 0
PLAYER  = 1
TREE_FULL = 2
HERB    = 3
TREE_DAMAGED = 4
TREE_STUMP = 5
BULLET = 6
BORDER = 7
BEAVER = 8
SNAKE = 9
LOG_SHOT = 10
HEART_FULL = 11
HEART_EMPTY = 12
BEAVER_ICON = 13
STATUS_BLANK = 33
DIGIT0 = 16
OS_HEART = 64
OS_COLON = 26
; OS-font screen codes for the "PvP" HUD indicator: screen_code = ATASCII-32
; for ATASCII 32-95 ('P' is ATASCII 80 -> 48), unchanged for ATASCII 96-127
; ('v' is ATASCII 118, already in that range -> 118). Same convention as
; OS_COLON/OS_HEART and the hud_line_hp/beavers/level label tables below.
OS_P = 48
OS_V = 118
STATUS_B = 26
STATUS_L = 27
STATUS_S = 28
STATUS_COLON = 29
; Phase 14b: new tile-table indices appended after the existing 0-33 range
; (0-13 are real custom art; 14-33 are legacy slots still read above by the
; status/digit HUD and are not safe to repaint).
ITEM_TILE_GOLD = 34
ITEM_TILE_STICKS = 35
GOBLIN = 36
TOWN_NPC = 37
GRIX = 38
ITEM_TILE_WARDEN_KEY = 39
DANIEL = 40
WILHELM = 41
LUCIAN = 42
NERISSA = 43
SLIME_0 = 44
SLIME_1 = 45
BAT_0 = 46
BAT_1 = 47
GORVAK = 48
DEEP_PUMP = 49
PUMP_CONTROLS = 50
WILHELM_WORKING = 51
; Player sprite frames index the dedicated player_sprite_* tables, NOT the
; tile2x2 terrain tables. They used to be tile ids 1/14/15/30/31/32, but
; Phase 8 server terrain ids collide with that range (GRAVE=14 drew as a
; standing player; CAVE_FLOOR=15 blanked the right-facing player sprite).
PLAYER_FRONT_0 = 0
PLAYER_FRONT_1 = 1
PLAYER_RIGHT_0 = 2
PLAYER_RIGHT_1 = 3
PLAYER_LEFT_0 = 4
PLAYER_LEFT_1 = 5
; Remote-player frame indices: base+0 is the idle/frame0 pose, base+1 the
; walk-cycle alternate -- draw_remote_players adds remote_anim,x (0 or 1).
REMOTE_FRONT_0 = 6
REMOTE_FRONT_1 = 7
REMOTE_RIGHT_0 = 8
REMOTE_RIGHT_1 = 9
REMOTE_LEFT_0 = 10
REMOTE_LEFT_1 = 11
; Phase 61 final glyph ownership. Codes 1-32 were legacy mini-art/HUD
; characters; HUD/modal digits now render under the OS font, so the custom
; font slots are dedicated to world art. Glyph 33 remains the separator blank.
; See art/PHASE_61_TILE_ALLOCATION.md.
T2_SLIME_F0_TL = 1
T2_SLIME_F0_TR = 2
T2_SLIME_F1_TL = 3
T2_SLIME_F1_TR = 4
T2_SLIME_BL = 5
T2_SLIME_BR = 6
T2_GORVAK_TL = 7
T2_GORVAK_TR = 8
T2_GORVAK_BL = 9
T2_GORVAK_BR = 10
T2_GRAVE_TL = 14
T2_GRAVE_TR = 15
T2_BAT_F0_TL = 18
T2_BAT_F0_TR = 19
T2_BAT_F0_BL = 20
T2_BAT_F0_BR = 21
T2_BAT_F1_TL = 22
T2_BAT_F1_TR = 23
T2_BAT_F1_BL = 24
T2_BAT_F1_BR = 25
T2_DEEP_PUMP_TL = 26
T2_DEEP_PUMP_TR = 27
T2_DEEP_PUMP_BL = 28
T2_DEEP_PUMP_BR = 29
T2_PUMP_CONTROLS_TL = 30
T2_PUMP_CONTROLS_TR = 31
T2_GRAVE_BL = 32
T2_GRASS_TL = 34
T2_GRASS_TR = 35
T2_GRASS_BL = 36
T2_GRASS_BR = 37
T2_PLAYER_F0_TL = 38
T2_PLAYER_F0_TR = 39
T2_PLAYER_F0_BL = 40
T2_PLAYER_F0_BR = 41
T2_PLAYER_F1_TL = 42
T2_PLAYER_F1_TR = 43
T2_PLAYER_F1_BL = 44
T2_PLAYER_F1_BR = 45
T2_PLAYER_R0_TL = 46
T2_PLAYER_R0_TR = 47
T2_PLAYER_R0_BL = 48
T2_PLAYER_R0_BR = 49
T2_PLAYER_R1_TL = 50
T2_PLAYER_R1_TR = 51
T2_PLAYER_R1_BL = 52
T2_PLAYER_R1_BR = 53
T2_PLAYER_L0_TL = 54
T2_PLAYER_L0_TR = 55
T2_PLAYER_L0_BL = 56
T2_PLAYER_L0_BR = 57
T2_PLAYER_L1_TL = 58
T2_PLAYER_L1_TR = 59
T2_PLAYER_L1_BL = 60
T2_PLAYER_L1_BR = 61
T2_TREE_TL = 62
T2_TREE_TR = 63
T2_TREE_BL = 64
T2_TREE_BR = 65
T2_HERB_TL = 66
T2_HERB_TR = 67
T2_HERB_BL = 68
T2_HERB_BR = 69
T2_TREE_DMG_TL = 70
T2_TREE_DMG_TR = 71
T2_TREE_DMG_BL = 72
T2_TREE_DMG_BR = 73
T2_STUMP_TL = 74
T2_STUMP_TR = 75
T2_STUMP_BL = 76
T2_STUMP_BR = 77
T2_BULLET_TL = 78
T2_BULLET_TR = 79
T2_NERISSA_BR = 80
T2_GRAVE_BR = 81
T2_BORDER_TL = 82
T2_BORDER_TR = 83
T2_BORDER_BL = 84
T2_BORDER_BR = 85
T2_BEAVER_TL = 86
T2_BEAVER_TR = 87
T2_BEAVER_BL = 88
T2_BEAVER_BR = 89
T2_SNAKE_TL = 90
T2_SNAKE_TR = 91
T2_SNAKE_BL = 92
T2_SNAKE_BR = 93
T2_LOG_TL = 94
T2_LOG_TR = 95
T2_LOG_BL = 96
T2_LOG_BR = 97
T2_LOG_FONT = FONT+T2_LOG_TL*8
; Phase 14b item-drop overlay tiles: one character reused for all four
; quadrants each (pure stripe patterns, see generated/fujirealm_art.inc).
T2_ITEM_GOLD = 98
T2_ITEM_STICKS = 99
T2_GOBLIN_TL = 100
T2_GOBLIN_TR = 101
T2_GOBLIN_BL = 102
T2_GOBLIN_BR = 103
T2_FARMER_TL = 104
T2_FARMER_TR = 105
T2_FARMER_BL = 106
T2_FARMER_BR = 107
; Remote players intentionally reuse the six local-player bitmap frames with
; character bit 7 set in player_sprite_*; this is one shared art identity, not
; a second editable logical entity. Slots 108-125 are therefore available for
; dedicated story NPC art.
T2_GRIX_TL = 108
T2_GRIX_TR = 109
T2_GRIX_BL = 110
T2_GRIX_BR = 111
T2_DANIEL_TL = 112
T2_DANIEL_TR = 113
T2_DANIEL_BL = 114
T2_DANIEL_BR = 115
T2_WILHELM_TL = 116
T2_WILHELM_TR = 117
T2_WILHELM_BL = 118
T2_WILHELM_BR = 119
T2_WILHELM_WORK_TR = 83
T2_WILHELM_WORK_BR = 85
T2_LUCIAN_TL = 120
T2_LUCIAN_TR = 121
T2_LUCIAN_BL = 122
T2_LUCIAN_BR = 123
T2_NERISSA_TL = 124
T2_NERISSA_TR = 125
; Warden Key item icon (index 39): one character reused across all four
; quadrants, like ITEM_TILE_GOLD/STICKS.
T2_ITEM_WARDEN_KEY = 126
T2_NERISSA_BL = 127
ENEMY_BEAVER = 1
ENEMY_SNAKE = 2
ENEMY_BAT = 3
ENEMY_SLIME = 4
ENEMY_GOBLIN = 5
ENEMY_GORVAK = 6
DYNAMIC_WILHELM = 7
DYNAMIC_WILHELM_WORKING = 8
ENEMY_KIND_MASK = $7F
ENEMY_HIT_BIT = $80
ENEMY_HIT_FLASH_FRAMES = 8
QUEST_STATE_COMPLETE = 3
MSG_BEAVER_KILLED = 5
MSG_LEVEL_UP = 10
MSG_PLAYER_DIED = 11
MSG_RESPAWN_GRAVE = 12
MSG_RESPAWN_CAVE = 13
MSG_GOBLIN_KILLED = 15
MSG_QUEST_OFFER = 17
MSG_PVP_ARENA_LOCKED = 25
SFX_NONE = 0
SFX_SHOOT = 1
SFX_HURT = 2
SFX_DEATH = 3
SFX_KILL = 4
SFX_LEVELUP = 5
SFX_COUNT = 5
MOVE_DELAY = 5
NET_MOVE_DELAY = 8
NET_MOVE_REPEAT_DELAY = 6
NET_REALTIME_MOVE_DELAY = 1
NET_REALTIME_SEND_DELAY = 4
NET_AUTH_KEEPALIVE_DELAY = 60
BULLET_DELAY = 3
BEAVER_DELAY = 15
; Visual-only bullet range; must match the server's HUNTER_RANGE (game.py)
; so the projectile stops where hits can actually land.
PLAYER_BULLET_RANGE = 6
BEAVER_START_COUNT = 4
BEAVER_MAX_COUNT = 8
; Heart glyph count is a HUD-resolution concept, separate from the
; player's actual max HP (which scales with level and is tracked at
; runtime in player_max_health instead) -- conflating the two used to
; mean hearts stayed full until real HP dropped below 4, no matter how
; high max HP had actually grown.
HEART_COUNT = 6
; Fixed HUD line-1 column layout, so hearts/gold/PvP digits can be repainted
; in place without walking through the labels ahead of them.
HUD_HEARTS_X = 3
HUD_LEVEL_LABEL_X = HUD_HEARTS_X+HEART_COUNT
HUD_LEVEL_DIGITS_X = HUD_LEVEL_LABEL_X+3
HUD_GOLD_X = HUD_LEVEL_DIGITS_X+3
; Literal 3-char "PvP" indicator -- HUD line 1 gets the OS-font DLI switch
; same as lines 2-3 (see OS_P/OS_V), so no custom glyph is needed here.
HUD_PVP_X = HUD_GOLD_X+8
TREE_COUNT = 140
HERB_COUNT = 32
TITLE_LINE_END = $FE
TITLE_END = $FF
KEY_NONE = $FF
KEY_CODE_MASK = $3F
KEY_DOWN_MASK = $04
KEY_W = 46
KEY_A = 63
KEY_S = 62
KEY_D = 58
; Keyboard movement is intentionally one direction key at a time. The Atari
; keyboard path exposes a single confirmed key latch, not a reliable held-key
; bitmap, so WASD rollover is not modeled here; joystick remains preferred.
KEY_SPACE = 33
KEY_RETURN = 12
KEY_I = 13
KEY_ESC = 28
; M is reserved for the Phase 15 map modal request.
KEY_M = 37
KEY_C = 18
; Best-recollection Atari internal keyboard scan code for H -- verify
; in the emulator; if H doesn't open the help screen, this needs fixing.
KEY_H = 57
; Same caveat as KEY_H -- best recollection, verify in the emulator.
KEY_P = 10
; Best-recollection internal scan code for V -- verify on hardware. V
; ("velocity") cycles the walk-speed presets (frames per held-direction
; step) so the movement cadence can be matched to the link's cache-step
; throughput. W is taken by WASD movement.
KEY_V = 16
TRANSITION_DELAY = 180
TITLE_ACTION_HOST = 1
TITLE_ACTION_HELP = 2
TITLE_ACTION_BAUD = 3
TITLE_ACTION_CHANGE_USERNAME = 4
LOGIN_STATUS_USERNAME_TAKEN = 1
USERNAME_PROMPT_NORMAL = 0
USERNAME_PROMPT_TAKEN = 1
TITLE_IDENTITY_NEW = 0
TITLE_IDENTITY_READY = 1
TITLE_IDENTITY_UNAVAILABLE = 2

DIR_UP = 0
DIR_DOWN = 1
DIR_LEFT = 2
DIR_RIGHT = 3
DIR_UP_LEFT = 4
DIR_UP_RIGHT = 5
DIR_DOWN_LEFT = 6
DIR_DOWN_RIGHT = 7

NET_DIR_NONE = 0
NET_DIR_UP = 1
NET_DIR_DOWN = 2
NET_DIR_LEFT = 3
NET_DIR_RIGHT = 4

ptr     = $80
target_x = $82
target_y = $83
screen_bottom_ptr = target_x
; Netstream NS_Init expects cc65 c_sp at $82/$83. Reuse target_x/target_y
; only during connection setup, before gameplay routines need target coords.
netstream_c_sp = target_x
player_x = $84
player_y = $85
lastclk  = $86
aim_dir  = $87
fire_latch = $88
scroll_col = $89
bullet_x = $8A
bullet_y = $8B
bullet_dir = $8C
bullet_clk = $8D
bullet_active = $8E
bullet_drawn = $8F
view_x = $90
view_y = $91
old_view_x = $92
old_view_y = $93
screen_x = $94
screen_y = $95
loop_x = $96
loop_y = $97
wptr = $98
strig0_repeat_latch = $99
row_counter = $9A
work = $9B
bullet_steps = $9C
scroll_row = $A1
input_stick_raw = $A2

; v4 2x2 tile renderer notes:
; - player_x/player_y, enemy_x/enemy_y, bullet_x/bullet_y, target_x/target_y,
;   and view_x/view_y remain world-cell coordinates.
; - screen_x/screen_y are screen-character coordinates when writing SCREEN.
; - visible logical tile coordinate (lx, ly) maps to screen char (lx*2, ly*2).
; - rows 0-21 are the 20x11 logical gameplay viewport; row 22 is a separator;
;   row 23 remains the one-character-high status row.

start
        jsr disable_attract_mode
        jsr server_host_init
        lda #0
        sta netstream_baud_index
        jsr netstream_apply_baud
title_start
        jsr setup_title_screen
        jsr wait_title_action
        beq attempt_connection
        cmp #TITLE_ACTION_HOST
        beq title_server_host
        cmp #TITLE_ACTION_BAUD
        beq title_baud_select
        cmp #TITLE_ACTION_CHANGE_USERNAME
        beq title_change_username
        jsr show_help_modal
        jmp title_start
title_server_host
        jsr server_host_prompt_screen
        bcc attempt_connection
        jmp title_start
title_baud_select
        jsr netstream_cycle_baud
        jmp title_start
title_change_username
        lda title_identity_state
        cmp #TITLE_IDENTITY_READY
        bne attempt_connection
        jsr title_change_username_flow
        bcs connection_failed
        jmp title_start
attempt_connection
        jsr appkey_check_and_login
        bcs connection_failed
        jsr netstream_smoke_test
        jsr netstream_game_connect
        lda network_enabled
        beq connection_failed
        lda network_realtime_enabled
        bne connection_ok
connection_failed
        jsr show_connection_failed_screen
        jmp attempt_connection
connection_ok
        jsr netstream_wait_for_initial_art
        jsr init_new_game
main_loop
        jsr disable_attract_mode
        jsr main_loop_os_sync
        lda network_realtime_enabled
        bne main_loop_network_realtime
; Realtime went away without a handled event (e.g. a failed keepalive
; send). Spinning here would hang the game silently; route to the
; connection-failed retry gate instead.
        jmp connection_failed
main_loop_network_realtime
        jsr netstream_recv_realtime_packets
        jsr netstream_watchdog_check
        bcc main_loop_watchdog_ok
        jmp connection_failed
main_loop_watchdog_ok
        lda net_map_change_pending
        beq main_loop_no_map_change
        jsr handle_map_change
        jmp main_loop
main_loop_no_map_change
; Terrain desync: request a fresh window in-band instead of tearing down
; the netstream (the SIO reconnect costs ~2 s of baud hunting and
; bootstrap). The staleness watchdog remains the fallback if the stream is
; truly dead.
        lda net_terrain_desync
        beq main_loop_no_desync
        lda #0
        sta net_terrain_desync
        jsr netstream_send_resync_request
        jmp main_loop
main_loop_no_desync
        jsr netstream_resync_retry_check
main_loop_no_resync_retry
; Movement is frozen while a map fill streams (the terrain cache is a
; mix of maps); PLAYER_STATE keepalives continue below.
        lda net_map_fill_pending
        bne main_loop_controls_done
        jsr read_controls_realtime
        lda net_modal_request
        cmp #KEY_ESC
        beq return_to_title_menu
        cmp #1
        bne main_loop_check_map_modal
        jsr show_inventory_modal
        jmp main_loop_controls_done
main_loop_check_map_modal
        cmp #2
        bne main_loop_check_quest_modal
        jsr show_map_modal
        jmp main_loop_controls_done
main_loop_check_quest_modal
        cmp #3
        bne main_loop_check_help_modal
        jsr show_quest_offer_modal
        jmp main_loop_controls_done
main_loop_check_help_modal
        cmp #4
        bne main_loop_check_dialogue_modal
        jsr show_help_modal
        jmp main_loop_controls_done
main_loop_check_dialogue_modal
        cmp #MODAL_REQ_DIALOGUE
        bne main_loop_controls_done
        jsr show_dialogue_modal
main_loop_controls_done
        jsr netstream_service_realtime_io
        jsr update_network_bullet_fast
        jsr update_remote_bullets
        jsr apply_pending_player_correction
        jsr update_enemy_visuals
        jsr draw_realtime_frame
        jsr sfx_update
        jmp main_loop

; Ending concurrent I/O alone (NETSTREAM_END_STREAM) is Atari-side only --
; it restores normal SIO framing but never tells FujiNet to close its TCP
; session, so netstreamActive stays set on the firmware and a later
; reconnect attempt finds the device already "streaming" and fails without
; a FujiNet/Atari reset. Sending FUJICMD_ENABLE_UDPSTREAM ($70/$F0) with a
; "STOP" host, same as the normal connect path uses to start it, makes the
; firmware call sio_disable_netstream() and actually tear the session down.
; Must run after NETSTREAM_END_STREAM: concurrent mode owns the serial IRQs
; and asserts the motor line for the whole session, so a normal SIOV
; command frame can't get through until concurrent mode has been exited.
return_to_title_menu
        jsr NETSTREAM_END_STREAM
        jsr netstream_send_stop
        jmp title_start

setup_title_screen
        jsr init_sound
        jsr init_screen_buffers
; The generated runtime tile2x2 tables still carry the pre-Phase-8 id
; layout (player chars at indices 14/15); copy the corrected overworld
; tables over them before anything draws terrain.
        jsr copy_overworld_tile_tables
        lda #MAP_OVERWORLD
        sta current_map_id
        lda #TILESET_OVERWORLD
        sta current_tileset_id
        lda #PALETTE_OVERWORLD
        sta current_palette_id
        lda #>FONT
        sta current_font_page
        jsr set_text_palette
        jsr clear_screen
        jsr draw_title_text
; draw_title_baud deliberately NOT called here -- it paints the rate digits
; at row 19 col 20, under a label this screen no longer has. The
; connection-failed screen still calls it, where the label remains.
        jsr title_refresh_identity
        jsr draw_title_identity
        jsr wait_frame_tick
        ldx #<display_list_text
        ldy #>display_list_text
        lda #OS_FONT_PAGE
        jsr apply_display_now
        rts

init_new_game
        jsr init_screen_buffers
        jsr wait_frame_tick
        ldx #<display_list_game
        ldy #>display_list_game
        lda #>FONT
        jsr apply_display_now
        jsr install_hud_dli

; Apply whatever art netstream_wait_for_initial_art already resolved
; (Overworld defaults, or the just-received MAP_CHANGE's cave/PvP art)
; instead of unconditionally hardcoding the Overworld palette here. The
; tile2x2 tables need no matching apply_tileset call: cave and overworld
; currently alias the same table (see copy_cave_tile_tables), and title
; screen setup already primed it.
        jsr apply_palette

        jsr disable_network_sound_state
        lda #1
        sta level_num
        lda #NET_MAX_BEAVERS
        sta active_beaver_count
        jsr init_level
        rts

set_text_palette
        lda #$00
        sta COLOR1
        lda #$c8
        sta COLOR2
        lda #$00
        sta COLOR4
; Fall through to the hardware copy: with CRITIC=1 the stage-2 VBI that
; normally applies the COLOR shadows never runs (see the CRITIC note).
        jmp sync_colors_hw

set_game_palette
; ANTIC 4 glyph pixel pairs: 00=COLOR4, 01=COLOR0, 10=COLOR1,
; 11=COLOR2 normally. With bit 7 set in the screen code, 11 selects COLOR3.
; Current visual roles: COLOR4 dark forest, COLOR0 foliage, COLOR1 bark/log,
; COLOR2 hunter/light UI, COLOR3 herbs/hearts/accent tiles.
        lda #$c8
        sta COLOR0
        lda #$24
        sta COLOR1
        lda #$0e
        sta COLOR2
        lda #$4a
        sta COLOR3
        lda #$00
        sta COLOR4
        jmp sync_colors_hw

init_screen_buffers
        lda #<SCREEN
        sta active_screen_lo
        lda #>SCREEN
        sta active_screen_hi
        lda #<SCREEN_BACK
        sta back_screen_lo
        lda #>SCREEN_BACK
        sta back_screen_hi
        jsr update_display_lms
        rts

update_display_lms
        lda active_screen_lo
        sta game_display_lms_lo
        lda active_screen_hi
        sta game_display_lms_hi
        rts

; hud_clock_lo/hi: a 16-bit frame counter this routine maintains itself,
; incremented exactly once per confirmed frame boundary. HUD timeouts key
; off this instead of RTCLOK+1 -- RTCLOK ($14) is confirmed (by this very
; wait loop) to tick once per frame, but nothing here establishes that the
; byte at $15 is a meaningful "next significant byte" of that count rather
; than an unrelated OS/system variable, so treating (RTCLOK,RTCLOK+1) as a
; trustworthy 16-bit pair for a 25+ second timeout is not safe to assume.
wait_frame_tick
        lda RTCLOK
wait_frame_tick_loop
        cmp RTCLOK
        beq wait_frame_tick_loop
        inc hud_clock_lo
        bne wait_frame_tick_done
        inc hud_clock_hi
wait_frame_tick_done
        rts

swap_screen_buffers
        lda active_screen_lo
        pha
        lda back_screen_lo
        sta active_screen_lo
        pla
        sta back_screen_lo
        lda active_screen_hi
        pha
        lda back_screen_hi
        sta active_screen_hi
        pla
        sta back_screen_hi
        rts

init_level
        lda #>FONT
        sta CHBAS
        jsr clear_screen
        lda #10
        sta player_x
        sta player_y
        lda net_window_origin_x
        sta view_x
        lda net_window_origin_y
        sta view_y
        lda #DIR_RIGHT
        sta aim_dir
        sta last_cardinal_aim
        lda #0
        sta fire_latch
        sta strig0_repeat_latch
        sta lastclk
        sta bullet_active
        sta bullet_drawn
        sta bullet_steps
        jsr clear_remote_bullets
        sta forest_damage_count
        sta player_anim
        sta net_screen_dirty
        sta net_scroll_dirty
        sta status_dirty
        sta net_player_correction_pending
        sta net_last_move_clk
        sta net_move_repeat_clk
        sta net_move_repeat_dir
        sta net_predicted_move_pending
        sta net_predicted_move_seq_lo
        sta net_predicted_move_seq_hi
        sta net_prediction_send_pending
        sta net_world_changed
        sta net_modal_request
        sta inventory_gold_lo
        sta inventory_gold_hi
        sta inventory_sticks_count
        sta inventory_slot_count
        sta hud_message_id
        sta hud_quest_state
        sta hud_quest_done_hidden
        lda #TITLE_LINE_END
        sta hud_message_text
        sta hud_quest_text
        lda #KEY_NONE
        sta net_key_repeat_latch
        lda #$0f
        sta net_last_move_raw
        lda active_beaver_count
        sta beavers_left
        lda #12
        sta player_health
        sta player_max_health
        lda player_x
        sta old_player_x
        lda player_y
        sta old_player_y
        jsr net_clear_enemy_tiles
        jsr draw_viewport
        jsr draw_player
        jsr draw_status_full
        rts

clear_screen
        lda #0
        sta screen_y
clear_screen_row
        lda #0
        sta screen_x
        jsr screen_cell_ptr
        ldy #0
        lda #0
clear_screen_byte
        sta (ptr),y
        iny
        cpy #SCREEN_W
        bne clear_screen_byte
        inc screen_y
        lda screen_y
        cmp #SCREEN_ROWS
        bne clear_screen_row
        rts

draw_title_text
        lda #<title_lines
        sta wptr
        lda #>title_lines
        sta wptr+1
draw_text_lines
title_line_loop
        ldy #0
        lda (wptr),y
        cmp #TITLE_END
        beq title_text_done
        sta screen_y
        iny
        lda (wptr),y
        sta screen_x
        jsr advance_title_ptr_two
        jsr screen_cell_ptr
        ldy #0
title_char_loop
        lda (wptr),y
        cmp #TITLE_LINE_END
        beq title_line_done
        sta (ptr),y
        iny
        jmp title_char_loop
title_line_done
        tya
        clc
        adc #1
        jsr advance_title_ptr_a
        jmp title_line_loop
title_text_done
        rts

advance_title_ptr_two
        lda #2
advance_title_ptr_a
        clc
        adc wptr
        sta wptr
        bcc title_ptr_done
        inc wptr+1
title_ptr_done
        rts

wait_transition_delay
        lda RTCLOK
        sta transition_start_clk
transition_delay_loop
        lda RTCLOK
        sec
        sbc transition_start_clk
        cmp #TRANSITION_DELAY
        bcc transition_delay_loop
        rts

; ============================================================
; Phase 13.5: configurable server hostname.
; AppKey key 1 stores the ASCII hostname. Missing/failed reads keep
; the default localhost target. Both N: login and Netstream realtime
; targets are patched before any connection attempt.
; ============================================================

server_host_init
        jsr server_host_set_default
        jsr appkey_read_server_host
        jsr server_host_patch_targets
        rts

server_host_set_default
        lda #SERVER_HOST_DEFAULT_LEN
        sta server_host_len
        ldx #0
server_host_set_default_copy
        cpx #SERVER_HOST_DEFAULT_LEN
        beq server_host_set_default_done
        lda server_host_default,x
        sta server_host_buf,x
        inx
        jmp server_host_set_default_copy
server_host_set_default_done
        rts

appkey_read_server_host
        lda #FUJINET_APPKEY_HOST
        sta appkey_key_id
        jsr appkey_open_read
        cpy #1
        bne appkey_read_server_host_done
        jsr appkey_read
        cpy #1
        bne appkey_read_server_host_done
        lda appkey_data_buf+0
        sta appkey_count
        ora appkey_data_buf+1
        beq appkey_read_server_host_done
        lda appkey_count
        cmp #SERVER_HOST_MAX_LEN+1
        bcs appkey_read_server_host_done
        sta server_host_len
        ldx #0
appkey_read_server_host_copy
        cpx server_host_len
        beq appkey_read_server_host_done
        lda appkey_data_buf+2,x
        sta server_host_buf,x
        inx
        jmp appkey_read_server_host_copy
appkey_read_server_host_done
        rts

appkey_store_server_host
        ldx #0
appkey_store_server_host_copy
        cpx server_host_len
        beq appkey_store_server_host_copy_done
        lda server_host_buf,x
        sta appkey_data_buf+2,x
        inx
        jmp appkey_store_server_host_copy
appkey_store_server_host_copy_done
        stx appkey_write_len
        lda #FUJINET_APPKEY_HOST
        sta appkey_key_id
        jsr appkey_open_write
        cpy #1
        bne appkey_store_server_host_fail
        jsr appkey_write
        cpy #1
        bne appkey_store_server_host_fail
        clc
        rts
appkey_store_server_host_fail
        sec
        rts

server_host_patch_targets
        ldx #0
server_host_patch_netstream
        cpx server_host_len
        beq server_host_patch_netstream_done
        lda server_host_buf,x
        sta netstream_host,x
        inx
        jmp server_host_patch_netstream
server_host_patch_netstream_done
        lda #0
        sta netstream_host,x
        ldx #0
        ldy #0
server_host_patch_prefix
        cpy #N_DEVICESPEC_PREFIX_LEN
        beq server_host_patch_host_start
        lda n_devicespec_prefix,y
        sta n_devicespec_buf,x
        inx
        iny
        jmp server_host_patch_prefix
server_host_patch_host_start
        ldy #0
server_host_patch_host
        cpy server_host_len
        beq server_host_patch_suffix_start
        lda server_host_buf,y
        sta n_devicespec_buf,x
        inx
        iny
        jmp server_host_patch_host
server_host_patch_suffix_start
        ldy #0
server_host_patch_suffix
        cpy #N_DEVICESPEC_SUFFIX_LEN
        beq server_host_patch_done
        lda n_devicespec_suffix,y
        sta n_devicespec_buf,x
        inx
        iny
        jmp server_host_patch_suffix
server_host_patch_done
        lda #0
        sta n_devicespec_buf,x
        rts

server_host_prompt_screen
        jsr cio_open_e
        bcs server_host_prompt_fail
        jsr cio_put_host_prompt
        bcs server_host_prompt_close_fail
        jsr cio_get_server_host
        lda #0
        rol
        sta cio_get_failed
        jsr cio_close_e
        lda cio_get_failed
        bne server_host_prompt_fail
        lda server_host_input_len
        beq server_host_prompt_keep
        jsr server_host_copy_input
        jsr appkey_store_server_host
        bcs server_host_prompt_fail
        jsr server_host_patch_targets
server_host_prompt_keep
        clc
        rts
server_host_prompt_close_fail
        jsr cio_close_e
server_host_prompt_fail
        sec
        rts

server_host_copy_input
        lda server_host_input_len
        sta server_host_len
        ldx #0
server_host_copy_input_loop
        cpx server_host_len
        beq server_host_copy_input_done
        lda appkey_data_buf+2,x
        sta server_host_buf,x
        inx
        jmp server_host_copy_input_loop
server_host_copy_input_done
        rts

; ============================================================
; Phase 7.6: AppKey identity + N: device login/resume exchange.
; Runs once between title action and netstream_smoke_test on
; every connection attempt. Carry set on return = show the
; connection-failed screen and retry from the top; carry clear =
; token_bin holds the 32-bit token to send in HELLO.
; ============================================================

appkey_check_and_login
        jsr appkey_check_and_read
        lda #USERNAME_PROMPT_NORMAL
        sta username_prompt_mode
        lda has_identity
        bne appkey_login_resume
appkey_login_prompt
        jsr username_prompt_screen
        bcs appkey_login_fail
        lda username_len
        beq appkey_login_prompt
        jsr n_login_open
        bcs appkey_login_fail
        jsr login_build_login_request
        jsr login_checksum_and_send
        bcs appkey_login_close_fail
        jsr login_recv_response
        bcs appkey_login_close_fail
        jsr n_close
        jsr login_parse_login_response
        bcs appkey_login_fail
        lda login_status
        beq appkey_login_prompt_ok
        cmp #LOGIN_STATUS_USERNAME_TAKEN
        bne appkey_login_fail
        lda #USERNAME_PROMPT_TAKEN
        sta username_prompt_mode
        jmp appkey_login_prompt
appkey_login_prompt_ok
        lda #USERNAME_PROMPT_NORMAL
        sta username_prompt_mode
        jsr token_ascii_to_binary
        jsr appkey_store_identity
        clc
        rts
appkey_login_resume
        jsr appkey_resume_identity
        bcs appkey_login_fail
        jsr token_ascii_to_binary
        clc
        rts
appkey_login_close_fail
        jsr n_close
appkey_login_fail
        sec
        rts

; ---- AppKey (FujiNet Fuji device $70/unit $01) ----

appkey_check_and_read
        lda #0
        sta has_identity
        lda #FUJINET_APPKEY_IDENTITY
        sta appkey_key_id
        jsr appkey_open_read
        cpy #1
        bne appkey_check_none
        jsr appkey_read
        cpy #1
        bne appkey_check_none
        lda appkey_data_buf+0
        sta appkey_count
        lda appkey_data_buf+1
        bne appkey_check_none
        lda appkey_count
        beq appkey_check_none
        cmp #65
        bcs appkey_check_none
        ldy #0
appkey_check_find_comma
        cpy appkey_count
        beq appkey_check_none
        lda appkey_data_buf+2,y
        cmp #44
        beq appkey_check_found_comma
        iny
        jmp appkey_check_find_comma
appkey_check_found_comma
        sty username_len
        cpy #1
        bcc appkey_check_none
        cpy #USERNAME_MAX_LEN+1
        bcs appkey_check_none
        ldx #0
appkey_check_copy_username
        cpx username_len
        beq appkey_check_copy_username_done
        lda appkey_data_buf+2,x
        sta username_buf,x
        inx
        jmp appkey_check_copy_username
appkey_check_copy_username_done
        iny
        lda appkey_count
        sec
        sbc username_len
        sec
        sbc #1
        sta token_len
        beq appkey_check_none
        cmp #TOKEN_MAX_LEN+1
        bcs appkey_check_none
        ldx #0
appkey_check_copy_token
        cpx token_len
        beq appkey_check_copy_token_done
        lda appkey_data_buf+2,y
        sta token_buf,x
        iny
        inx
        jmp appkey_check_copy_token
appkey_check_copy_token_done
        lda #1
        sta has_identity
        rts
appkey_check_none
        lda #0
        sta has_identity
        rts

appkey_open_read
        lda #APPKEY_MODE_READ
        sta appkey_open_buf+4
        jsr appkey_open_common
        rts

appkey_open_write
        lda #APPKEY_MODE_WRITE
        sta appkey_open_buf+4
        jsr appkey_open_common
        rts

appkey_open_common
        lda #<FUJINET_CREATOR_ID
        sta appkey_open_buf+0
        lda #>FUJINET_CREATOR_ID
        sta appkey_open_buf+1
        lda #FUJINET_APP_ID
        sta appkey_open_buf+2
        lda appkey_key_id
        sta appkey_open_buf+3
        lda #0
        sta appkey_open_buf+5
        lda #FUJI_DEVICE
        sta DDEVIC
        lda #FUJI_UNIT
        sta DUNIT
        lda #FUJICMD_OPEN_APPKEY
        sta DCOMND
        lda #$80
        sta DSTATS
        lda #<appkey_open_buf
        sta DBUFLO
        lda #>appkey_open_buf
        sta DBUFHI
        lda #6
        sta DBYTLO
        lda #0
        sta DBYTHI
        sta DAUX1
        sta DAUX2
        jsr SIOV
        rts

appkey_read
        lda #FUJI_DEVICE
        sta DDEVIC
        lda #FUJI_UNIT
        sta DUNIT
        lda #FUJICMD_READ_APPKEY
        sta DCOMND
        lda #$40
        sta DSTATS
        lda #<appkey_data_buf
        sta DBUFLO
        lda #>appkey_data_buf
        sta DBUFHI
        lda #66
        sta DBYTLO
        lda #0
        sta DBYTHI
        sta DAUX1
        sta DAUX2
        jsr SIOV
        rts

appkey_write
        lda #FUJI_DEVICE
        sta DDEVIC
        lda #FUJI_UNIT
        sta DUNIT
        lda #FUJICMD_WRITE_APPKEY
        sta DCOMND
        lda #$80
        sta DSTATS
        lda #<(appkey_data_buf+2)
        sta DBUFLO
        lda #>(appkey_data_buf+2)
        sta DBUFHI
        lda #64
        sta DBYTLO
        lda #0
        sta DBYTHI
        lda appkey_write_len
        sta DAUX1
        lda #0
        sta DAUX2
        jsr SIOV
        rts

appkey_store_identity
        ldx #0
appkey_store_identity_copy_username
        cpx username_len
        beq appkey_store_identity_comma
        lda username_buf,x
        sta appkey_data_buf+2,x
        inx
        jmp appkey_store_identity_copy_username
appkey_store_identity_comma
        lda #44
        sta appkey_data_buf+2,x
        inx
        ldy #0
appkey_store_identity_copy_token
        cpy token_len
        beq appkey_store_identity_copy_token_done
        lda token_buf,y
        sta appkey_data_buf+2,x
        inx
        iny
        jmp appkey_store_identity_copy_token
appkey_store_identity_copy_token_done
        stx appkey_write_len
        lda #FUJINET_APPKEY_IDENTITY
        sta appkey_key_id
        jsr appkey_open_write
        cpy #1
        bne appkey_store_identity_fail
        jsr appkey_write
        cpy #1
        bne appkey_store_identity_fail
        clc
        rts
appkey_store_identity_fail
        sec
        rts

; ---- N: device raw TCP (FujiNet network device $71, N1:) ----

n_login_open
        jsr n_open
        cpy #1
        bne n_login_open_fail
        clc
        rts
n_login_open_fail
        sec
        rts

n_open
        lda #N_DEVICE
        sta DDEVIC
        lda #N_UNIT
        sta DUNIT
        lda #N_CMD_OPEN
        sta DCOMND
        lda #$80
        sta DSTATS
        lda #<n_devicespec_buf
        sta DBUFLO
        lda #>n_devicespec_buf
        sta DBUFHI
        lda #0
        sta DBYTLO
        lda #1
        sta DBYTHI
        lda #N_OPEN_MODE_RW
        sta DAUX1
        lda #N_OPEN_TRANS_NONE
        sta DAUX2
        jsr SIOV
        rts

n_status
        lda #N_DEVICE
        sta DDEVIC
        lda #N_UNIT
        sta DUNIT
        lda #N_CMD_STATUS
        sta DCOMND
        lda #$40
        sta DSTATS
        lda #<n_status_buf
        sta DBUFLO
        lda #>n_status_buf
        sta DBUFHI
        lda #4
        sta DBYTLO
        lda #0
        sta DBYTHI
        sta DAUX1
        sta DAUX2
        jsr SIOV
        rts

; A = number of bytes to read; appends into login_pkt_buf at offset
; login_recv_len (uses ptr as scratch, safe: connection sequence runs
; before any gameplay routine needs ptr).
n_read_response_chunk
        sta DBYTLO
        lda #0
        sta DBYTHI
        lda #<login_pkt_buf
        clc
        adc login_recv_len
        sta ptr
        lda #>login_pkt_buf
        adc #0
        sta ptr+1
        lda ptr
        sta DBUFLO
        lda ptr+1
        sta DBUFHI
        lda #N_DEVICE
        sta DDEVIC
        lda #N_UNIT
        sta DUNIT
        lda #N_CMD_READ
        sta DCOMND
        lda #$40
        sta DSTATS
        lda DBYTLO
        sta DAUX1
        lda #0
        sta DAUX2
        jsr SIOV
        rts

; A = number of bytes to write from login_pkt_buf+0.
n_write
        sta DBYTLO
        pha
        lda #0
        sta DBYTHI
        lda #N_DEVICE
        sta DDEVIC
        lda #N_UNIT
        sta DUNIT
        lda #N_CMD_WRITE
        sta DCOMND
        lda #$80
        sta DSTATS
        lda #<login_pkt_buf
        sta DBUFLO
        lda #>login_pkt_buf
        sta DBUFHI
        pla
        sta DAUX1
        lda #0
        sta DAUX2
        jsr SIOV
        rts

n_close
        lda #N_DEVICE
        sta DDEVIC
        lda #N_UNIT
        sta DUNIT
        lda #N_CMD_CLOSE
        sta DCOMND
        lda #0
        sta DSTATS
        sta DBYTLO
        sta DBYTHI
        sta DAUX1
        sta DAUX2
        jsr SIOV
        rts

; ---- Login/resume packet framing (protocol.py encode_packet) ----

login_build_login_request
        lda #NET_PACKET_MAGIC
        sta login_pkt_buf+0
        lda #NETSTREAM_PROTOCOL_VERSION
        sta login_pkt_buf+1
        lda #LOGIN_PKT_LOGIN_REQUEST
        sta login_pkt_buf+2
        lda username_len
        sta login_pkt_buf+4
        clc
        adc #1
        sta login_payload_len
        sta login_pkt_buf+3
        ldy #0
login_build_login_request_copy
        cpy username_len
        beq login_build_login_request_done
        lda username_buf,y
        sta login_pkt_buf+5,y
        iny
        jmp login_build_login_request_copy
login_build_login_request_done
        rts

login_build_resume_request
        lda #NET_PACKET_MAGIC
        sta login_pkt_buf+0
        lda #NETSTREAM_PROTOCOL_VERSION
        sta login_pkt_buf+1
        lda #LOGIN_PKT_RESUME_REQUEST
        sta login_pkt_buf+2
        lda token_len
        sta login_pkt_buf+4
        clc
        adc #1
        sta login_payload_len
        sta login_pkt_buf+3
        ldy #0
login_build_resume_request_copy
        cpy token_len
        beq login_build_resume_request_done
        lda token_buf,y
        sta login_pkt_buf+5,y
        iny
        jmp login_build_resume_request_copy
login_build_resume_request_done
        rts

; Sums login_pkt_buf[0..3+payload_len], stores checksum byte, writes
; the whole frame over the N: device. Carry set on write failure.
login_checksum_and_send
        lda login_payload_len
        clc
        adc #4
        sta login_frame_len
        lda #0
        sta login_checksum
        ldy #0
login_checksum_send_loop
        cpy login_frame_len
        beq login_checksum_send_store
        lda login_pkt_buf,y
        clc
        adc login_checksum
        sta login_checksum
        iny
        jmp login_checksum_send_loop
login_checksum_send_store
        lda login_checksum
        sta login_pkt_buf,y
        iny
        sty login_total_len
        lda login_total_len
        jsr n_write
        cpy #1
        bne login_checksum_send_fail
        clc
        rts
login_checksum_send_fail
        sec
        rts

; Polls STATUS/READ until a full framed packet has arrived in
; login_pkt_buf or the timeout elapses. Carry set = timeout/error.
login_recv_response
        lda #0
        sta login_recv_len
        lda #180
        sta login_recv_timeout
login_recv_wait_loop
        jsr n_status
        cpy #1
        bne login_recv_error
; FujiNet status error byte: 1 = success, values >= 2 are real errors
; (e.g. 136 = EOF after the server closes its end). Bytes already
; buffered in FujiNet remain readable after a remote close, so only
; treat an error as fatal when there is nothing left to read.
        lda n_status_buf+0
        bne login_recv_have_avail
        lda n_status_buf+3
        cmp #2
        bcs login_recv_error
        jmp login_recv_wait_more
login_recv_have_avail
        sta login_recv_avail
        lda #LOGIN_PKT_BUF_SIZE
        sec
        sbc login_recv_len
        cmp login_recv_avail
        bcs login_recv_avail_ok
        sta login_recv_avail
login_recv_avail_ok
        lda login_recv_avail
        beq login_recv_wait_more
        jsr n_read_response_chunk
        cpy #1
        bne login_recv_error
        lda login_recv_avail
        clc
        adc login_recv_len
        sta login_recv_len
        cmp #4
        bcc login_recv_wait_more
        lda login_pkt_buf+3
        clc
        adc #5
        sta login_expected_total
        lda login_recv_len
        cmp login_expected_total
        bcc login_recv_wait_more
        clc
        rts
login_recv_wait_more
        jsr wait_frame_tick
        dec login_recv_timeout
        bne login_recv_wait_loop
login_recv_error
        sec
        rts

; Validates magic/version/checksum over login_pkt_buf. Carry set = bad.
login_verify_checksum
        lda login_pkt_buf+0
        cmp #NET_PACKET_MAGIC
        bne login_verify_bad
        lda login_pkt_buf+1
        cmp #NETSTREAM_PROTOCOL_VERSION
        bne login_verify_bad
        lda login_pkt_buf+3
        clc
        adc #4
        sta login_frame_len
        lda #0
        sta login_checksum
        ldy #0
login_verify_checksum_loop
        cpy login_frame_len
        beq login_verify_checksum_compare
        lda login_pkt_buf,y
        clc
        adc login_checksum
        sta login_checksum
        iny
        jmp login_verify_checksum_loop
login_verify_checksum_compare
        lda login_pkt_buf,y
        cmp login_checksum
        bne login_verify_bad
        clc
        rts
login_verify_bad
        sec
        rts

login_parse_login_response
        jsr login_verify_checksum
        bcs login_parse_fail
        lda login_pkt_buf+2
        cmp #LOGIN_PKT_LOGIN_RESPONSE
        bne login_parse_fail
        lda login_pkt_buf+4
        sta login_status
        lda login_pkt_buf+5
        sta token_len
        ldy #0
login_parse_login_response_copy
        cpy token_len
        beq login_parse_login_response_done
        lda login_pkt_buf+6,y
        sta token_buf,y
        iny
        jmp login_parse_login_response_copy
login_parse_login_response_done
        clc
        rts
login_parse_fail
        sec
        rts

login_parse_resume_response
        jsr login_verify_checksum
        bcs login_parse_fail
        lda login_pkt_buf+2
        cmp #LOGIN_PKT_RESUME_RESPONSE
        bne login_parse_fail
        lda login_pkt_buf+4
        sta login_status
        lda login_pkt_buf+5
        sta username_len
        ldy #0
login_parse_resume_response_copy
        cpy username_len
        beq login_parse_resume_response_done
        lda login_pkt_buf+6,y
        sta username_buf,y
        iny
        jmp login_parse_resume_response_copy
login_parse_resume_response_done
        clc
        rts

; ---- ASCII decimal token -> 32-bit binary (little-endian token_bin) ----

token_ascii_to_binary
        lda #0
        sta token_bin+0
        sta token_bin+1
        sta token_bin+2
        sta token_bin+3
        ldx #0
token_ascii_to_binary_loop
        cpx token_len
        beq token_ascii_to_binary_done
        lda token_buf,x
        sec
        sbc #48
        jsr token_accumulate_digit
        inx
        jmp token_ascii_to_binary_loop
token_ascii_to_binary_done
        rts

; A = digit (0-9). token_bin = token_bin*10 + digit.
token_accumulate_digit
        sta token_digit
        lda token_bin+0
        sta token_tmp+0
        lda token_bin+1
        sta token_tmp+1
        lda token_bin+2
        sta token_tmp+2
        lda token_bin+3
        sta token_tmp+3
        jsr token_shl1
        jsr token_shl1
        jsr token_shl1
        jsr token_tmp_shl1
        clc
        lda token_bin+0
        adc token_tmp+0
        sta token_bin+0
        lda token_bin+1
        adc token_tmp+1
        sta token_bin+1
        lda token_bin+2
        adc token_tmp+2
        sta token_bin+2
        lda token_bin+3
        adc token_tmp+3
        sta token_bin+3
        clc
        lda token_bin+0
        adc token_digit
        sta token_bin+0
        lda token_bin+1
        adc #0
        sta token_bin+1
        lda token_bin+2
        adc #0
        sta token_bin+2
        lda token_bin+3
        adc #0
        sta token_bin+3
        rts

token_shl1
        asl token_bin+0
        rol token_bin+1
        rol token_bin+2
        rol token_bin+3
        rts

token_tmp_shl1
        asl token_tmp+0
        rol token_tmp+1
        rol token_tmp+2
        rol token_tmp+3
        rts

; ---- Username entry (CIO E: screen editor device) ----

; Opening E: reinitializes the OS screen editor: it resets the display
; list to the standard editor screen and clears it, wiping anything drawn
; beforehand. So the prompt text must be printed through E: itself (via
; PUT_RECORD) after the open, not drawn onto the custom screen first.
username_prompt_screen
        jsr cio_open_e
        bcs username_prompt_fail
        jsr cio_put_prompt
        bcs username_prompt_close_fail
        jsr cio_get_username
        lda #0
        rol
        sta cio_get_failed
        jsr cio_close_e
        lda cio_get_failed
        bne username_prompt_fail
        clc
        rts
username_prompt_close_fail
        jsr cio_close_e
username_prompt_fail
        lda #0
        sta username_len
        sec
        rts

cio_open_e
        lda #<e_device_name
        sta ICBAL
        lda #>e_device_name
        sta ICBAH
        lda #CIO_OPEN_RW
        sta ICAX1
        lda #0
        sta ICAX2
        lda #CIO_OPEN
        sta ICCMD
        ldx #IOCB1_X
        jsr CIOV
        cpy #1
        bne cio_open_e_fail
        jsr set_text_palette
        clc
        rts
cio_open_e_fail
        sec
        rts

cio_put_host_prompt
        lda #<server_host_prompt_text
        sta ICBAL
        lda #>server_host_prompt_text
        sta ICBAH
        lda #SERVER_HOST_PROMPT_TEXT_LEN
        sta ICBLL
        lda #0
        sta ICBLH
        lda #CIO_PUT_RECORD
        sta ICCMD
        ldx #IOCB1_X
        jsr CIOV
        cpy #1
        bne cio_put_host_prompt_fail
        clc
        rts
cio_put_host_prompt_fail
        sec
        rts

cio_get_username
        lda #<username_buf
        sta ICBAL
        lda #>username_buf
        sta ICBAH
        lda #USERNAME_MAX_LEN+2
        sta ICBLL
        lda #0
        sta ICBLH
        lda #CIO_GET_RECORD
        sta ICCMD
        ldx #IOCB1_X
        jsr CIOV
        cpy #1
        bne cio_get_username_fail
        ldx #0
cio_get_username_scan
        cpx #USERNAME_MAX_LEN
        beq cio_get_username_scan_done
        lda username_buf,x
        cmp #$9B
        beq cio_get_username_scan_done
        inx
        jmp cio_get_username_scan
cio_get_username_scan_done
        stx username_len
        clc
        rts
cio_get_username_fail
        sec
        rts

cio_get_server_host
        lda #<(appkey_data_buf+2)
        sta ICBAL
        lda #>(appkey_data_buf+2)
        sta ICBAH
        lda #SERVER_HOST_MAX_LEN+2
        sta ICBLL
        lda #0
        sta ICBLH
        lda #CIO_GET_RECORD
        sta ICCMD
        ldx #IOCB1_X
        jsr CIOV
        cpy #1
        bne cio_get_server_host_fail
        ldx #0
cio_get_server_host_scan
        cpx #SERVER_HOST_MAX_LEN
        beq cio_get_server_host_done
        lda appkey_data_buf+2,x
        cmp #$9B
        beq cio_get_server_host_done
        inx
        jmp cio_get_server_host_scan
cio_get_server_host_done
        stx server_host_input_len
        clc
        rts
cio_get_server_host_fail
        sec
        rts

cio_close_e
        lda #CIO_CLOSE
        sta ICCMD
        ldx #IOCB1_X
        jsr CIOV
        rts

netstream_smoke_test
        lda #<netstream_connect_lines
        sta wptr
        lda #>netstream_connect_lines
        sta wptr+1
        jsr show_netstream_screen

        jsr netstream_smoke_init
        cmp #0
        beq netstream_init_ok
        lda #1
        sta netstream_result
        lda #<netstream_init_fail_lines
        sta wptr
        lda #>netstream_init_fail_lines
        sta wptr+1
        jsr show_netstream_result_screen
        rts

netstream_init_ok
        jsr NETSTREAM_BEGIN_STREAM
        lda #15
        sta netstream_timeout
netstream_begin_settle_loop
        jsr wait_frame_tick
        dec netstream_timeout
        bne netstream_begin_settle_loop
        jsr netstream_send_probe
        bcc netstream_probe_sent
        lda #2
        sta netstream_result
        jsr NETSTREAM_END_STREAM
        lda #<netstream_send_fail_lines
        sta wptr
        lda #>netstream_send_fail_lines
        sta wptr+1
        jsr show_netstream_result_screen
        rts

netstream_probe_sent
        jsr netstream_wait_probe_echo
        bcc netstream_probe_ok
        lda #3
        sta netstream_result
        jsr NETSTREAM_END_STREAM
        lda #<netstream_recv_fail_lines
        sta wptr
        lda #>netstream_recv_fail_lines
        sta wptr+1
        jsr show_netstream_result_screen
        rts

netstream_probe_ok
        lda #0
        sta netstream_result
        jsr NETSTREAM_GET_FINAL_FLAGS
        sta netstream_final_flags
        jsr NETSTREAM_GET_FINAL_AUDF3
        sta netstream_final_audf3
        jsr NETSTREAM_GET_FINAL_AUDF4
        sta netstream_final_audf4
        rts

netstream_smoke_init
        lda #<netstream_args
        sta netstream_c_sp
        lda #>netstream_args
        sta netstream_c_sp+1
        lda #<NETSTREAM_PORT_SWAPPED
        ldx #>NETSTREAM_PORT_SWAPPED
        jsr NETSTREAM_INIT
        rts

netstream_realtime_init
        lda #<netstream_realtime_args
        sta netstream_c_sp
        lda #>netstream_realtime_args
        sta netstream_c_sp+1
        lda #<NETSTREAM_PORT_SWAPPED
        ldx #>NETSTREAM_PORT_SWAPPED
        jsr NETSTREAM_INIT
        rts

netstream_send_probe
        lda #60
        sta netstream_timeout
netstream_send_probe_loop
        lda #NETSTREAM_PROBE_BYTE
        jsr NETSTREAM_SEND_BYTE
        cmp #0
        beq netstream_send_probe_ok
        jsr wait_frame_tick
        dec netstream_timeout
        bne netstream_send_probe_loop
        sec
        rts
netstream_send_probe_ok
        clc
        rts

netstream_wait_probe_echo
        lda #180
        sta netstream_timeout
netstream_wait_probe_echo_loop
        jsr NETSTREAM_BYTES_AVAIL
        cpx #0
        bne netstream_recv_probe_byte
        cmp #0
        bne netstream_recv_probe_byte
        jsr wait_frame_tick
        dec netstream_timeout
        bne netstream_wait_probe_echo_loop
        sec
        rts
netstream_recv_probe_byte
        jsr NETSTREAM_RECV_BYTE
        cmp #NETSTREAM_PROBE_BYTE
        beq netstream_recv_probe_ok
        jmp netstream_wait_probe_echo_loop
netstream_recv_probe_ok
        clc
        rts

netstream_game_connect
        lda #0
        sta network_enabled
        sta network_got_welcome
        sta network_got_window
        sta network_realtime_enabled
        sta net_tick_lo
        sta net_tick_hi
        sta net_ack_tick_lo
        sta net_ack_tick_hi
        sta net_screen_dirty
        sta net_scroll_dirty
        sta status_dirty
        sta perf_world_packets
        sta perf_terrain_packets
        sta perf_full_redraws
        sta perf_partial_redraws
        sta perf_scroll_dirty_sets
        sta perf_screen_dirty_sets
        sta perf_snapshot_dirty_sets
        sta perf_frames_waited
        sta perf_edge_frames_max
        sta net_player_correction_pending
        sta net_last_terrain_seq_valid
        sta net_last_terrain_seq_lo
        sta net_last_terrain_seq_hi
        sta net_parser_state
        sta net_parser_index
        sta net_parser_checksum
        lda #$0f
        sta net_sent_stick_raw
        lda #>WORLD
        sta cache_active_hi
        lda #>WORLD_PENDING
        sta cache_pending_hi
        lda #15
        sta netstream_timeout
netstream_game_settle_loop
        jsr wait_frame_tick
        dec netstream_timeout
        bne netstream_game_settle_loop
        jsr netstream_send_hello
        bcc netstream_game_send_ok
        jsr NETSTREAM_END_STREAM
        rts
netstream_game_send_ok
        jsr netstream_bootstrap_start
netstream_game_wait_welcome
        jsr netstream_recv_packets
        lda network_got_welcome
        beq netstream_game_wait_more
        lda network_got_window
        bne netstream_game_connected
netstream_game_wait_more
        jsr wait_frame_tick
        dec netstream_timeout
        bne netstream_game_wait_welcome
        jsr netstream_bootstrap_retry
        bcc netstream_game_wait_welcome
netstream_game_bootstrap_fail
        lda #0
        sta network_enabled
        jsr NETSTREAM_END_STREAM
        rts
netstream_game_connected
        jsr netstream_start_realtime
        bcc netstream_game_realtime_ok
        lda #0
        sta network_enabled
        sta network_realtime_enabled
        jsr NETSTREAM_END_STREAM
        rts
netstream_game_realtime_ok
        rts

netstream_start_realtime
        jsr NETSTREAM_END_STREAM
        jsr netstream_realtime_init
        cmp #0
        beq netstream_realtime_init_ok
        sec
        rts
netstream_realtime_init_ok
        jsr NETSTREAM_BEGIN_STREAM
        lda #30
        sta netstream_timeout
netstream_realtime_settle_loop
        jsr wait_frame_tick
        dec netstream_timeout
        bne netstream_realtime_settle_loop
; Classify this connection as realtime v3: the raw "RT3" + newline preamble
; replaces the old first-byte $AD detection (COBS frames have no fixed
; first byte), then AUTH identifies the player.
        jsr netstream_send_rt3_preamble
        bcc netstream_realtime_preamble_ok
        sec
        rts
netstream_realtime_preamble_ok
; Identify this realtime connection before any PLAYER_STATE: the server
; ignores unauthenticated connections and drops them after ~5 seconds.
        jsr netstream_send_auth_packet
        bcc netstream_realtime_auth_ok
        sec
        rts
netstream_realtime_auth_ok
        lda RTCLOK
        sec
        sbc #NET_REALTIME_SEND_DELAY
        sta net_realtime_send_clk
        lda RTCLOK
        sta net_auth_keepalive_clk
; These live in uninitialized fixed RAM: clear them on every realtime
; start (first boot does not pass through netstream_reconnect_bootstrap).
        lda #0
        sta net_rt_watchdog_armed
        sta net_rt_rx_index
        sta net_v3_discard
        sta net_cache_rev_lo
        sta net_cache_rev_hi
        sta net_terrain_desync
        sta net_resync_pending
        sta net_row_fill_active
        sta net_map_fill_pending
        lda #1
        sta network_realtime_enabled
        clc
        rts

; One small NET_RT_AUTH packet carrying the Phase 7.6 login token
; (4 bytes little-endian at offset 6). Carry set on send failure.
; A = realtime packet type: clear the TX buffer, write magic/version/type
; and the tail pattern. Seq bytes (+4/+5) stay zero for callers that need
; none; others fill them after this returns.
netstream_tx_prepare
        pha
        ldx #0
        lda #0
netstream_tx_prepare_clear
        sta net_realtime_tx_packet,x
        inx
        cpx #NET_REALTIME_SMALL_PACKET_BYTES
        bne netstream_tx_prepare_clear
        lda #NET_REALTIME_V3_VERSION
        sta net_realtime_tx_packet+1
        pla
        sta net_realtime_tx_packet+2
        rts

; Send the prepared TX packet as one COBS/CRC-16 v3 wire frame. Finalize
; stamps the per-type payload length, appends the CRC, and COBS-encodes
; into net_packet_payload; then the encoded bytes plus the zero delimiter
; go out. Carry set on send failure.
netstream_tx_send
        jsr netstream_tx_finalize
        ldx #0
netstream_tx_send_loop
        cpx net_v3_tx_len
        beq netstream_tx_send_delim
        lda net_packet_payload,x
        stx net_realtime_send_index
        jsr netstream_send_raw_byte
        ldx net_realtime_send_index
        bcs netstream_tx_send_fail
        inx
        jmp netstream_tx_send_loop
netstream_tx_send_delim
        lda #0
        jsr netstream_send_raw_byte
        bcs netstream_tx_send_fail
        clc
        rts
netstream_tx_send_fail
        sec
        rts

netstream_send_auth_packet
        lda #NET_RT_AUTH
        jsr netstream_tx_prepare
        lda token_bin+0
        sta net_realtime_tx_packet+NET_RT_AUTH_TOKEN_OFFSET
        lda token_bin+1
        sta net_realtime_tx_packet+NET_RT_AUTH_TOKEN_OFFSET+1
        lda token_bin+2
        sta net_realtime_tx_packet+NET_RT_AUTH_TOKEN_OFFSET+2
        lda token_bin+3
        sta net_realtime_tx_packet+NET_RT_AUTH_TOKEN_OFFSET+3
        jmp netstream_tx_send

netstream_send_auth_keepalive
        lda network_realtime_enabled
        bne netstream_auth_keepalive_enabled
        rts
netstream_auth_keepalive_enabled
        lda RTCLOK
        sec
        sbc net_auth_keepalive_clk
        cmp #NET_AUTH_KEEPALIVE_DELAY
        bcs netstream_auth_keepalive_due
        rts
netstream_auth_keepalive_due
        lda RTCLOK
        sta net_auth_keepalive_clk
        jsr netstream_send_auth_packet
        bcc netstream_auth_keepalive_done
        lda #0
        sta network_enabled
        sta network_realtime_enabled
        jsr NETSTREAM_END_STREAM
netstream_auth_keepalive_done
        rts

; Ask the server for a fresh window over the open netstream (the missing
; NET_RT_WINDOW_ROW packets follow; all 24 when no NACK bitmap is sent).
; Marks the resync pending; main_loop retries after NET_RESYNC_RETRY_DELAY
; frames of fill silence (arriving rows re-stamp the clock) until the
; row bitmap completes.
; netstream_send_resync_request relocated to the $5A00 segment (the main
; segment is out of room and the routine gained request-new-fill flag
; handling there).

netstream_send_map_ready
        lda #NET_RT_MAP_READY
        jsr netstream_tx_prepare
        lda current_map_id
        sta net_realtime_tx_packet+6
        jsr netstream_tx_send
        bcs netstream_send_resync_req_fail
        rts

netstream_send_resync_req_fail
        lda #0
        sta network_enabled
        sta network_realtime_enabled
        jsr NETSTREAM_END_STREAM
        rts

netstream_send_hello
        lda #0
        sta net_send_checksum
        lda #NET_PACKET_MAGIC
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda #NETSTREAM_PROTOCOL_VERSION
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda #NET_PKT_HELLO
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda #NET_HELLO_PAYLOAD_LEN
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda #0
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda #1
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda #0
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda token_bin+0
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda token_bin+1
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda token_bin+2
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda token_bin+3
        jsr netstream_send_packet_byte
        bcs netstream_send_hello_fail
        lda net_send_checksum
        jsr netstream_send_raw_byte
        rts
netstream_send_hello_fail
        sec
        rts

; (The legacy v5 framed INPUT sender lived here; realtime PLAYER_STATE
; replaced it and it had no remaining callers.)

netstream_send_player_state_realtime
        lda network_enabled
        bne netstream_send_player_state_enabled
        rts
netstream_send_player_state_enabled
        lda net_prediction_send_pending
        bne netstream_realtime_send_due
        lda RTCLOK
        sec
        sbc net_realtime_send_clk
        cmp #NET_REALTIME_SEND_DELAY
        bcs netstream_realtime_send_due
        rts
netstream_realtime_send_due
        lda RTCLOK
        sta net_realtime_send_clk
        inc net_realtime_seq_lo
        bne netstream_player_seq_ok
        inc net_realtime_seq_hi
netstream_player_seq_ok
        lda #NET_RT_PLAYER_STATE
        jsr netstream_tx_prepare
        lda net_realtime_seq_lo
        sta net_realtime_tx_packet+4
        lda net_realtime_seq_hi
        sta net_realtime_tx_packet+5
        lda player_x
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET
        lda player_y
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET+1
        lda aim_dir
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET+2
        lda input_buttons
        ora net_dialogue_decline
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET+3
        lda net_fire_counter
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET+4
        lda net_pickup_counter
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET+5
        lda net_realtime_server_seq_lo
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET+6
        lda net_realtime_server_seq_hi
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET+7
        lda net_rx_drops
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET+8
        lda net_pvp_toggle_counter
        sta net_realtime_tx_packet+NET_RT_PLAYER_PAYLOAD_OFFSET+9
        jsr netstream_tx_send
        bcs netstream_send_player_packet_fail
        lda net_prediction_send_pending
        beq netstream_send_player_packet_done
        lda #0
        sta net_prediction_send_pending
        lda #1
        sta net_predicted_move_pending
        lda net_realtime_seq_lo
        sta net_predicted_move_seq_lo
        lda net_realtime_seq_hi
        sta net_predicted_move_seq_hi
netstream_send_player_packet_done
        rts
netstream_send_player_packet_fail
        lda #0
        sta network_enabled
        jsr NETSTREAM_END_STREAM
        rts

netstream_recv_realtime_packets
        lda network_enabled
        bne netstream_recv_realtime_enabled
        rts
netstream_recv_realtime_enabled
        jsr NETSTREAM_BYTES_AVAIL
        cpx #0
        bne netstream_recv_realtime_read_byte
        cmp #0
        bne netstream_recv_realtime_read_byte
        rts
netstream_recv_realtime_read_byte
        jsr NETSTREAM_RECV_BYTE
        jsr netstream_v3_rx_byte
        jmp netstream_recv_realtime_packets

; Dispatch a validated v3 raw frame (netstream_v3_process_frame verified
; version, declared length, and CRC-16, then zero-padded the tail, so the
; per-type handlers read padded zeros beyond the sent payload).
netstream_apply_realtime_packet
        lda net_realtime_packet+2
        sta net_realtime_type
        cmp #NET_RT_MAP_CHANGE
        beq netstream_apply_map_change_jump
        cmp #NET_RT_WORLD_STATE
        beq netstream_apply_world_state_jump
        cmp #NET_RT_TERRAIN_EDGE
        beq netstream_apply_terrain_edge_jump
        cmp #NET_RT_REMOTE_PLAYERS
        beq netstream_apply_remote_players_jump
        cmp #NET_RT_WINDOW_ROW
        beq netstream_apply_window_row_jump
        cmp #NET_RT_INVENTORY
        beq netstream_apply_inventory_jump
        cmp #NET_RT_ITEM_DROPS
        beq netstream_apply_item_drops_jump
        cmp #NET_RT_MAP_SUMMARY
        beq netstream_apply_map_summary_jump
        cmp #NET_RT_QUEST_UPDATE
        beq netstream_apply_quest_update_jump
        cmp #NET_RT_MESSAGE
        beq netstream_apply_message_jump
        cmp #NET_RT_HUD_UPDATE
        beq netstream_apply_hud_update_jump
        cmp #NET_RT_RESPAWN
        beq netstream_apply_respawn_event_jump
        cmp #NET_RT_WINDOW_COMMIT_ACK
        beq netstream_apply_commit_ack_jump
        cmp #NET_RT_DIALOGUE_PAGE
        beq netstream_apply_dialogue_page_jump
        rts
netstream_apply_dialogue_page_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_dialogue_page
netstream_apply_commit_ack_jump
        jsr netstream_stamp_valid_realtime
; Server confirmed the window commit: stop retrying it.
        lda net_realtime_packet+6
        cmp net_last_committed_fill_id
        bne netstream_apply_commit_ack_done
        lda #0
        sta net_fill_commit_pending
netstream_apply_commit_ack_done
        rts

netstream_apply_map_change_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_map_change
netstream_apply_world_state_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_world_state
netstream_apply_terrain_edge_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_terrain_edge
netstream_apply_remote_players_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_remote_players
netstream_apply_window_row_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_window_row
netstream_apply_inventory_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_inventory
netstream_apply_item_drops_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_item_drops
netstream_apply_map_summary_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_map_summary
netstream_apply_quest_update_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_quest_update
netstream_apply_message_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_message
netstream_apply_hud_update_jump
        jsr netstream_stamp_valid_realtime
        jmp netstream_apply_hud_update
netstream_apply_respawn_event_jump
        jmp netstream_stamp_valid_realtime

netstream_stamp_valid_realtime
        lda #1
        sta net_rt_packet_valid
        sta net_rt_watchdog_armed
        lda RTCLOK
        sta net_last_valid_rt_clk
        rts

; MAP_CHANGE arrives mid-receive, several JSRs deep. Only record it here
; and defer the actual reconnect to main_loop depth (handle_map_change),
; so a failed reconnect can fall into the connection-failed retry gate
; without abandoning return addresses on the stack.
netstream_apply_map_change
; The server re-sends MAP_CHANGE until MAP_READY. A duplicate of the
; transition already in progress must not reset the staged fill (that
; discards recovered rows and can livelock a slow/lossy link).
        lda net_map_change_pending
        ora net_map_fill_pending
        beq netstream_map_change_fresh
        lda net_realtime_packet+NET_RT_MAP_ID_OFFSET
        cmp current_map_id
        bne netstream_map_change_fresh
        rts
netstream_map_change_fresh
        lda net_realtime_packet+NET_RT_MAP_ID_OFFSET
        sta current_map_id
        lda net_realtime_packet+NET_RT_MAP_TILESET_OFFSET
        sta current_tileset_id
        lda net_realtime_packet+NET_RT_MAP_PALETTE_OFFSET
        sta current_palette_id
        lda net_realtime_packet+NET_RT_MAP_SPAWN_X_OFFSET
        sta net_map_spawn_x
        lda net_realtime_packet+NET_RT_MAP_SPAWN_Y_OFFSET
        sta net_map_spawn_y
        jsr netstream_map_change_reset_fill
        lda #1
        sta net_map_change_pending
        rts

; Runs at main_loop depth. The transition stays in-band: the server keeps
; the realtime session and streams the new map's window as WINDOW_ROW
; packets on the same connection, so the netstream never drops. Snap to the
; spawn, clear old-map overlays and prediction, and freeze movement until
; the fill completes (row 23 applies the new tileset/palette, snaps the
; view, and full-redraws -- one clean cut). If the fill stalls, the retry
; timer requests a full fill; the watchdog remains the disaster fallback.
handle_map_change
        lda #0
        sta net_map_change_pending
        sta input_dir
        sta input_buttons
        sta net_player_correction_pending
        sta net_predicted_move_pending
        jsr netstream_restore_clear_dynamic
; Row masks are NOT cleared here: netstream_apply_map_change already reset
; the fill state at parser depth, and rows staged from the same recv batch
; have live bits in the bitmap that a clear here would wipe.
        lda net_map_spawn_x
        sta player_x
        sta old_player_x
        lda net_map_spawn_y
        sta player_y
        sta old_player_y
        lda #1
        sta net_map_fill_pending
        lda RTCLOK
        sta net_resync_request_clk
; If the whole fill already staged while a modal held this handler off,
; its completion was deferred (see netstream_window_row_complete_check);
; run the mask check now at safe depth so the transition cuts over
; immediately. Enter past the mark step -- the RX buffer no longer holds a
; WINDOW_ROW packet here, so marking would set a bogus mask bit.
        jmp netstream_window_row_check_masks

netstream_watchdog_check
        lda network_realtime_enabled
        bne netstream_watchdog_enabled
        clc
        rts
netstream_watchdog_enabled
        lda net_rt_watchdog_armed
        bne netstream_watchdog_armed
        clc
        rts
netstream_watchdog_armed
        lda RTCLOK
        sec
        sbc net_last_valid_rt_clk
        cmp #NET_REALTIME_STALE_TIMEOUT
        bcs netstream_watchdog_trip
        clc
        rts
netstream_watchdog_trip
; If a map fill was interrupted by the stream dying, apply the deferred
; tileset/palette now so the post-reconnect bootstrap window (which is for
; the new map) renders with the right art.
        lda net_map_fill_pending
        beq netstream_watchdog_no_map_fill
        lda #0
        sta net_map_fill_pending
        jsr apply_tileset
        jsr apply_palette
netstream_watchdog_no_map_fill
        jsr netstream_restore_clear_dynamic
        jsr netstream_reconnect_bootstrap
        bcs netstream_watchdog_fail
        jsr netstream_snap_view_to_window
        clc
        rts
netstream_watchdog_fail
        lda #0
        sta network_realtime_enabled
        sec
        rts

netstream_restore_clear_dynamic
        jsr restore_old_dynamic_overlays
        ldx #0
        lda #0
netstream_clear_enemy_state
        cpx #NET_MAX_BEAVERS
        beq netstream_clear_enemy_state_done
        sta enemy_alive,x
        sta old_enemy_alive,x
        sta enemy_kind,x
        sta old_enemy_kind,x
        inx
        jmp netstream_clear_enemy_state
netstream_clear_enemy_state_done
        ldx #0
netstream_clear_remote_state
        cpx #NET_MAX_REMOTE_PLAYERS
        beq netstream_clear_remote_state_done
        sta remote_alive,x
        sta old_remote_alive,x
        inx
        jmp netstream_clear_remote_state
netstream_clear_remote_state_done
; Item-drop slot clear lives with the rest of the item-drop overlay code
; near $8000 (net_clear_item_state); A=0 on entry and returns unchanged
; since the routine only ever stores it.
        jsr net_clear_item_state
        lda #0
        sta bullet_active
        sta bullet_drawn
        jsr clear_remote_bullets
        sta net_last_terrain_seq_valid
        rts

netstream_reconnect_bootstrap
        lda #0
        sta network_realtime_enabled
        sta net_rt_watchdog_armed
        sta net_rt_rx_index
        sta net_v3_discard
        sta net_cache_rev_lo
        sta net_cache_rev_hi
        sta net_terrain_desync
        sta net_resync_pending
        sta net_row_fill_active
        sta net_map_fill_pending
        sta net_rx_drops
        jsr NETSTREAM_END_STREAM
        jsr netstream_smoke_init
        cmp #0
        bne netstream_reconnect_fail
        jsr NETSTREAM_BEGIN_STREAM
        lda #15
        sta netstream_timeout
netstream_reconnect_settle
        jsr wait_frame_tick
        dec netstream_timeout
        bne netstream_reconnect_settle
        jsr netstream_game_connect
        lda network_enabled
        beq netstream_reconnect_fail
        lda network_realtime_enabled
        beq netstream_reconnect_fail
        clc
        rts
netstream_reconnect_fail
        sec
        rts

netstream_snap_view_to_window
; Snap the view to the current map's window origin (like init_level does at
; boot) instead of keeping a stale view. net_update_view_position only nudges
; one tile per call, so a stale view can leave the player off-screen.
        lda net_window_origin_x
        sta view_x
        sta old_view_x
        lda net_window_origin_y
        sta view_y
        sta old_view_y
        jsr net_update_view_position
        lda #1
        sta net_snapshot_dirty
        rts

apply_tileset
        lda current_tileset_id
        cmp #TILESET_CAVE
        beq apply_tileset_cave
        jsr copy_overworld_tile_tables
        lda #>FONT
        sta current_font_page
        rts
apply_tileset_cave
        jsr copy_cave_tile_tables
; Cave shares the overworld FONT page (Phase 57 font reclamation); the cave tile
; tables still select their own glyph quads from that shared font.
        lda #>FONT
        sta current_font_page
        rts

copy_overworld_tile_tables
        ldx #CAVE_TILE_TABLE_LEN-1
copy_overworld_tile_tables_loop
        lda tile2x2_tl_overworld,x
        sta tile2x2_tl,x
        lda tile2x2_tr_overworld,x
        sta tile2x2_tr,x
        lda tile2x2_bl_overworld,x
        sta tile2x2_bl,x
        lda tile2x2_br_overworld,x
        sta tile2x2_br,x
        dex
        bpl copy_overworld_tile_tables_loop
        rts

copy_cave_tile_tables
        ldx #CAVE_TILE_TABLE_LEN-1
copy_cave_tile_tables_loop
        lda tile2x2_tl_cave,x
        sta tile2x2_tl,x
        lda tile2x2_tr_cave,x
        sta tile2x2_tr,x
        lda tile2x2_bl_cave,x
        sta tile2x2_bl,x
        lda tile2x2_br_cave,x
        sta tile2x2_br,x
        dex
        bpl copy_cave_tile_tables_loop
        rts

apply_palette
        lda current_palette_id
        cmp #PALETTE_CAVE
        beq apply_palette_cave
        cmp #2
        beq apply_palette_pvp_realm
        jsr set_game_palette
        rts
apply_palette_cave
        lda #$06
        sta COLOR0
        lda #$84
        sta COLOR1
        lda #$0e
        sta COLOR2
        lda #$98
        sta COLOR3
        lda #$00
        sta COLOR4
        jmp sync_colors_hw
apply_palette_pvp_realm
        lda #$24
        sta COLOR0
        lda #$c2
        sta COLOR1
        lda #$0c
        sta COLOR2
        lda #$46
        sta COLOR3
        lda #$00
        sta COLOR4
        jmp sync_colors_hw

netstream_apply_world_state
        inc perf_world_packets
        lda #0
        sta net_world_changed
        lda net_realtime_packet+4
        sta net_realtime_server_seq_lo
        lda net_realtime_packet+5
        sta net_realtime_server_seq_hi
        lda net_realtime_packet+NET_RT_WORLD_CORRECTION_OFFSET
        bne netstream_world_apply_correction
        lda net_realtime_packet+NET_RT_WORLD_ECHO_SEQ_LO_OFFSET
        cmp net_realtime_seq_lo
        bne netstream_world_skip_player_pos
        lda net_realtime_packet+NET_RT_WORLD_ECHO_SEQ_HI_OFFSET
        cmp net_realtime_seq_hi
        bne netstream_world_skip_player_pos
netstream_world_apply_player_pos
        lda #0
        sta net_player_correction_pending
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET
        cmp player_x
        bne netstream_world_player_changed
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET+1
        cmp player_y
        beq netstream_world_store_player_pos
netstream_world_player_changed
        lda #1
        sta net_world_changed
netstream_world_store_player_pos
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET
        sta player_x
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET+1
        sta player_y
        jmp netstream_world_skip_player_pos
netstream_world_apply_correction
        jsr queue_or_apply_player_correction
netstream_world_skip_player_pos
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET+2
        cmp player_health
        beq netstream_world_store_health
        pha
        lda #1
        sta status_dirty
        sta hp_dirty
        pla
        bcs netstream_world_store_health
        pha
        lda #SFX_HURT
        jsr sfx_request
        pla
netstream_world_store_health
        sta player_health
        lda net_realtime_packet+NET_RT_WORLD_TILE_X_OFFSET
        sta net_packet_payload+20
        lda net_realtime_packet+NET_RT_WORLD_TILE_Y_OFFSET
        sta net_packet_payload+21
        lda net_realtime_packet+NET_RT_WORLD_TILE_ID_OFFSET
        sta net_packet_payload+22
        lda net_packet_payload+20
        ora net_packet_payload+21
        beq netstream_world_no_tile_change
        lda #1
        sta net_world_changed
netstream_world_no_tile_change
        jsr net_apply_tile_update
        jsr net_clear_enemy_tiles
        lda net_realtime_packet+3
        cmp #NET_MAX_BEAVERS+1
        bcc netstream_world_count_ok
        lda #NET_MAX_BEAVERS
netstream_world_count_ok
        sta active_beaver_count
        ldx #0
netstream_world_copy_beaver_loop
        cpx #NET_MAX_BEAVERS*4
        beq netstream_world_copy_beaver_done
        lda net_realtime_packet+NET_RT_WORLD_BEAVER_OFFSET,x
        cmp net_packet_payload+8,x
        beq netstream_world_beaver_byte_same
        lda #1
        sta net_world_changed
        lda net_realtime_packet+NET_RT_WORLD_BEAVER_OFFSET,x
netstream_world_beaver_byte_same
        sta net_packet_payload+8,x
        inx
        jmp netstream_world_copy_beaver_loop
netstream_world_copy_beaver_done
        lda beavers_left
        sta net_old_beavers_left
        jsr net_apply_beavers
        lda beavers_left
        cmp net_old_beavers_left
        beq netstream_world_beavers_same
netstream_world_beavers_same
        jsr net_update_view_position
.if ENABLE_WORLDSTATE_PARTIAL
        lda net_scroll_dirty
        bne netstream_world_scroll_dirty
        lda net_world_changed
        ora status_dirty
        bne netstream_world_mark_dirty
        rts
netstream_world_mark_dirty
        lda #1
        sta net_world_dirty
        sta net_screen_dirty
        rts
netstream_world_scroll_dirty
        rts
.else
        inc perf_snapshot_dirty_sets
        lda #1
        sta net_snapshot_dirty
        rts
.endif

; Cosmetic sibling of update_bullet. Remote tracers never apply damage; they
; only reproduce the local bullet's pacing, range, and blocking rules.
update_remote_bullets
        lda #0
        sta rbullet_index
update_remote_bullets_loop
        ldx rbullet_index
        cpx #RBULLET_SLOTS
        bne update_remote_bullets_check_active
        rts
update_remote_bullets_check_active
        lda rbullet_active,x
        bne update_remote_bullets_check_time
        jmp update_remote_bullets_next
update_remote_bullets_check_time
        lda RTCLOK
        sec
        sbc rbullet_clk,x
        cmp #BULLET_DELAY
        bcs update_remote_bullets_time_ready
        jmp update_remote_bullets_next
update_remote_bullets_time_ready
        lda RTCLOK
        sta rbullet_clk,x

        lda rbullet_drawn,x
        beq update_remote_bullet_advance
        lda rbullet_x,x
        sta target_x
        lda rbullet_y,x
        sta target_y
        jsr restore_target_top_cell
        ldx rbullet_index
update_remote_bullet_advance
        lda rbullet_x,x
        sta target_x
        lda rbullet_y,x
        sta target_y
        lda rbullet_dir,x
        jsr shot_step_target
        bcc update_remote_bullet_clear
        ldx rbullet_index
        lda target_x
        sta rbullet_x,x
        lda target_y
        sta rbullet_y,x
update_remote_bullet_check
        lda target_x
        cmp player_x
        bne update_remote_bullet_check_enemy
        lda target_y
        cmp player_y
        beq update_remote_bullet_clear
update_remote_bullet_check_enemy
        jsr find_enemy_at_target
        bne update_remote_bullet_clear
        jsr find_remote_at_target
        bne update_remote_bullet_clear
        jsr remote_bullet_hits_terrain
        bne update_remote_bullet_clear
        ldx rbullet_index
        inc rbullet_steps,x
        lda rbullet_steps,x
        cmp #PLAYER_BULLET_RANGE
        bcs update_remote_bullet_clear
        jsr draw_bullet_top_at_target
        ldx rbullet_index
        sta rbullet_drawn,x
        jmp update_remote_bullets_next
update_remote_bullet_clear
        ldx rbullet_index
        lda #0
        sta rbullet_active,x
        sta rbullet_drawn,x
update_remote_bullets_next
        inc rbullet_index
        jmp update_remote_bullets_loop

; NET_RT_WINDOW_ROW: one absolute terrain row of an in-band window resync.
; Self-describing: window origin = (origin_x, origin_y - row_index), so any
; row independently re-establishes the origin and a lost row costs only one
; stale row. Rows are staged into WORLD_PENDING and activated only after all
; rows arrive so collision/draw never sees a mixed-origin cache.
netstream_apply_window_row
        lda network_got_window
        bne netstream_window_row_ready
        rts
netstream_window_row_ready
        jmp netstream_window_row_route

netstream_apply_terrain_edge
; Only an in-progress row fill blocks relative edges (they would shift the
; window mid-fill). A pending resync must NOT block them: the server's
; small-gap repair IS relative edges replayed from our reported origin.
        lda net_row_fill_active
        beq netstream_terrain_edge_allowed
        rts
netstream_terrain_edge_allowed
; Phase 40: every edge is an acknowledged cache step carrying a 16-bit
; revision in the old reserved bytes. A retransmit of the step we already
; applied (the ACK was lost) is answered with a fresh ACK, never reapplied.
        lda net_realtime_packet+NET_RT_TERRAIN_REV_LO_OFFSET
        cmp net_cache_rev_lo
        bne netstream_terrain_rev_new
        lda net_realtime_packet+NET_RT_TERRAIN_REV_HI_OFFSET
        cmp net_cache_rev_hi
        bne netstream_terrain_rev_new
        jmp netstream_send_cache_step_ack
netstream_terrain_rev_new
        lda net_realtime_packet+NET_RT_TERRAIN_REV_LO_OFFSET
        sta net_cache_rev_pend_lo
        lda net_realtime_packet+NET_RT_TERRAIN_REV_HI_OFFSET
        sta net_cache_rev_pend_hi
        lda net_window_origin_x
        sta net_edge_prev_origin_x
        lda net_window_origin_y
        sta net_edge_prev_origin_y
        inc perf_terrain_packets
        lda RTCLOK
        sta perf_edge_clk_start
        lda net_realtime_packet+NET_RT_TERRAIN_ORIGIN_X_OFFSET
        sta net_packet_payload+2
        lda #0
        sta net_packet_payload+3
        lda net_realtime_packet+NET_RT_TERRAIN_ORIGIN_Y_OFFSET
        sta net_packet_payload+4
        lda #0
        sta net_packet_payload+5
        lda net_realtime_packet+NET_RT_TERRAIN_WIDTH_OFFSET
        sta net_packet_payload+6
        lda net_realtime_packet+NET_RT_TERRAIN_HEIGHT_OFFSET
        sta net_packet_payload+7
        lda #0
        sta net_packet_payload+8
        lda net_realtime_packet+NET_RT_TERRAIN_HEIGHT_OFFSET
        sta net_packet_payload+9
        lda net_realtime_packet+NET_RT_TERRAIN_WIDTH_OFFSET
        cmp #1
        bne netstream_terrain_not_column
        lda net_realtime_packet+NET_RT_TERRAIN_HEIGHT_OFFSET
        sta net_payload_offset
        jmp netstream_terrain_count_ok
netstream_terrain_not_column
        lda net_realtime_packet+NET_RT_TERRAIN_HEIGHT_OFFSET
        cmp #1
        bne netstream_terrain_done
        lda net_realtime_packet+NET_RT_TERRAIN_WIDTH_OFFSET
        sta net_payload_offset
netstream_terrain_count_ok
        ldx #0
netstream_terrain_copy_loop
        cpx net_payload_offset
        beq netstream_terrain_copy_done
        lda net_realtime_packet+NET_RT_TERRAIN_TILE_OFFSET,x
        sta net_packet_payload+NET_WINDOW_TILE_OFFSET,x
        inx
        jmp netstream_terrain_copy_loop
netstream_terrain_copy_done
        jsr net_apply_window_delta
        lda RTCLOK
        sec
        sbc perf_edge_clk_start
        cmp perf_edge_frames_max
        bcc netstream_terrain_perf_done
        sta perf_edge_frames_max
netstream_terrain_perf_done
; The shift routines move net_window_origin exactly when the step applied.
; Commit the step's revision and acknowledge; a rejected step leaves the
; origin unchanged (the desync flag already schedules the NACK resync).
        lda net_window_origin_x
        cmp net_edge_prev_origin_x
        bne netstream_terrain_step_applied
        lda net_window_origin_y
        cmp net_edge_prev_origin_y
        beq netstream_terrain_done
netstream_terrain_step_applied
        lda net_cache_rev_pend_lo
        sta net_cache_rev_lo
        lda net_cache_rev_pend_hi
        sta net_cache_rev_hi
        jmp netstream_send_cache_step_ack
netstream_terrain_done
        rts

correction_echo_ready
        lda net_predicted_move_pending
        bne correction_echo_check
        sec
        rts
correction_echo_check
        lda net_realtime_packet+NET_RT_WORLD_ECHO_SEQ_HI_OFFSET
        cmp net_predicted_move_seq_hi
        bne correction_echo_hi_diff
        lda net_realtime_packet+NET_RT_WORLD_ECHO_SEQ_LO_OFFSET
        cmp net_predicted_move_seq_lo
        bcs correction_echo_ready_yes
        clc
        rts
correction_echo_hi_diff
        bcs correction_echo_ready_yes
        clc
        rts
correction_echo_ready_yes
        sec
        rts

queue_or_apply_player_correction
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET
        cmp player_x
        beq correction_x_same
        bcc correction_x_left
        sec
        sbc player_x
        cmp #2
        bcs correction_snap_now
        jmp correction_check_y
correction_x_left
        lda player_x
        sec
        sbc net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET
        cmp #2
        bcs correction_snap_now
correction_check_y
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET+1
        cmp player_y
        beq correction_queue
        bcc correction_y_up
        sec
        sbc player_y
        cmp #2
        bcs correction_snap_now
        jmp correction_queue
correction_y_up
        lda player_y
        sec
        sbc net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET+1
        cmp #2
        bcs correction_snap_now
correction_queue
        jsr correction_echo_ready
        bcc correction_defer
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET
        sta net_player_correction_x
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET+1
        sta net_player_correction_y
        lda #1
        sta net_player_correction_pending
        rts
correction_defer
        lda #0
        sta net_player_correction_pending
        rts
correction_snap_now
        lda #0
        sta net_player_correction_pending
        sta net_predicted_move_pending
        lda #1
        sta net_world_changed
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET
        sta player_x
        lda net_realtime_packet+NET_RT_WORLD_PAYLOAD_OFFSET+1
        sta player_y
        rts
correction_x_same
correction_queue_y_only
        jmp correction_check_y

apply_pending_player_correction
        lda net_player_correction_pending
        bne apply_player_correction_now
        rts
apply_player_correction_now
        lda player_x
        cmp net_player_correction_x
        beq apply_player_correction_y
        bcc apply_player_correction_inc_x
        dec player_x
        jsr net_update_view_position
        lda #1
        sta net_screen_dirty
        rts
apply_player_correction_inc_x
        inc player_x
        jsr net_update_view_position
        lda #1
        sta net_screen_dirty
        rts
apply_player_correction_y
        lda player_y
        cmp net_player_correction_y
        beq apply_player_correction_done
        bcc apply_player_correction_inc_y
        dec player_y
        jsr net_update_view_position
        lda #1
        sta net_screen_dirty
        rts
apply_player_correction_inc_y
        inc player_y
        jsr net_update_view_position
        lda #1
        sta net_screen_dirty
        rts
apply_player_correction_done
        lda #0
        sta net_player_correction_pending
        sta net_predicted_move_pending
        rts

netstream_send_packet_byte
        pha
        clc
        adc net_send_checksum
        sta net_send_checksum
        pla
        jsr netstream_send_raw_byte
        rts

netstream_send_raw_byte
        sta net_send_byte
        lda #20
        sta net_send_retry
netstream_send_raw_retry
        lda net_send_byte
        jsr NETSTREAM_SEND_BYTE
        cmp #0
        beq netstream_send_raw_ok
        jsr wait_frame_tick
        dec net_send_retry
        bne netstream_send_raw_retry
        sec
        rts
netstream_send_raw_ok
        clc
        rts

netstream_recv_packets
        lda network_enabled
        bne netstream_recv_enabled
        rts
netstream_recv_enabled
        lda #128
        sta net_recv_budget
netstream_recv_loop
        jsr NETSTREAM_BYTES_AVAIL
        cpx #0
        bne netstream_recv_have_byte
        cmp #0
        bne netstream_recv_have_byte
        jsr netstream_recv_finish
        rts
netstream_recv_have_byte
        jsr NETSTREAM_RECV_BYTE
        jsr netstream_parse_byte
        dec net_recv_budget
        bne netstream_recv_loop
        jsr netstream_recv_finish
        rts

netstream_recv_finish
        lda net_snapshot_pending
        beq netstream_recv_draw
        lda #0
        sta net_snapshot_pending
        ldx #0
netstream_recv_copy_snapshot
        lda net_snapshot_payload,x
        sta net_packet_payload,x
        inx
        cpx #NET_SNAPSHOT_PAYLOAD_LEN
        bne netstream_recv_copy_snapshot
        lda #NET_SNAPSHOT_PAYLOAD_LEN
        sta net_packet_len
        jsr net_apply_snapshot
netstream_recv_draw
        lda net_snapshot_dirty
        beq netstream_recv_finish_done
        lda #0
        sta net_snapshot_dirty
        inc perf_full_redraws
        jsr draw_scrolled_frame_buffered
netstream_recv_finish_done
        rts

netstream_parse_byte
        sta net_rx_byte
        lda net_parser_state
        beq net_parse_magic
        lda net_rx_byte
        cmp #NET_PACKET_MAGIC
        bne net_parse_dispatch
        jmp net_parse_mid_magic_resync
net_parse_dispatch
        lda net_parser_state
        cmp #1
        beq net_parse_version
        cmp #2
        beq net_parse_type
        cmp #3
        beq net_parse_len
        cmp #4
        beq net_parse_payload_jump
        jmp net_parse_checksum
net_parse_payload_jump
        jmp net_parse_payload
net_parse_magic
        lda net_rx_byte
        cmp #NET_PACKET_MAGIC
        beq net_parse_magic_ok
        rts
net_parse_magic_ok
        sta net_parser_checksum
        lda #1
        sta net_parser_state
        rts
net_parse_version
        lda net_rx_byte
        cmp #NETSTREAM_PROTOCOL_VERSION
        beq net_parse_version_ok
        lda #0
        sta net_parser_state
        rts
net_parse_version_ok
        jsr net_parse_add_checksum
        lda #2
        sta net_parser_state
        rts
net_parse_type
        lda net_rx_byte
        sta net_packet_type
        jsr net_parse_add_checksum
        lda #3
        sta net_parser_state
        rts
net_parse_len
        lda net_rx_byte
        sta net_packet_len
        lda #0
        sta net_parser_index
        jsr net_parse_add_checksum
        jsr net_parse_len_valid
        bcs net_parse_reset_drop
net_parse_len_ok
        lda net_packet_len
        beq net_parse_payload_done
        lda #4
        sta net_parser_state
        rts
net_parse_payload
        ldx net_parser_index
        cpx #NET_PACKET_MAX_PAYLOAD
        bcs net_parse_payload_skip_store
        lda net_rx_byte
        sta net_packet_payload,x
net_parse_payload_skip_store
        inc net_parser_index
        jsr net_parse_add_checksum
        lda net_parser_index
        cmp net_packet_len
        beq net_parse_payload_done
        rts
net_parse_payload_done
        lda #5
        sta net_parser_state
        rts
net_parse_checksum
        lda net_rx_byte
        cmp net_parser_checksum
        beq net_parse_packet_ok
        inc net_rx_drops
net_parse_reset
        lda #0
        sta net_parser_state
        rts
net_parse_reset_drop
        inc net_rx_drops
        jmp net_parse_reset
net_parse_packet_ok
        lda #0
        sta net_parser_state
        lda net_packet_type
        cmp #NET_PKT_WELCOME
        beq net_apply_welcome
        cmp #NET_PKT_WINDOW
        beq net_apply_window
        cmp #NET_PKT_SNAPSHOT
        beq net_dispatch_snapshot
        rts
net_dispatch_snapshot
        jmp net_store_snapshot

net_parse_add_checksum
        lda net_rx_byte
        clc
        adc net_parser_checksum
        sta net_parser_checksum
        rts

net_apply_welcome
        lda net_packet_payload+1
        sta net_seed_lo
        lda net_packet_payload+2
        sta net_seed_hi
        lda #1
        sta network_got_welcome
        rts

net_store_snapshot
        lda net_packet_len
        cmp #NET_SNAPSHOT_PAYLOAD_LEN
        beq net_store_snapshot_len_ok
        rts
net_store_snapshot_len_ok
        ldx #0
net_store_snapshot_loop
        lda net_packet_payload,x
        sta net_snapshot_payload,x
        inx
        cpx #NET_SNAPSHOT_PAYLOAD_LEN
        bne net_store_snapshot_loop
        lda #1
        sta net_snapshot_pending
        rts

net_apply_window
        lda net_packet_len
        cmp #NET_WINDOW_HEAD_LEN
        bcs net_apply_window_len_ok
        rts
net_apply_window_len_ok
        lda net_packet_payload+2
        sta net_pending_origin_x
        lda net_packet_payload+3
        sta net_pending_origin_x_hi
        lda net_packet_payload+4
        sta net_pending_origin_y
        lda net_packet_payload+5
        sta net_pending_origin_y_hi
        lda net_packet_payload+6
        cmp #NET_WINDOW_W
        beq net_apply_window_width_ok
        jmp net_apply_window_delta
net_apply_window_width_ok
        lda net_packet_payload+7
        cmp #NET_WINDOW_H
        beq net_apply_window_height_ok
        jmp net_apply_window_delta
net_apply_window_height_ok
        lda net_packet_payload+8
        sta net_window_chunk_y
        bne net_apply_window_continue
        lda #0
        sta net_window_rows_loaded
net_apply_window_continue
        lda net_packet_payload+9
        sta net_window_chunk_h
        beq net_apply_window_done
        clc
        adc net_window_chunk_y
        cmp #NET_WINDOW_H+1
        bcc net_apply_window_range_ok
        rts
net_apply_window_range_ok
        lda #0
        sta net_window_row
        sta net_window_col
        lda #NET_WINDOW_TILE_OFFSET
        sta net_payload_offset
net_apply_window_loop
        lda net_window_chunk_y
        clc
        adc net_window_row
        sta cache_local_y
        lda cache_local_y
        lsr
        clc
        adc cache_pending_hi
        sta ptr+1
        lda cache_local_y
        and #1
        beq net_apply_window_even_row
        lda #$80
        jmp net_apply_window_low_done
net_apply_window_even_row
        lda #0
net_apply_window_low_done
        clc
        adc net_window_col
        sta ptr
        ldy #0
        ldx net_payload_offset
        lda net_packet_payload,x
        sta (ptr),y
        inc net_payload_offset
        inc net_window_col
        lda net_window_col
        cmp #NET_WINDOW_W
        bne net_apply_window_loop
        lda #0
        sta net_window_col
        inc net_window_row
        lda net_window_row
        cmp net_window_chunk_h
        bne net_apply_window_loop
        lda net_window_rows_loaded
        clc
        adc net_window_chunk_h
        sta net_window_rows_loaded
        cmp #NET_WINDOW_H
        bcc net_apply_window_done
        jsr net_activate_pending_window
net_apply_window_done
        rts

net_activate_pending_window
        lda net_pending_origin_x
        sta net_window_origin_x
        lda net_pending_origin_x_hi
        sta net_window_origin_x_hi
        lda net_pending_origin_y
        sta net_window_origin_y
        lda net_pending_origin_y_hi
        sta net_window_origin_y_hi
        lda cache_active_hi
        pha
        lda cache_pending_hi
        sta cache_active_hi
        pla
        sta cache_pending_hi
        lda #1
        sta network_got_window
        rts

net_apply_window_delta
        lda network_got_window
        bne net_apply_window_delta_ready
        rts
net_apply_window_delta_ready
        lda net_packet_payload+6
        cmp #1
        bne net_delta_not_column
        lda net_packet_payload+7
        cmp #NET_WINDOW_H
        bne net_apply_window_done
        lda net_packet_payload+2
        sec
        sbc net_window_origin_x
        cmp #NET_WINDOW_W
        bne net_delta_column_left
        jsr net_shift_cache_left
        inc net_window_origin_x
        jmp net_delta_shift_applied
net_delta_column_left
        lda net_packet_payload+2
        clc
        adc #1
        cmp net_window_origin_x
        bne net_delta_flag_desync
        jsr net_shift_cache_right
        dec net_window_origin_x
        jmp net_delta_shift_applied
net_delta_not_column
        lda net_packet_payload+6
        cmp #NET_WINDOW_W
        bne net_apply_window_done
        lda net_packet_payload+7
        cmp #1
        bne net_apply_window_done
        lda net_packet_payload+4
        sec
        sbc net_window_origin_y
        cmp #NET_WINDOW_H
        bne net_delta_row_up
        jsr net_shift_cache_up
        inc net_window_origin_y
        jmp net_delta_shift_applied
net_delta_row_up
        lda net_packet_payload+4
        clc
        adc #1
        cmp net_window_origin_y
        beq net_delta_row_up_ok
        jmp net_delta_flag_desync
net_delta_row_up_ok
        jsr net_shift_cache_down
        dec net_window_origin_y
        jmp net_delta_shift_applied

; A well-formed edge strip that is not adjacent to our window origin means
; an earlier edge was lost (firmware ring overflow, etc). The server's copy
; of the window has moved on, so every future edge would be rejected too and
; the window would stay frozen (invisible walls). Flag it; main_loop sends an
; in-band RESYNC_REQUEST for a fresh window. Suppressed while a resync is
; already pending so stale in-flight edges cannot re-trigger.
net_delta_flag_desync
; With pipelined cache steps (go-back-N), a non-adjacent step means an
; earlier step in the pipeline died and its followers arrived first. Do
; not apply it -- instead re-ACK our applied revision and origin (a
; duplicate ACK). The server fast-retransmits the pipeline on a duplicate
; ACK, so loss recovery costs one round trip instead of the 0.5 s
; retransmit timer -- the difference between a stall and a blip on the
; lossy real-hardware serial link.
        jmp netstream_send_cache_step_ack

; An adjacent edge shift is being applied: if a resync was pending, the
; server's edge replay has reached us -- recovery complete. (Falls through
; into the patch writer. WINDOW_ROW fills call net_apply_window_patch
; directly and manage their own pending state.)
net_delta_shift_applied
        lda #0
        sta net_resync_pending
net_apply_window_patch
        lda #0
        sta net_window_row
        sta net_window_col
        lda #NET_WINDOW_TILE_OFFSET
        sta net_payload_offset
net_apply_window_patch_loop
        lda net_packet_payload+2
        clc
        adc net_window_col
        sta target_x
        lda net_packet_payload+4
        clc
        adc net_window_row
        sta target_y
        jsr world_cell_ptr
        lda cache_ptr_valid
        beq net_apply_window_patch_skip
        ldy #0
        ldx net_payload_offset
        lda net_packet_payload,x
        sta (ptr),y
        lda net_map_fill_pending
        bne net_apply_window_patch_skip
        jsr draw_target_world_cell
net_apply_window_patch_skip
        inc net_payload_offset
        inc net_window_col
        lda net_window_col
        cmp net_packet_payload+6
        bne net_apply_window_patch_loop
        lda #0
        sta net_window_col
        inc net_window_row
        lda net_window_row
        cmp net_packet_payload+9
        bne net_apply_window_patch_loop
        rts

net_cache_ptr_to_wptr
        jsr world_cell_ptr_cache
        lda ptr
        sta wptr
        lda ptr+1
        sta wptr+1
        rts

; Phase 5.5 Step 2: cache rows are contiguous 32-byte runs (two per page at
; low-byte $00/$80), so each shift computes one row base pointer per row and
; copies with a tight indexed loop instead of two world_cell_ptr_cache calls
; per byte. Copy direction preserves in-row overlap correctness.

; Camera moved right: copy columns 1..31 to 0..30 (dst < src: ascend Y).
net_shift_cache_left
        lda #0
        sta net_window_row
net_shift_left_row
        lda net_window_row
        sta cache_local_y
        lda #0
        sta cache_local_x
        jsr world_cell_ptr_cache   ; ptr = row base (column 0) = dest
        lda ptr
        clc
        adc #1
        sta wptr                   ; wptr = row base + 1 (column 1) = source
        lda ptr+1
        adc #0
        sta wptr+1
        ldy #0
net_shift_left_copy
        lda (wptr),y
        sta (ptr),y
        iny
        cpy #NET_WINDOW_W-1
        bne net_shift_left_copy
        inc net_window_row
        lda net_window_row
        cmp #NET_WINDOW_H
        bne net_shift_left_row
        rts

; Camera moved left: copy columns 30..0 to 31..1 (dst > src: descend Y).
net_shift_cache_right
        lda #0
        sta net_window_row
net_shift_right_row
        lda net_window_row
        sta cache_local_y
        lda #0
        sta cache_local_x
        jsr world_cell_ptr_cache   ; ptr = row base (column 0) = source
        lda ptr
        clc
        adc #1
        sta wptr                   ; wptr = row base + 1 (column 1) = dest
        lda ptr+1
        adc #0
        sta wptr+1
        ldy #NET_WINDOW_W-2
net_shift_right_copy
        lda (ptr),y
        sta (wptr),y
        dey
        bpl net_shift_right_copy
        inc net_window_row
        lda net_window_row
        cmp #NET_WINDOW_H
        bne net_shift_right_row
        rts

; Camera moved down: copy rows 1..23 to rows 0..22 (ascend rows).
net_shift_cache_up
        lda #0
        sta net_window_row
net_shift_up_row
        lda net_window_row
        clc
        adc #1
        sta cache_local_y
        lda #0
        sta cache_local_x
        jsr net_cache_ptr_to_wptr  ; wptr = source row base (row + 1)
        lda net_window_row
        sta cache_local_y
        jsr world_cell_ptr_cache   ; ptr = dest row base (row)
        ldy #0
net_shift_up_copy
        lda (wptr),y
        sta (ptr),y
        iny
        cpy #NET_WINDOW_W
        bne net_shift_up_copy
        inc net_window_row
        lda net_window_row
        cmp #NET_WINDOW_H-1
        bne net_shift_up_row
        rts

; Camera moved up: copy rows 22..0 to rows 23..1 (descend rows).
net_shift_cache_down
        lda #NET_WINDOW_H-1
        sta net_window_row
net_shift_down_row
        lda net_window_row
        sec
        sbc #1
        sta cache_local_y
        lda #0
        sta cache_local_x
        jsr net_cache_ptr_to_wptr  ; wptr = source row base (row - 1)
        lda net_window_row
        sta cache_local_y
        jsr world_cell_ptr_cache   ; ptr = dest row base (row)
        ldy #0
net_shift_down_copy
        lda (wptr),y
        sta (ptr),y
        iny
        cpy #NET_WINDOW_W
        bne net_shift_down_copy
        dec net_window_row
        lda net_window_row
        bne net_shift_down_row
        rts

net_apply_snapshot
        lda net_packet_len
        cmp #NET_SNAPSHOT_PAYLOAD_LEN
        beq net_apply_snapshot_len_ok
        rts
net_apply_snapshot_len_ok
        lda net_packet_payload+2
        cmp net_window_origin_x
        bcc net_apply_snapshot_done
        sec
        sbc net_window_origin_x
        cmp #NET_WINDOW_W
        bcs net_apply_snapshot_done
        lda net_packet_payload+3
        cmp net_window_origin_y
        bcc net_apply_snapshot_done
        sec
        sbc net_window_origin_y
        cmp #NET_WINDOW_H
        bcs net_apply_snapshot_done
        lda net_packet_payload
        sta net_ack_tick_lo
        lda net_packet_payload+1
        sta net_ack_tick_hi
        lda player_x
        sta old_player_x
        lda player_y
        sta old_player_y
        lda net_packet_payload+2
        sta player_x
        lda net_packet_payload+3
        sta player_y
        lda net_packet_payload+4
        sta player_health
        jsr net_apply_tile_update
        jsr net_clear_enemy_tiles
        lda net_packet_payload+7
        cmp #NET_MAX_BEAVERS+1
        bcc net_snapshot_count_ok
        lda #NET_MAX_BEAVERS
net_snapshot_count_ok
        sta active_beaver_count
        jsr net_apply_beavers
        jsr net_update_view_position
        inc perf_snapshot_dirty_sets
        lda #1
        sta net_snapshot_dirty
net_apply_snapshot_done
        rts

net_apply_tile_update
        ; Server tile updates are terrain-only. Dynamic entities must stay in
        ; entity arrays and be rendered as screen overlays.
        lda net_packet_payload+20
        ora net_packet_payload+21
        beq net_apply_tile_done
        lda net_packet_payload+20
        sta target_x
        lda net_packet_payload+21
        sta target_y
        jsr world_cell_ptr
        lda cache_ptr_valid
        beq net_apply_tile_done
        ldy #0
        lda net_packet_payload+22
        sta (ptr),y
net_apply_tile_done
        rts

net_update_view_position
        lda view_x
        sta old_view_x
        lda view_y
        sta old_view_y
        lda player_x
        sec
        sbc view_x
; A borrow means the player is left of the view origin entirely (large
; position jump, e.g. a map-change spawn). The unsigned compare below
; would misread the negative diff as "far right" and scroll AWAY from
; the player, pinning the view at the window's right edge.
        bcc net_view_scroll_left
        cmp #SCROLL_LEFT_EDGE
        bcs net_check_view_right
net_view_scroll_left
        lda view_x
        beq net_check_view_y
        dec view_x
        jmp net_check_view_y
net_check_view_right
        cmp #SCROLL_RIGHT_EDGE+1
        bcc net_check_view_y
        lda view_x
        cmp #VIEW_MAX_X
        beq net_check_view_y
        inc view_x
net_check_view_y
        lda player_y
        sec
        sbc view_y
        bcc net_view_scroll_up
        cmp #SCROLL_TOP_EDGE
        bcs net_check_view_down
net_view_scroll_up
        lda view_y
        beq net_clamp_view
        dec view_y
        jmp net_clamp_view
net_check_view_down
        cmp #SCROLL_BOTTOM_EDGE+1
        bcc net_clamp_view
        lda view_y
        cmp #VIEW_MAX_Y
        beq net_clamp_view
        inc view_y
net_clamp_view
        lda view_x
        cmp net_window_origin_x
        bcs net_clamp_view_x_high
        lda net_window_origin_x
        sta view_x
net_clamp_view_x_high
        lda net_window_origin_x
        clc
        adc #NET_VIEW_MAX_OFFSET_X
        cmp view_x
        bcs net_clamp_view_y_low
        sta view_x
net_clamp_view_y_low
        lda view_y
        cmp net_window_origin_y
        bcs net_clamp_view_y_high
        lda net_window_origin_y
        sta view_y
net_clamp_view_y_high
        lda net_window_origin_y
        clc
        adc #NET_VIEW_MAX_OFFSET_Y
        cmp view_y
        bcs net_update_view_done
        sta view_y
net_update_view_done
        lda view_x
        cmp old_view_x
        bne net_update_view_scrolled
        lda view_y
        cmp old_view_y
        bne net_update_view_scrolled
        rts
net_update_view_scrolled
        inc perf_scroll_dirty_sets
        lda #1
        sta net_scroll_dirty
        rts

net_capture_enemy_cells
        ldx #0
net_capture_enemy_loop
        cpx #BEAVER_MAX_COUNT
        beq net_capture_enemy_done
        lda enemy_x,x
        sta old_enemy_x,x
        lda enemy_y,x
        sta old_enemy_y,x
        lda enemy_alive,x
        sta old_enemy_alive,x
        lda enemy_kind,x
        sta old_enemy_kind,x
        inx
        jmp net_capture_enemy_loop
net_capture_enemy_done
; Remote-player slots ride the same capture/restore cycle as enemy slots.
        ldx #0
net_capture_remote_loop
        cpx #NET_MAX_REMOTE_PLAYERS
        beq net_capture_remote_done
        lda remote_x,x
        sta old_remote_x,x
        lda remote_y,x
        sta old_remote_y,x
        lda remote_alive,x
        sta old_remote_alive,x
        inx
        jmp net_capture_remote_loop
net_capture_remote_done
; Item-drop slots ride the same capture/restore cycle (Phase 14b); the loop
; body lives with the rest of the item-drop overlay code near $8000 (see
; net_capture_item_cells), which has ample free space unlike this segment.
        jmp net_capture_item_cells

; Historical name. Network enemies are dynamic overlays, not terrain.
; Capture old cells separately, then clear only enemy state arrays here.
net_clear_enemy_tiles
        ldx #0
net_clear_enemy_loop
        cpx #BEAVER_MAX_COUNT
        beq net_clear_enemy_done
        lda #0
        sta enemy_alive,x
        sta enemy_kind,x
        inx
        jmp net_clear_enemy_loop
net_clear_enemy_done
        rts

net_apply_beavers
        ldx #0
        stx beavers_left
        lda #8
        sta net_payload_offset
net_apply_beaver_loop
        cpx active_beaver_count
        beq net_apply_beaver_done
        ldy net_payload_offset
        lda net_packet_payload,y
        sta enemy_x,x
        iny
        lda net_packet_payload,y
        sta enemy_y,x
        iny
        lda net_packet_payload,y
        sta enemy_hp,x
        iny
        lda net_packet_payload,y
        pha
        and #ENEMY_KIND_MASK
        sta enemy_kind,x
        pla
        and #ENEMY_HIT_BIT
        beq net_apply_beaver_no_hit
        lda #ENEMY_HIT_FLASH_FRAMES
        sta enemy_hit_timer,x
net_apply_beaver_no_hit
        lda enemy_hp,x
        bne net_apply_beaver_live
        lda #0
        sta enemy_alive,x
        jmp net_apply_beaver_next
net_apply_beaver_live
        lda #1
        sta enemy_alive,x
        inc beavers_left
net_apply_beaver_next
        lda net_payload_offset
        clc
        adc #4
        sta net_payload_offset
        inx
        jmp net_apply_beaver_loop
net_apply_beaver_done
        rts

show_netstream_screen
        jsr init_sound
        jsr wait_frame_tick
        ldx #<display_list_text
        ldy #>display_list_text
        lda #OS_FONT_PAGE
        jsr apply_display_now
        jsr init_screen_buffers
        jsr set_text_palette
        jsr clear_screen
        jsr draw_text_lines
        rts

show_netstream_result_screen
        jsr show_netstream_screen
        jsr wait_transition_delay
        rts

read_controls_realtime
        lda #0
        sta input_dir
        sta input_buttons
; PIA/GTIA hardware, not the STICK0/STRIG0 shadows: the shadows are only
; refreshed by the stage-2 VBI, which CRITIC=1 suppresses during realtime
; play (see the CRITIC equate note). Same nibble layout and polarity.
        lda PORTA
        and #$0f
        sta input_stick_raw
; SPACE is handled independently inside read_keyboard_realtime_actions
; (edge-triggered, fires once in the player's current facing direction) --
; it does not participate in this joystick-only direction+trigger check,
; since the keyboard can't reliably report a WASD key and SPACE held down
; at the same time (single key-latch hardware).
        jsr read_keyboard_realtime_actions
        jsr read_keyboard_stick
        and input_stick_raw
        sta input_stick_raw
        lda TRIG0
        bne read_controls_realtime_strig0_up
; The joystick trigger also acts like RETURN: on the fresh press (not
; every frame it's held), also nudge net_pickup_counter, the same signal
; RETURN uses -- the server already knows whether that means "pick up a
; nearby item" or "talk to an adjacent NPC," so pressing fire next to an
; NPC starts/advances the conversation instead of doing nothing.
        lda strig0_repeat_latch
        bne read_controls_realtime_fire
        lda #1
        sta strig0_repeat_latch
        inc net_pickup_counter
        jmp read_controls_realtime_fire
read_controls_realtime_strig0_up
        lda #0
        sta strig0_repeat_latch
        jmp read_controls_realtime_move
read_controls_realtime_fire
        jsr aim_and_fire
        rts
read_controls_realtime_move
        lda #0
        sta fire_latch
        lda RTCLOK
        sec
        sbc lastclk
        cmp #NET_REALTIME_MOVE_DELAY
        bcs realtime_move_delay_ok
        rts
realtime_move_delay_ok
        lda input_stick_raw
        cmp #15
        bne realtime_move_not_neutral
        jmp read_controls_realtime_neutral
realtime_move_not_neutral
        lda RTCLOK
        sta lastclk
        lda input_stick_raw
        cmp #$0a
        bne realtime_not_up_left
        sta input_dir
        jsr realtime_gate_move_repeat
        bcs realtime_up_left_allowed
        rts
realtime_up_left_allowed
        jsr realtime_check_up_left
        bcs realtime_up_left_move
        rts
realtime_up_left_move
        jsr try_up
        jsr try_left
        jmp move_anim_toggle
realtime_not_up_left
        cmp #$06
        bne realtime_not_up_right
        sta input_dir
        jsr realtime_gate_move_repeat
        bcs realtime_up_right_allowed
        rts
realtime_up_right_allowed
        jsr realtime_check_up_right
        bcs realtime_up_right_move
        rts
realtime_up_right_move
        jsr try_up
        jsr try_right
        jmp move_anim_toggle
realtime_not_up_right
        cmp #$09
        bne realtime_not_down_left
        sta input_dir
        jsr realtime_gate_move_repeat
        bcs realtime_down_left_allowed
        rts
realtime_down_left_allowed
        jsr realtime_check_down_left
        bcs realtime_down_left_move
        rts
realtime_down_left_move
        jsr try_down
        jsr try_left
        jmp move_anim_toggle
realtime_not_down_left
        cmp #$05
        bne realtime_not_down_right
        sta input_dir
        jsr realtime_gate_move_repeat
        bcs realtime_down_right_allowed
        rts
realtime_down_right_allowed
        jsr realtime_check_down_right
        bcs realtime_down_right_move
        rts
realtime_down_right_move
        jsr try_down
        jsr try_right
        jmp move_anim_toggle
realtime_not_down_right
        and #1
        bne realtime_not_up
        lda #DIR_UP
        sta aim_dir
        sta last_cardinal_aim
        lda #NET_DIR_UP
        sta input_dir
        jsr realtime_gate_move_repeat
        bcc read_controls_realtime_done
        jsr try_up
        rts
realtime_not_up
        lda input_stick_raw
        and #2
        bne realtime_not_down
        lda #DIR_DOWN
        sta aim_dir
        sta last_cardinal_aim
        lda #NET_DIR_DOWN
        sta input_dir
        jsr realtime_gate_move_repeat
        bcc read_controls_realtime_done
        jsr try_down
        rts
realtime_not_down
        lda input_stick_raw
        and #4
        bne realtime_not_left
        lda #DIR_LEFT
        sta aim_dir
        sta last_cardinal_aim
        lda #NET_DIR_LEFT
        sta input_dir
        jsr realtime_gate_move_repeat
        bcc read_controls_realtime_done
        jsr try_left
        rts
realtime_not_left
        lda input_stick_raw
        and #8
        bne read_controls_realtime_done
        lda #DIR_RIGHT
        sta aim_dir
        sta last_cardinal_aim
        lda #NET_DIR_RIGHT
        sta input_dir
        jsr realtime_gate_move_repeat
        bcc read_controls_realtime_done
        jsr try_right
        rts
read_controls_realtime_neutral
        jsr realtime_reset_move_repeat
read_controls_realtime_done
        rts

realtime_reset_move_repeat
        lda #NET_DIR_NONE
        sta net_move_repeat_dir
        lda #0
        sta net_move_repeat_clk
        rts

realtime_gate_move_repeat
        lda input_dir
        cmp net_move_repeat_dir
        bne realtime_gate_move_allow
        lda RTCLOK
        sec
        sbc net_move_repeat_clk
        cmp net_move_repeat_cfg
        bcs realtime_gate_move_allow
        clc
        rts
realtime_gate_move_allow
        lda input_dir
        sta net_move_repeat_dir
        lda RTCLOK
        sta net_move_repeat_clk
        sec
        rts

; One BULLET_DELAY-gated step per call, so the bullet actually travels
; visibly across the frames it takes to cross the map instead of
; resolving its whole flight (up to PLAYER_BULLET_RANGE cells) within a
; single call before that frame is ever presented. spawn_bullet_visual's
; own bullet_clk priming still makes the very first cell draw immediately
; on firing; every step after that is paced for real by update_bullet.
update_network_bullet_fast
        jmp update_bullet

update_bullet
        lda bullet_active
        bne bullet_active_now
        rts
bullet_active_now
        lda RTCLOK
        sec
        sbc bullet_clk
        cmp #BULLET_DELAY
        bcs bullet_time_ok
        rts
bullet_time_ok
        lda RTCLOK
        sta bullet_clk

        lda bullet_drawn
        beq bullet_skip_erase
        jsr erase_bullet
bullet_skip_erase
        lda bullet_x
        sta target_x
        lda bullet_y
        sta target_y
        lda bullet_dir
        jsr shot_step_target
        bcc bullet_clear
        lda target_x
        sta bullet_x
        lda target_y
        sta bullet_y
bullet_check
        jsr find_enemy_at_target
        bne bullet_hit_enemy
        jsr find_remote_at_target
        bne bullet_hit_enemy
        jsr bullet_target_hits_terrain
        bne bullet_clear
        inc bullet_steps
        lda bullet_steps
        cmp #PLAYER_BULLET_RANGE
        bcs bullet_clear
        jsr draw_bullet
bullet_done
        rts
bullet_hit_enemy
bullet_clear
        lda #0
        sta bullet_active
        sta bullet_drawn
        rts

try_up
        lda player_y
        cmp #1
        beq move_done
        sta target_y
        dec target_y
        lda player_x
        sta target_x
        jsr move_if_clear
        rts

try_down
        lda player_y
        cmp #94
        beq move_done
        sta target_y
        inc target_y
        lda player_x
        sta target_x
        jsr move_if_clear
        rts

try_left
        lda player_x
        cmp #1
        beq move_done
        sta target_x
        dec target_x
        lda player_y
        sta target_y
        jsr move_if_clear
        rts

try_right
        lda player_x
        cmp #126
        beq move_done
        sta target_x
        inc target_x
        lda player_y
        sta target_y
        jsr move_if_clear
move_done
        rts

move_if_clear
        jsr world_cell_ptr
        ldy #0
        lda (ptr),y
        cmp #TREE_FULL
        bne move_not_tree_full
        jmp blocked
move_not_tree_full
        cmp #TREE_DAMAGED
        bne move_not_tree_damaged
        jmp blocked
move_not_tree_damaged
        cmp #BULLET
        beq blocked
        cmp #BORDER
        beq blocked
        cmp #BEAVER
        beq blocked
; Phase 8 blocking terrain: must match the server's PLAYER_BLOCKING set
; (world.py) or the client predicts into walls and the server correction
; rubber-bands the player back out every step.
        cmp #TILE_WATER
        beq blocked
        cmp #TILE_BUILDING
        beq blocked
        cmp #TILE_CAVE_WALL
        beq blocked
        cmp #TILE_FARMER
        beq blocked
        cmp #TILE_GOBLIN_NPC
        beq blocked
        lda network_realtime_enabled
        beq move_check_herb
        jsr find_enemy_at_target
        bne blocked
; Remote players block too; predicting through them would only be
; rubber-banded back by the server correction.
        jsr find_remote_at_target
        bne blocked

move_check_herb
        jsr world_cell_ptr
        ldy #0
        lda (ptr),y
        cmp #HERB
        bne move_clear
        lda player_health
        cmp player_max_health
        bcs herb_health_done
        inc player_health
herb_health_done
        lda #GRASS
        sta (ptr),y
        jsr redraw_hud_hearts

move_clear
move_anim_toggle
        lda player_anim
        eor #1
        sta player_anim
        lda target_x
        sta player_x
        lda target_y
        sta player_y
        lda #0
        sta net_player_correction_pending
        lda #1
        sta net_prediction_send_pending
        lda RTCLOK
        sec
        sbc #NET_REALTIME_SEND_DELAY
        sta net_realtime_send_clk
        jsr net_update_view_position
        inc perf_screen_dirty_sets
        lda #1
        sta net_screen_dirty
        rts
blocked
        rts

seed_network_rng
        lda net_seed_lo
        ora net_seed_hi
        bne seed_network_rng_ok
        lda #1
        sta net_seed_lo
seed_network_rng_ok
        lda net_seed_lo
        sta net_rng_lo
        lda net_seed_hi
        sta net_rng_hi
        rts

draw_seeded_trees
        ldx #TREE_COUNT
seeded_tree_loop
        jsr seeded_random_cell
        jsr world_cell_ptr
        ldy #0
        lda (ptr),y
        cmp #GRASS
        bne seeded_tree_loop
        lda #TREE_FULL
        sta (ptr),y
        dex
        bne seeded_tree_loop
        rts

draw_seeded_herbs
        ldx #HERB_COUNT
seeded_herb_loop
        jsr seeded_random_cell
        jsr world_cell_ptr
        ldy #0
        lda (ptr),y
        cmp #GRASS
        bne seeded_herb_loop
        lda #HERB
        sta (ptr),y
        dex
        bne seeded_herb_loop
        rts

seeded_random_cell
        jsr seeded_random_x
        jsr seeded_random_y
        lda target_x
        cmp #10
        beq seeded_random_cell_check_left
        cmp #11
        bne seeded_random_cell_done
        lda target_y
        cmp #10
        beq seeded_random_cell
        jmp seeded_random_cell_done
seeded_random_cell_check_left
        lda target_y
        cmp #10
        beq seeded_random_cell
        cmp #11
        beq seeded_random_cell
seeded_random_cell_done
        rts

seeded_random_x
        jsr seeded_next_byte
        and #$7f
        cmp #126
        bcs seeded_random_x
        clc
        adc #1
        sta target_x
        rts

seeded_random_y
        jsr seeded_next_byte
        and #$7f
        cmp #94
        bcs seeded_random_y
        clc
        adc #1
        sta target_y
        rts

seeded_next_byte
        lda net_rng_hi
        lsr
        sta net_rng_hi
        lda net_rng_lo
        ror
        sta net_rng_lo
        bcc seeded_next_no_feedback
        lda net_rng_hi
        eor #$b4
        sta net_rng_hi
seeded_next_no_feedback
        lda net_rng_hi
        rts

draw_player
        lda player_x
        sta target_x
        lda player_y
        sta target_y
        jsr target_in_view
        beq draw_player_done
        jsr select_player_tile
        jsr draw_player_sprite_2x2
draw_player_done
        rts

; A = player sprite frame (PLAYER_FRONT_0..PLAYER_LEFT_1). Same screen
; mechanics as draw_tile_id_2x2 but reads the dedicated sprite char
; tables, keeping player art independent of the terrain tile namespace.
draw_player_sprite_2x2
        sta work
        jsr screen_cell_ptr
        ldx work
        ldy #0
        lda player_sprite_tl,x
        sta (ptr),y
        iny
        lda player_sprite_tr,x
        sta (ptr),y
        clc
        lda ptr
        adc #SCREEN_W
        sta ptr
        bcc draw_player_sprite_bottom_ok
        inc ptr+1
draw_player_sprite_bottom_ok
        ldx work
        ldy #0
        lda player_sprite_bl,x
        sta (ptr),y
        iny
        lda player_sprite_br,x
        sta (ptr),y
        rts

select_player_tile
        lda aim_dir
        cmp #DIR_LEFT
        bcc select_player_front
        cmp #8
        bcs select_player_front
        and #1
        beq select_player_left
        jmp select_player_right
select_player_front
        lda player_anim
        beq select_player_front_0
        lda #PLAYER_FRONT_1
        rts
select_player_front_0
        lda #PLAYER_FRONT_0
        rts
select_player_left
        lda player_anim
        beq select_player_left_0
        lda #PLAYER_LEFT_1
        rts
select_player_left_0
        lda #PLAYER_LEFT_0
        rts
select_player_right
        lda player_anim
        beq select_player_right_0
        lda #PLAYER_RIGHT_1
        rts
select_player_right_0
        lda #PLAYER_RIGHT_0
        rts

erase_player
        lda player_x
        sta target_x
        lda player_y
        sta target_y
        jsr draw_target_world_cell
        rts

erase_bullet
        lda bullet_x
        sta target_x
        lda bullet_y
        sta target_y
        jsr restore_target_top_cell
        rts

draw_bullet
        lda bullet_x
        sta target_x
        lda bullet_y
        sta target_y
        jsr draw_bullet_top_at_target
        sta bullet_drawn
        rts

init_sound
        lda #3
        sta SKCTL
        lda #0
        sta AUDCTL
        sta AUDC1
        sta AUDC2
        sta AUDC3
        sta AUDC4
        rts

disable_network_sound_state
        lda #0
        sta sfx_ch1_id
        sta sfx_ch1_step
        sta sfx_ch1_prio
        sta sfx_ch2_id
        sta sfx_ch2_step
        sta sfx_ch2_prio
        sta sfx_clk
        sta AUDC1
        sta AUDC2
        sta AUDC3
        sta AUDC4
        rts

find_enemy_at_target
        lda active_beaver_count
        bne find_enemy_has_slots
        lda #0
        rts
find_enemy_has_slots
        lda #0
        sta enemy_index
find_enemy_loop
        ldx enemy_index
        lda enemy_alive,x
        beq find_enemy_next
        lda enemy_x,x
        cmp target_x
        bne find_enemy_next
        lda enemy_y,x
        cmp target_y
        bne find_enemy_next
        lda #1
        rts
find_enemy_next
        inc enemy_index
        lda enemy_index
        cmp active_beaver_count
        bne find_enemy_loop
        lda #0
        rts

; A=1 when a live remote player occupies target_x/target_y.
find_remote_at_target
        ldx #0
find_remote_loop
        cpx #NET_MAX_REMOTE_PLAYERS
        beq find_remote_none
        lda remote_alive,x
        beq find_remote_next
        lda remote_x,x
        cmp target_x
        bne find_remote_next
        lda remote_y,x
        cmp target_y
        bne find_remote_next
        lda #1
        rts
find_remote_next
        inx
        jmp find_remote_loop
find_remote_none
        lda #0
        rts

draw_target_world_cell
        jsr target_in_view
        beq draw_target_done
        jsr world_cell_ptr_to_wptr
        ldy #0
        lda (wptr),y
        jsr draw_tile_id_2x2
draw_target_done
        rts

screen_tile_from_world
        cmp #HERB
        bne screen_tile_done
        ora #$80
screen_tile_done
        rts

target_in_view
        lda target_x
        sec
        sbc view_x
        cmp #VIEW_TILE_W
        bcs target_not_visible
        asl
        sta screen_x
        lda target_y
        sec
        sbc view_y
        cmp #VIEW_TILE_H
        bcs target_not_visible
        asl
        sta screen_y
        lda #1
        rts
target_not_visible
        lda #0
        rts

draw_realtime_frame
        jsr hud_message_timeout_check
        jsr hud_quest_done_timeout_check
        lda net_snapshot_dirty
        beq draw_realtime_check_scroll
        jmp draw_realtime_frame_full
draw_realtime_check_scroll
        lda net_scroll_dirty
        beq draw_realtime_check_screen
        jmp draw_realtime_frame_scroll
draw_realtime_check_screen
        lda net_screen_dirty
.if ENABLE_DIRTY_CELL_REDRAW
        beq draw_realtime_idle
        jmp draw_realtime_frame_dirty_cells
.else
.if ENABLE_WORLDSTATE_PARTIAL
        beq draw_realtime_idle
        jmp draw_realtime_frame_dirty_cells
.else
        bne draw_realtime_frame_partial
.endif
.endif
; The idle/partial/dirty paths draw in place into the LIVE displayed buffer
; (no swap), so they wait for the frame tick FIRST and then draw: the
; erase+redraw runs during VBlank/top-of-frame, ahead of the beam, instead
; of at an arbitrary raster position where the beam can scan a cell between
; its terrain restore and its entity redraw (an entity blinking out for one
; frame -- visible as a random flicker when standing near moving entities;
; the buffered scroll/full paths never had this race).
draw_realtime_idle
        inc perf_frames_waited
        jsr wait_frame_tick
        lda status_dirty
        beq draw_realtime_idle_status_done
        lda #0
        sta status_dirty
        jsr draw_status
draw_realtime_idle_status_done
        rts
draw_realtime_frame_partial
        inc perf_partial_redraws
        jsr wait_frame_tick
        lda #0
        sta net_screen_dirty
        lda old_player_x
        sta target_x
        lda old_player_y
        sta target_y
        jsr draw_target_world_cell
        jsr draw_realtime_world_changes
        jsr draw_player
        lda bullet_active
        beq draw_realtime_partial_no_bullet
        jsr draw_bullet
draw_realtime_partial_no_bullet
        lda status_dirty
        beq draw_realtime_partial_status_done
        lda #0
        sta status_dirty
        jsr draw_status
draw_realtime_partial_status_done
        lda player_x
        sta old_player_x
        lda player_y
        sta old_player_y
        rts

; Dirty redraw order:
; wait for VBlank (see the note above draw_realtime_idle), restore old
; dynamic cells, restore changed terrain cell, draw current overlays,
; redraw status if dirty. Used by ENABLE_WORLDSTATE_PARTIAL.
draw_realtime_frame_dirty_cells
        inc perf_dirty_cell_frames
        jsr wait_frame_tick
        lda #0
        sta net_screen_dirty
        jsr restore_old_dynamic_overlays
        jsr restore_changed_world_cell
        jsr draw_dynamic_entities
        jsr net_capture_enemy_cells
        lda status_dirty
        beq draw_realtime_dirty_status_done
        lda #0
        sta status_dirty
        jsr draw_status
draw_realtime_dirty_status_done
        lda player_x
        sta old_player_x
        lda player_y
        sta old_player_y
        rts

restore_old_player_cell
        lda old_player_x
        cmp player_x
        bne restore_old_player_needed
        lda old_player_y
        cmp player_y
        bne restore_old_player_needed
        rts
restore_old_player_needed
        inc perf_dirty_player_restores
        lda old_player_x
        sta target_x
        lda old_player_y
        sta target_y
        jsr draw_target_world_cell
        rts

restore_old_enemy_cells
        lda #0
        sta enemy_index
restore_old_enemy_loop
        ldx enemy_index
        cpx #BEAVER_MAX_COUNT
        beq restore_old_enemy_done
        lda old_enemy_alive,x
        beq restore_old_enemy_next
        inc perf_dirty_enemy_restores
        lda old_enemy_x,x
        sta target_x
        lda old_enemy_y,x
        sta target_y
        jsr draw_target_world_cell
restore_old_enemy_next
        inc enemy_index
        jmp restore_old_enemy_loop
restore_old_enemy_done
        rts

restore_old_remote_cells
        lda #0
        sta enemy_index
restore_old_remote_loop
        ldx enemy_index
        cpx #NET_MAX_REMOTE_PLAYERS
        beq restore_old_remote_done
        lda old_remote_alive,x
        beq restore_old_remote_next
        lda old_remote_x,x
        sta target_x
        lda old_remote_y,x
        sta target_y
        jsr draw_target_world_cell
restore_old_remote_next
        inc enemy_index
        jmp restore_old_remote_loop
restore_old_remote_done
        rts

restore_changed_world_cell
        lda net_world_dirty
        beq restore_changed_world_done
        lda #0
        sta net_world_dirty
        lda net_packet_payload+20
        ora net_packet_payload+21
        beq restore_changed_world_done
        lda net_packet_payload+20
        sta target_x
        lda net_packet_payload+21
        sta target_y
        jsr draw_target_world_cell
restore_changed_world_done
        rts
draw_realtime_frame_scroll
        inc perf_partial_redraws
        lda #0
        sta net_scroll_dirty
        sta net_screen_dirty
        sta net_world_dirty
        jsr draw_scroll_frame_buffered
        jsr net_capture_enemy_cells
        lda player_x
        sta old_player_x
        lda player_y
        sta old_player_y
        lda view_x
        sta old_view_x
        lda view_y
        sta old_view_y
        rts

draw_realtime_frame_full
        inc perf_full_redraws
        lda #0
        sta net_snapshot_dirty
        sta net_scroll_dirty
        sta net_screen_dirty
        sta net_world_dirty
        sta status_dirty
        jsr draw_scrolled_frame_buffered
        jsr net_capture_enemy_cells
        lda player_x
        sta old_player_x
        lda player_y
        sta old_player_y
        rts

draw_realtime_world_changes
        lda net_world_dirty
        beq draw_realtime_world_done
        lda #0
        sta net_world_dirty
        lda net_packet_payload+20
        ora net_packet_payload+21
        beq draw_realtime_world_old_beavers
        lda net_packet_payload+20
        sta target_x
        lda net_packet_payload+21
        sta target_y
        jsr draw_target_world_cell
draw_realtime_world_old_beavers
        ldx #0
draw_realtime_old_beaver_loop
        cpx #BEAVER_MAX_COUNT
        beq draw_realtime_new_beavers
        lda old_enemy_alive,x
        beq draw_realtime_old_beaver_next
        lda old_enemy_x,x
        sta target_x
        lda old_enemy_y,x
        sta target_y
        jsr draw_target_world_cell
draw_realtime_old_beaver_next
        inx
        jmp draw_realtime_old_beaver_loop
draw_realtime_new_beavers
        ldx #0
draw_realtime_new_beaver_loop
        cpx #BEAVER_MAX_COUNT
        beq draw_realtime_world_done
        lda enemy_alive,x
        beq draw_realtime_new_beaver_next
        lda enemy_x,x
        sta target_x
        lda enemy_y,x
        sta target_y
        jsr target_in_view
        beq draw_realtime_new_beaver_next
        jsr select_enemy_tile
        bcs draw_realtime_new_beaver_next
        jsr draw_tile_id_2x2
draw_realtime_new_beaver_next
        inx
        jmp draw_realtime_new_beaver_loop
draw_realtime_world_done
        rts

draw_scrolled_frame_buffered
        jsr swap_screen_buffers
        jsr draw_viewport
        jsr draw_dynamic_entities
        jsr draw_status_full
        jsr wait_frame_tick
        jsr update_display_lms
        rts

draw_scroll_frame_buffered
        jsr swap_screen_buffers
        jsr draw_viewport
        jsr draw_dynamic_entities
        lda status_dirty
        beq draw_scroll_frame_status_done
        lda #0
        sta status_dirty
        jsr draw_status
draw_scroll_frame_status_done
        jsr wait_frame_tick
        jsr update_display_lms
        rts

; Overlay priority: terrain base, enemies, items, remote players, local
; player, projectiles, then status.
; Dynamic overlays draw to screen buffers only; terrain/cache remains authoritative.
draw_dynamic_entities
        jsr draw_enemies
        jsr draw_items
        jsr draw_remote_players
        jsr draw_player
        lda bullet_active
        beq draw_dynamic_remote_bullets
        jsr draw_bullet
draw_dynamic_remote_bullets
        jsr draw_remote_bullets
        rts

; draw_remote_players lives in the $8000 block (see the note near
; redraw_hud_pvp) -- the main $2000 segment has no headroom left below
; SCREEN, and this routine grew a PvP recolor check.

draw_enemies
        lda #0
        sta enemy_index
draw_enemies_loop
        ldx enemy_index
        cpx active_beaver_count
        beq draw_enemies_done
        lda enemy_alive,x
        beq draw_enemies_next
        lda enemy_x,x
        sta target_x
        lda enemy_y,x
        sta target_y
        jsr target_in_view
        beq draw_enemies_next
        ldx enemy_index
        jsr select_enemy_tile
        bcs draw_enemies_next
        jsr draw_tile_id_2x2
draw_enemies_next
        inc enemy_index
        jmp draw_enemies_loop
draw_enemies_done
        rts

draw_viewport
        lda #0
        sta loop_y
viewport_row_loop
        jsr draw_viewport_prepare_row
        bcs draw_viewport_slow
        lda #0
        sta loop_x
viewport_col_loop
        ldy #0
        lda (wptr),y
        tax
        lda tile2x2_tl,x
        sta (ptr),y
        iny
        lda tile2x2_tr,x
        sta (ptr),y
        ldy #0
        lda tile2x2_bl,x
        sta (screen_bottom_ptr),y
        iny
        lda tile2x2_br,x
        sta (screen_bottom_ptr),y
        clc
        lda ptr
        adc #2
        sta ptr
        bcc viewport_top_ptr_ok
        inc ptr+1
viewport_top_ptr_ok
        clc
        lda screen_bottom_ptr
        adc #2
        sta screen_bottom_ptr
        bcc viewport_bottom_ptr_ok
        inc screen_bottom_ptr+1
viewport_bottom_ptr_ok
        inc wptr
        bne viewport_cache_ptr_ok
        inc wptr+1
viewport_cache_ptr_ok
        inc loop_x
        lda loop_x
        cmp #VIEW_TILE_W
        bne viewport_col_loop
        inc loop_y
        lda loop_y
        cmp #VIEW_TILE_H
        bne viewport_row_loop
        jsr clear_view_separator
        rts

draw_viewport_slow
        lda #0
        sta loop_y
viewport_slow_row_loop
        lda #0
        sta loop_x
viewport_slow_col_loop
        lda loop_x
        asl
        sta screen_x
        lda loop_y
        asl
        sta screen_y
        jsr draw_view_cell
        inc loop_x
        lda loop_x
        cmp #VIEW_TILE_W
        bne viewport_slow_col_loop
        inc loop_y
        lda loop_y
        cmp #VIEW_TILE_H
        bne viewport_slow_row_loop
        jsr clear_view_separator
        rts

draw_viewport_prepare_row
        lda active_screen_lo
        sta ptr
        lda active_screen_hi
        sta ptr+1
        ldx loop_y
        beq draw_viewport_screen_row_ready
draw_viewport_screen_row_loop
        clc
        lda ptr
        adc #80
        sta ptr
        bcc draw_viewport_screen_row_no_carry
        inc ptr+1
draw_viewport_screen_row_no_carry
        dex
        bne draw_viewport_screen_row_loop
draw_viewport_screen_row_ready
        clc
        lda ptr
        adc #SCREEN_W
        sta screen_bottom_ptr
        lda ptr+1
        adc #0
        sta screen_bottom_ptr+1
        lda network_enabled
        beq draw_viewport_prepare_world_row
        lda network_got_window
        beq draw_viewport_prepare_world_row
        lda view_x
        cmp net_window_origin_x
        bcc draw_viewport_prepare_fail
        sec
        sbc net_window_origin_x
        cmp #NET_WINDOW_W-VIEW_TILE_W+1
        bcs draw_viewport_prepare_fail
        sta cache_local_x
        lda view_y
        clc
        adc loop_y
        cmp net_window_origin_y
        bcc draw_viewport_prepare_fail
        sec
        sbc net_window_origin_y
        cmp #NET_WINDOW_H
        bcs draw_viewport_prepare_fail
        sta cache_local_y
        jsr world_cell_ptr_cache
        lda ptr
        sta wptr
        lda ptr+1
        sta wptr+1
        lda active_screen_lo
        sta ptr
        lda active_screen_hi
        sta ptr+1
        ldx loop_y
        beq draw_viewport_restore_screen_done
draw_viewport_restore_screen_loop
        clc
        lda ptr
        adc #80
        sta ptr
        bcc draw_viewport_restore_screen_no_carry
        inc ptr+1
draw_viewport_restore_screen_no_carry
        dex
        bne draw_viewport_restore_screen_loop
draw_viewport_restore_screen_done
        clc
        rts
draw_viewport_prepare_world_row
        lda view_y
        clc
        adc loop_y
        sta cache_local_y
        lsr
        clc
        adc #>WORLD
        sta wptr+1
        lda cache_local_y
        and #1
        beq draw_viewport_world_even_row
        lda #$80
        jmp draw_viewport_world_low_done
draw_viewport_world_even_row
        lda #0
draw_viewport_world_low_done
        clc
        adc view_x
        sta wptr
        clc
        rts
draw_viewport_prepare_fail
        sec
        rts

draw_view_col
        lda #0
        sta screen_y
draw_view_col_loop
        jsr draw_view_cell
        inc screen_y
        lda screen_y
        cmp #SCREEN_H
        bne draw_view_col_loop
        rts

draw_view_row
        lda #0
        sta screen_x
draw_view_row_loop
        jsr draw_view_cell
        inc screen_x
        lda screen_x
        cmp #SCREEN_W
        bne draw_view_row_loop
        rts

draw_view_cell
        lda view_x
        clc
        adc loop_x
        sta target_x
        lda view_y
        clc
        adc loop_y
        sta target_y
        jsr world_cell_ptr_to_wptr
        ldy #0
        lda (wptr),y
        jsr draw_tile_id_2x2
        rts

clear_view_separator
        lda #VIEW_SEPARATOR_Y
        sta screen_y
        lda #0
        sta screen_x
clear_view_separator_loop
        jsr screen_cell_ptr
        ldy #0
        lda #STATUS_BLANK
        sta (ptr),y
        inc screen_x
        lda screen_x
        cmp #SCREEN_W
        bne clear_view_separator_loop
        rts

draw_tile_id_2x2
        sta work
        jsr screen_cell_ptr
        ldx work
        ldy #0
        lda tile2x2_tl,x
        sta (ptr),y
        iny
        lda tile2x2_tr,x
        sta (ptr),y
        clc
        lda ptr
        adc #SCREEN_W
        sta ptr
        bcc draw_tile_bottom_ptr_ok
        inc ptr+1
draw_tile_bottom_ptr_ok
        ldx work
        ldy #0
        lda tile2x2_bl,x
        sta (ptr),y
        iny
        lda tile2x2_br,x
        sta (ptr),y
        rts

; Sync all three HUD rows (21-23, offsets 840-959) into the back buffer,
; not just the old single status row, or HUD changes drawn between buffer
; swaps reappear stale after the next scroll/full frame swap. 120 bytes,
; still fits a single 8-bit Y index loop.
copy_status_to_back
        clc
        lda active_screen_lo
        adc #<(HUD_LINE1_Y*SCREEN_W)
        sta ptr
        lda active_screen_hi
        adc #>(HUD_LINE1_Y*SCREEN_W)
        sta ptr+1
        clc
        lda back_screen_lo
        adc #<(HUD_LINE1_Y*SCREEN_W)
        sta wptr
        lda back_screen_hi
        adc #>(HUD_LINE1_Y*SCREEN_W)
        sta wptr+1
        ldy #0
copy_status_byte_loop
        lda (ptr),y
        sta (wptr),y
        iny
        cpy #3*SCREEN_W
        bne copy_status_byte_loop
        rts

screen_cell_ptr
        txa
        pha
        lda active_screen_lo
        sta ptr
        lda active_screen_hi
        sta ptr+1
        ldx screen_y
        beq add_x
row_add
        clc
        lda ptr
        adc #40
        sta ptr
        bcc row_no_carry
        inc ptr+1
row_no_carry
        dex
        bne row_add
add_x
        clc
        lda ptr
        adc screen_x
        sta ptr
        bcc ptr_done
        inc ptr+1
ptr_done
        pla
        tax
        rts

world_cell_ptr
        txa
        pha
        jsr world_cell_ptr_body
        pla
        tax
        rts

world_cell_ptr_to_wptr
        txa
        pha
        jsr world_cell_ptr_body
        lda ptr
        sta wptr
        lda ptr+1
        sta wptr+1
        pla
        tax
        rts

world_cell_ptr_body
        lda network_enabled
        beq world_cell_ptr_full_world
        lda network_got_window
        beq world_cell_ptr_full_world
        lda target_x
        cmp net_window_origin_x
        bcc world_cell_ptr_blocking
        sec
        sbc net_window_origin_x
        cmp #NET_WINDOW_W
        bcs world_cell_ptr_blocking
world_cell_ptr_x_in_cache
        sta cache_local_x
        lda target_y
        cmp net_window_origin_y
        bcc world_cell_ptr_blocking
        sec
        sbc net_window_origin_y
        cmp #NET_WINDOW_H
        bcs world_cell_ptr_blocking
world_cell_ptr_y_in_cache
        sta cache_local_y
        jmp world_cell_ptr_cache
world_cell_ptr_blocking
        lda #0
        sta cache_ptr_valid
        lda #BORDER
        sta cache_blocking_tile
        lda #<cache_blocking_tile
        sta ptr
        lda #>cache_blocking_tile
        sta ptr+1
        rts
world_cell_ptr_cache
        lda #1
        sta cache_ptr_valid
        lda cache_local_y
        lsr
        clc
        adc cache_active_hi
        sta ptr+1
        lda cache_local_y
        and #1
        beq world_cache_even_row
        lda #$80
        jmp world_cache_low_base_done
world_cache_even_row
        lda #0
world_cache_low_base_done
        clc
        adc cache_local_x
        sta ptr
        rts
world_cell_ptr_full_world
        lda #1
        sta cache_ptr_valid
        lda target_y
        lsr
        clc
        adc #>WORLD
        sta ptr+1
        lda target_y
        and #1
        beq world_even_row
        lda #$80
        jmp world_low_base_done
world_even_row
        lda #0
world_low_base_done
        clc
        adc target_x
        sta ptr
        rts

; Selective HUD redraw: only repaints the field(s) whose dirty flag is set,
; instead of blanking and redrawing all 3 HUD rows on every change -- that
; full clear-then-redraw was visible as flicker on every health/beaver/quest/
; message update. draw_status_full (the old clear-everything path) is still
; used for the rare true full-screen redraws (init, modal close, map change).
draw_status
        lda hp_dirty
        beq draw_status_check_level
        lda #0
        sta hp_dirty
        jsr redraw_hud_hearts
draw_status_check_level
        lda level_dirty
        beq draw_status_check_quest
        lda #0
        sta level_dirty
        jsr redraw_hud_level
draw_status_check_quest
        lda quest_dirty
        beq draw_status_check_message
        lda #0
        sta quest_dirty
        jsr redraw_hud_quest
draw_status_check_message
        lda message_dirty
        beq draw_status_done
        lda #0
        sta message_dirty
        jsr redraw_hud_message
draw_status_done
        rts

; Fills heart_full_count with how many of the HEART_COUNT heart glyphs
; should show full, proportional to player_health/player_max_health
; rather than comparing raw HP against a fixed 4-6 point scale (which
; used to mean hearts stayed full until real HP dropped below HEART_COUNT
; no matter how big max HP had grown from leveling up).
; heart i is full when player_health*HEART_COUNT >= (i+1)*player_max_health;
; computed by building the left side once and walking the right side up
; by player_max_health each step, avoiding any need for real division.
compute_heart_full_count
        lda #0
        sta heart_lhs_lo
        sta heart_lhs_hi
        ldx #HEART_COUNT
compute_heart_lhs_loop
        clc
        lda heart_lhs_lo
        adc player_health
        sta heart_lhs_lo
        bcc compute_heart_lhs_no_carry
        inc heart_lhs_hi
compute_heart_lhs_no_carry
        dex
        bne compute_heart_lhs_loop
        lda player_max_health
        sta heart_rhs_lo
        lda #0
        sta heart_rhs_hi
        ldx #0
compute_heart_count_loop
        cpx #HEART_COUNT
        beq compute_heart_count_done
        lda heart_lhs_hi
        cmp heart_rhs_hi
        bne compute_heart_hi_decides
        lda heart_lhs_lo
        cmp heart_rhs_lo
compute_heart_hi_decides
        bcc compute_heart_count_done
        clc
        lda heart_rhs_lo
        adc player_max_health
        sta heart_rhs_lo
        bcc compute_heart_rhs_no_carry
        inc heart_rhs_hi
compute_heart_rhs_no_carry
        inx
        jmp compute_heart_count_loop
compute_heart_count_done
        stx heart_full_count
        rts

redraw_hud_hearts
        jsr compute_heart_full_count
        lda #HUD_LINE1_Y
        sta screen_y
        lda #HUD_HEARTS_X
        sta screen_x
        ldx #0
redraw_hud_hearts_loop
        cpx #HEART_COUNT
        beq redraw_hud_hearts_done
        txa
        cmp heart_full_count
        bcs redraw_hud_hearts_empty
        lda #OS_HEART
        jmp redraw_hud_hearts_store
redraw_hud_hearts_empty
        lda #0
redraw_hud_hearts_store
        jsr status_store_tile
        inc screen_x
        inx
        jmp redraw_hud_hearts_loop
redraw_hud_hearts_done
        jmp copy_status_to_back

redraw_hud_level
        lda #HUD_LINE1_Y
        sta screen_y
        lda #HUD_LEVEL_DIGITS_X
        sta screen_x
        lda level_num
        jsr hud_draw_two_digits
; Gold/PvP changes piggyback on level_dirty (see netstream_apply_hud_update)
; instead of their own dirty flag/dispatch branches, since the main $2000
; segment has no headroom left below SCREEN for more dispatch checks.
        lda #HUD_GOLD_X
        sta screen_x
        jsr draw_hud_gold
        jsr redraw_hud_pvp
        jmp copy_status_to_back

; redraw_hud_pvp lives in the $8000 block (see the note near
; netstream_item_count_ok) -- the main $2000 segment has no headroom left
; below SCREEN.

redraw_hud_quest
        lda #HUD_LINE2_Y
        jsr clear_hud_row
        jsr draw_quest_status_line
        jmp copy_status_to_back

redraw_hud_message
        lda #HUD_LINE3_Y
        jsr clear_hud_row
        jsr draw_message_status_line
        jmp copy_status_to_back

clear_hud_row
        sta screen_y
        lda #0
        sta screen_x
clear_hud_row_loop
        jsr screen_cell_ptr
        ldy #0
        lda #0
        sta (ptr),y
        inc screen_x
        lda screen_x
        cmp #SCREEN_W
        bne clear_hud_row_loop
        rts

status_store_tile
        pha
        jsr screen_cell_ptr
        ldy #0
        pla
        sta (ptr),y
        rts

enemy_index
        dta 0
player_health
        dta 0
; Real max HP (scales with level), distinct from HEART_COUNT (the fixed
; number of heart glyphs). Defaults to the server's level-1 starting
; value until the first HUD_UPDATE packet corrects it.
player_max_health
        dta 12
heart_full_count
        dta 0
heart_lhs_lo
        dta 0
heart_lhs_hi
        dta 0
heart_rhs_lo
        dta 0
heart_rhs_hi
        dta 0
active_beaver_count
        dta 0
beavers_left
        dta 0
level_num
        dta 0
status_pos
        dta 0
forest_damage_count
        dta 0
player_anim
        dta 0
enemy_x
        dta 0,0,0,0,0,0,0,0
enemy_y
        dta 0,0,0,0,0,0,0,0
enemy_hp
        dta 0,0,0,0,0,0,0,0
enemy_alive
        dta 0,0,0,0,0,0,0,0
old_enemy_x
        dta 0,0,0,0,0,0,0,0
old_enemy_y
        dta 0,0,0,0,0,0,0,0
old_enemy_alive
        dta 0,0,0,0,0,0,0,0
remote_count_tmp
        dta 0
; Phase 14b item-drop overlay slots live near $8000 with the rest of that
; feature's code -- see the comment above netstream_apply_item_drops.
active_screen_lo
        dta <SCREEN
active_screen_hi
        dta >SCREEN
back_screen_lo
        dta <SCREEN_BACK
back_screen_hi
        dta >SCREEN_BACK
old_player_x
        dta 0
old_player_y
        dta 0
transition_start_clk
        dta 0
netstream_timeout
        dta 0
netstream_result
        dta 0
netstream_final_flags
        dta 0
netstream_final_audf3
        dta 0
netstream_final_audf4
        dta 0
network_enabled
        dta 0
network_realtime_enabled
        dta 0
network_got_welcome
        dta 0
network_got_window
        dta 0
input_dir
        dta 0
input_buttons
        dta 0
net_tick_lo
        dta 0
net_tick_hi
        dta 0
net_ack_tick_lo
        dta 0
net_ack_tick_hi
        dta 0
net_realtime_seq_lo
        dta 0
net_realtime_seq_hi
        dta 0
net_realtime_send_clk
        dta 0
net_realtime_send_index
        dta 0
net_realtime_server_seq_lo
        dta 0
net_realtime_server_seq_hi
        dta 0
net_last_terrain_seq_valid
        dta 0
net_last_terrain_seq_lo
        dta 0
net_last_terrain_seq_hi
        dta 0
net_player_correction_pending
        dta 0
net_player_correction_x
        dta 0
net_player_correction_y
        dta 0
net_predicted_move_pending
        dta 0
net_predicted_move_seq_lo
        dta 0
net_predicted_move_seq_hi
        dta 0
net_prediction_send_pending
        dta 0
net_world_changed
        dta 0
; Phase 1 dirty-flag meanings:
; net_screen_dirty: partial redraw requested when no full redraw is pending.
; net_scroll_dirty: viewport origin changed; the client still routes this to full redraw.
; net_world_dirty: terrain/entity state changed; currently mostly masked by full redraw.
; status_dirty: status line changed; partial redraw may redraw status only when set.
; net_snapshot_dirty: full redraw required for snapshots, cache/window replacement, or recovery.
net_screen_dirty
        dta 0
net_scroll_dirty
        dta 0
net_world_dirty
        dta 0
status_dirty
        dta 0
; Per-field HUD dirty flags: status_dirty just gates whether draw_status
; runs at all; these say which field(s) actually need repainting, so a
; health tick doesn't blank/redraw the quest and message lines too.
hp_dirty
        dta 0
beavers_dirty
        dta 0
level_dirty
        dta 0
quest_dirty
        dta 0
message_dirty
        dta 0
net_old_beavers_left
        dta 0
net_fire_counter
        dta 0
net_pickup_counter
        dta 0
net_input_clk
        dta 0
net_last_move_raw
        dta $0f
net_last_move_clk
        dta 0
net_move_repeat_dir
        dta 0
net_move_repeat_clk
        dta 0
net_sent_stick_raw
        dta $0f
net_parser_state
        dta 0
net_parser_index
        dta 0
net_parser_checksum
        dta 0
net_packet_type
        dta 0
net_packet_len
        dta 0
net_rx_byte
        dta 0
net_recv_budget
        dta 0
net_snapshot_pending
        dta 0
net_snapshot_dirty
        dta 0
net_snapshot_payload
        :NET_SNAPSHOT_PAYLOAD_LEN dta 0
net_payload_offset
        dta 0
net_seed_lo
        dta 1
net_seed_hi
        dta 0
net_rng_lo
        dta 1
net_rng_hi
        dta 0
net_window_origin_x
        dta 0
net_window_origin_x_hi
        dta 0
net_window_origin_y
        dta 0
net_window_origin_y_hi
        dta 0
net_pending_origin_x
        dta 0
net_pending_origin_x_hi
        dta 0
net_pending_origin_y
        dta 0
net_pending_origin_y_hi
        dta 0
cache_active_hi
        dta >WORLD
cache_pending_hi
        dta >WORLD_PENDING
net_window_row
        dta 0
net_window_col
        dta 0
net_window_chunk_y
        dta 0
net_window_chunk_h
        dta 0
net_window_rows_loaded
        dta 0
cache_local_x
        dta 0
cache_local_y
        dta 0
cache_ptr_valid
        dta 0
cache_blocking_tile
        dta BORDER
current_map_id
        dta MAP_OVERWORLD
current_tileset_id
        dta TILESET_OVERWORLD
current_palette_id
        dta PALETTE_OVERWORLD
current_font_page
        dta >FONT
net_map_change_pending
        dta 0
; Round 2/3 realtime state lives in fixed RAM (see $8C00 equates). All of
; these are cleared in netstream_start_realtime or written before read;
; none rely on load-time zero init.
net_last_valid_rt_clk = NET_RT_STATE_BUFFER+0
net_rt_watchdog_armed = NET_RT_STATE_BUFFER+1
net_rt_rx_index = NET_RT_STATE_BUFFER+2
net_rt_packet_valid = NET_RT_STATE_BUFFER+3
net_rt_resync_src = NET_RT_STATE_BUFFER+4
net_auth_keepalive_clk = NET_RT_STATE_BUFFER+5
net_terrain_desync = NET_RT_STATE_BUFFER+6
net_resync_pending = NET_RT_STATE_BUFFER+7
net_resync_request_clk = NET_RT_STATE_BUFFER+8
net_resync_row_origin_y = NET_RT_STATE_BUFFER+9
net_row_fill_active = NET_RT_STATE_BUFFER+10
net_map_fill_pending = NET_RT_STATE_BUFFER+11
net_window_row_mask0 = NET_RT_STATE_BUFFER+12
net_window_row_mask1 = NET_RT_STATE_BUFFER+13
net_window_row_mask2 = NET_RT_STATE_BUFFER+14
; +15 was net_rt_target_size (retired by realtime v3); +16 was
; net_rt_checksum_offset, whose address aliased LOGIN_STATE_BUFFER+0
; (has_identity) -- retiring it also removed that collision.
net_v3_discard = NET_RT_STATE_BUFFER+15
net_realtime_packet = NET_REALTIME_PACKET_BUFFER
net_realtime_tx_packet = NET_REALTIME_TX_PACKET_BUFFER
net_packet_payload = NET_PACKET_PAYLOAD_BUFFER

; ---- Phase 7.6: AppKey/login state and buffers ----
; Login/appkey scratch state in fixed RAM (see LOGIN_STATE_BUFFER): every
; field is (re)written by its flow before being read, on every attempt.
; appkey_key_id and small load-time state live in the $5400 data segment so
; the main segment stays below SCREEN.
has_identity = LOGIN_STATE_BUFFER+0
username_len = LOGIN_STATE_BUFFER+1
token_len = LOGIN_STATE_BUFFER+2
login_status = LOGIN_STATE_BUFFER+3
appkey_count = LOGIN_STATE_BUFFER+4
appkey_write_len = LOGIN_STATE_BUFFER+5
login_payload_len = LOGIN_STATE_BUFFER+6
login_checksum = LOGIN_STATE_BUFFER+7
login_frame_len = LOGIN_STATE_BUFFER+8
login_total_len = LOGIN_STATE_BUFFER+9
login_recv_len = LOGIN_STATE_BUFFER+10
login_recv_timeout = LOGIN_STATE_BUFFER+11
login_recv_avail = LOGIN_STATE_BUFFER+12
login_expected_total = LOGIN_STATE_BUFFER+13
token_digit = LOGIN_STATE_BUFFER+14
cio_get_failed = LOGIN_STATE_BUFFER+15
username_prompt_mode = LOGIN_STATE_BUFFER+16
title_identity_state = LOGIN_STATE_BUFFER+17
token_bin = TOKEN_BIN_BUFFER
; Login/appkey scratch buffers relocated to fixed RAM (see the $8C00
; equates); every one is written before it is read.
token_tmp = TOKEN_TMP_BUFFER
appkey_open_buf = APPKEY_OPEN_BUFFER
appkey_data_buf = APPKEY_DATA_BUFFER
n_status_buf = N_STATUS_BUFFER
login_pkt_buf = LOGIN_PKT_BUFFER
username_buf = USERNAME_BUFFER
token_buf = TOKEN_BUFFER
; MADS's dta "string" uses the Atari internal screen-code table, not
; ATASCII (confirmed against the assembled listing) -- CIO and the N:
; device both need real ATASCII, so these are spelled out as decimal
; ASCII bytes instead, matching the existing netstream_host convention.
; Phase 61 visuals are entirely client-local. RTCLOK selects the two-frame
; slime/bat pose and also drives a short self-clearing hit blink. The server
; only sets bit 7 in the existing enemy-kind byte when damage lands.
update_enemy_visuals
        lda RTCLOK
        and #8
        cmp enemy_anim_phase
        beq update_enemy_hit_timers
        sta enemy_anim_phase
        lda #1
        sta net_screen_dirty
update_enemy_hit_timers
        ldx #0
update_enemy_hit_loop
        cpx #BEAVER_MAX_COUNT
        beq update_enemy_visuals_done
        lda enemy_hit_timer,x
        beq update_enemy_hit_next
        dec enemy_hit_timer,x
        lda #1
        sta net_screen_dirty
update_enemy_hit_next
        inx
        jmp update_enemy_hit_loop
update_enemy_visuals_done
        rts

select_enemy_tile
        lda enemy_hit_timer,x
        and #1
        bne select_enemy_flash_hidden
        lda enemy_kind,x
        cmp #ENEMY_SNAKE
        beq select_enemy_snake
        cmp #ENEMY_BAT
        beq select_enemy_bat
        cmp #ENEMY_SLIME
        beq select_enemy_slime
        cmp #ENEMY_GOBLIN
        beq select_enemy_goblin
        cmp #ENEMY_GORVAK
        beq select_enemy_gorvak
        cmp #DYNAMIC_WILHELM
        beq select_dynamic_wilhelm
        cmp #DYNAMIC_WILHELM_WORKING
        beq select_dynamic_wilhelm_working
        lda #BEAVER
        clc
        rts
select_enemy_snake
        lda #SNAKE
        clc
        rts
select_enemy_bat
        lda enemy_anim_phase
        beq select_enemy_bat_0
        lda #BAT_1
        clc
        rts
select_enemy_bat_0
        lda #BAT_0
        clc
        rts
select_enemy_slime
        lda enemy_anim_phase
        beq select_enemy_slime_0
        lda #SLIME_1
        clc
        rts
select_enemy_slime_0
        lda #SLIME_0
        clc
        rts
select_enemy_goblin
        lda #GOBLIN
        clc
        rts
select_enemy_gorvak
        lda #GORVAK
        clc
        rts
select_dynamic_wilhelm
        lda #WILHELM
        clc
        rts
select_dynamic_wilhelm_working
        lda enemy_anim_phase
        beq select_dynamic_wilhelm
        lda #WILHELM_WORKING
        clc
        rts
select_enemy_flash_hidden
        sec
        rts

; Guard: the main $2000 code/variable segment must end below the screen
; buffer at SCREEN ($4680). Phase 5 code growth silently pushed const tables
; into the screen region (clear_screen zeroed them); keep this assert.
        ert *>SCREEN

; Constant tables live in the free gap between the font ($5000-$53FF area)
; and the title/message text data at $5600.
        org $5400
appkey_key_id
        dta FUJINET_APPKEY_IDENTITY
server_host_len
        dta 0
server_host_input_len
        dta 0
net_map_spawn_x
        dta 0
net_map_spawn_y
        dta 0
; Relocated here (rather than alongside the other per-field HUD state near
; level_dirty/remote_x) because the main $2000 segment has no headroom
; left below SCREEN -- see the "ert *>SCREEN" guard just above.
net_pvp_toggle_counter
        dta 0
hud_pvp_enabled
        dta 0
hud_pvp_kills_lo
        dta 0
hud_pvp_kills_hi
        dta 0
hud_digits_value_lo
        dta 0
hud_digits_value_hi
        dta 0
hud_digits_tmp
        dta 0
map_summary_cells
        :MAP_SUMMARY_CELL_COUNT dta 0
enemy_kind
        dta 0,0,0,0,0,0,0,0
old_enemy_kind
        dta 0,0,0,0,0,0,0,0
enemy_hit_timer
        dta 0,0,0,0,0,0,0,0
enemy_anim_phase
        dta 0
map_summary_valid
        dta 0
map_summary_map_id
        dta 0
map_summary_width
        dta 0
map_summary_height
        dta 0
map_cell_index
        dta 0
map_row_tmp
        dta 0
map_col_tmp
        dta 0
map_char_tmp
        dta 0
; Scratch byte set per-remote-player by draw_remote_players ($80 or 0) and
; consumed by draw_remote_player_sprite_2x2 -- see the notes there.
remote_recolor_bit
        dta 0
; Remote-player overlay slots (Phase 13.5). Filled from NET_RT_REMOTE_PLAYERS;
; persists between packets (server sends change-driven updates only). Relocated
; here so stress builds with up to 12 slots do not grow the main segment into
; screen RAM.
        icl "generated/remote_player_arrays.inc"
sfx_ch1_id
        dta 0
sfx_ch1_step
        dta 0
sfx_ch1_prio
        dta 0
sfx_ch2_id
        dta 0
sfx_ch2_step
        dta 0
sfx_ch2_prio
        dta 0
sfx_clk
        dta 0
sfx_update_save_x
        dta 0
sfx_update_save_y
        dta 0
sfx_update_save_wptr
        dta 0,0
sfx_request_id
        dta 0
sfx_request_save_x
        dta 0
sfx_request_save_y
        dta 0
sfx_request_save_wptr
        dta 0,0
e_device_name
        dta 69,58,155

show_connection_failed_screen
; Realtime play holds CRITIC=1 (see main_loop_os_sync); the stream is down
; here, so hand the deferred VBI back to the OS before the retry screens.
        lda #0
        sta CRITIC
        lda #<connection_failed_lines
        sta wptr
        lda #>connection_failed_lines
        sta wptr+1
        jsr wait_frame_tick
        ldx #<display_list_text
        ldy #>display_list_text
        lda #OS_FONT_PAGE
        jsr apply_display_now
        jsr init_screen_buffers
        jsr set_text_palette
        jsr clear_screen
        lda netstream_final_flags
        beq show_connection_failed_normal
        lda #<connection_unstable_lines
        sta wptr
        lda #>connection_unstable_lines
        sta wptr+1
show_connection_failed_normal
        jsr draw_text_lines
        jsr draw_title_baud
connection_failed_wait_action
        jsr wait_title_action
        cmp #TITLE_ACTION_BAUD
        beq connection_failed_change_baud
        cmp #0
        beq connection_failed_action_done
        jmp connection_failed_wait_action
connection_failed_change_baud
        jsr netstream_cycle_baud
        jmp show_connection_failed_screen
connection_failed_action_done
        rts

netstream_args
        dta <NETSTREAM_BAUD_DEFAULT,>NETSTREAM_BAUD_DEFAULT,NETSTREAM_FLAGS
        dta <netstream_host,>netstream_host
netstream_realtime_args
        dta <NETSTREAM_BAUD_DEFAULT,>NETSTREAM_BAUD_DEFAULT,NETSTREAM_REALTIME_FLAGS
        dta <netstream_host,>netstream_host
netstream_baud_index
        dta 1
; ANTIC 4 character row encoding:
; each byte contains four 2-bit color pixels: bits 76,54,32,10.
; 00=COLOR4, 01=COLOR0, 10=COLOR1, 11=COLOR2, or COLOR3 when bit 7 is set
; in the screen character code.
;
log_frame_data
; horizontal
        dta %00000000
        dta %00000000
        dta %10111110
        dta %10101010
        dta %10111110
        dta %00000000
        dta %00000000
        dta %00000000
; slash
        dta %00000010
        dta %00001010
        dta %00111000
        dta %10100000
        dta %00111000
        dta %00001010
        dta %00000010
        dta %00000000
; horizontal alternate
        dta %00000000
        dta %00000000
        dta %10111110
        dta %10111110
        dta %10101010
        dta %00000000
        dta %00000000
        dta %00000000
; backslash
        dta %10000000
        dta %10100000
        dta %00111000
        dta %00001010
        dta %00111000
        dta %10100000
        dta %10000000
        dta %00000000

log_frame_2x2_data
; horizontal
        dta %00000000
        dta %00000000
        dta %00001010
        dta %00101010
        dta %00111110
        dta %00001010
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %10100000
        dta %10101000
        dta %10111100
        dta %10100000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00001010
        dta %00101010
        dta %00111110
        dta %00101010
        dta %00001010
        dta %00000000
        dta %00000000
        dta %00000000
        dta %10100000
        dta %10101000
        dta %10111100
        dta %10101000
        dta %10100000
        dta %00000000
        dta %00000000
; slash
        dta %00000000
        dta %00000000
        dta %00000010
        dta %00001010
        dta %00101000
        dta %00100000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %10000000
        dta %10100000
        dta %00101000
        dta %00001000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00000010
        dta %00001010
        dta %00101000
        dta %00100000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %10000000
        dta %10100000
        dta %00101000
        dta %00001000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00000000
; horizontal alternate
        dta %00000000
        dta %00000000
        dta %00101010
        dta %00111110
        dta %00001010
        dta %00101010
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %10101000
        dta %10111100
        dta %10100000
        dta %10101000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00101010
        dta %00111110
        dta %00001010
        dta %00101010
        dta %00000000
        dta %00000000
        dta %00000000
        dta %10101000
        dta %10111100
        dta %10100000
        dta %10101000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00000000
; backslash
        dta %00000000
        dta %00100000
        dta %00101000
        dta %00001010
        dta %00000010
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00001000
        dta %00101000
        dta %10100000
        dta %10000000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00100000
        dta %00101000
        dta %00001010
        dta %00000010
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00001000
        dta %00101000
        dta %10100000
        dta %10000000
        dta %00000000
        dta %00000000
        dta %00000000
        dta %00000000

net_fill_id
        dta 0
net_fill_commit_pending
        dta 0
net_fill_commit_clk
        dta 0
net_last_committed_fill_id
        dta 0
net_fill_retry_count
        dta 0
net_request_new_fill
        dta 0
; Netstream handler health (NS_GetStatus is clear-on-read, so returned bits
; are OR-accumulated here): bit 4 = input ring overflow, bit 7 = POKEY
; framing error, bit 6 = POKEY input overrun (mirrored by the handler).
net_handler_last_status
        dta 0
net_handler_overflow_count
        dta 0
net_handler_serial_error_count
        dta 0

; Cosmetic remote-shot tracers. remote_prev_fire scales with the configured
; visible-player count; the tracer pool itself stays fixed at three slots.
remote_prev_fire
        :NET_MAX_REMOTE_PLAYERS dta 0
rbullet_x
        :RBULLET_SLOTS dta 0
rbullet_y
        :RBULLET_SLOTS dta 0
rbullet_dir
        :RBULLET_SLOTS dta 0
rbullet_clk
        :RBULLET_SLOTS dta 0
rbullet_steps
        :RBULLET_SLOTS dta 0
rbullet_active
        :RBULLET_SLOTS dta 0
rbullet_drawn
        :RBULLET_SLOTS dta 0
rbullet_next
        dta 0
rbullet_index
        dta 0
remote_state_tmp
        dta 0
; Keyboard Space must remain cardinal after a diagonal joystick shot.
last_cardinal_aim
        dta DIR_RIGHT

; Guard: const tables must not grow into the title/message data at $5600.
        ert *>$5600

        org $5600
title_lines
        dta 2,15
        dta 38,53,42,41,50,37,33,44,45,TITLE_LINE_END
        dta 5,8
        dta 38,53,42,41,46,37,52,0,45,47,50,48,39,0,36,37,45,47,0,39,33,45,37,TITLE_LINE_END
; Rows 8-12: the story hook. Deliberately says what the player will DO and
; that something down there is deliberate, without naming the Deep Pump,
; Gorvak, or the cause -- those are the Grix reveal and must stay a reveal.
; "A TOWN IS DROWNING FROM UNDERNEATH."
        dta 8,2
        dta 33,0,52,47,55,46,0,41,51,0,36,50,47,55,46,41,46,39,0,38,50,47,45,0,53,46,36,37,50,46,37,33,52,40,14,TITLE_LINE_END
; "SOMETHING DOWN THERE WANTS IT THAT WAY."
        dta 9,0
        dta 51,47,45,37,52,40,41,46,39,0,36,47,55,46,0,52,40,37,50,37,0,55,33,46,52,51,0,41,52,0,52,40,33,52,0,55,33,57,14,TITLE_LINE_END
; "EXPLORE, FIGHT, AND GO DEEPER"
        dta 10,5
        dta 37,56,48,44,47,50,37,12,0,38,41,39,40,52,12,0,33,46,36,0,39,47,0,36,37,37,48,37,50,TITLE_LINE_END
; "UNTIL YOU FIND OUT WHAT."
        dta 11,8
        dta 53,46,52,41,44,0,57,47,53,0,38,41,46,36,0,47,53,52,0,55,40,33,52,14,TITLE_LINE_END
; "PLAY ALONE OR WITH FRIENDS"
        dta 12,7
        dta 48,44,33,57,0,33,44,47,46,37,0,47,50,0,55,41,52,40,0,38,50,41,37,46,36,51,TITLE_LINE_END
        dta 14,10
        dta 53,51,37,50,46,33,45,37,OS_COLON,TITLE_LINE_END
        dta 15,11
        dta 48,50,37,51,51,0,38,41,50,37,0,52,47,0,51,52,33,50,52,TITLE_LINE_END
        dta 16,6
        dta 48,50,37,51,51,0,35,0,52,47,0,35,40,33,46,39,37,0,53,51,37,50,46,33,45,37,TITLE_LINE_END
        dta 17,11
        dta 48,50,37,51,51,0,40,0,38,47,50,0,40,37,44,48,TITLE_LINE_END
; No "OPTION BAUD" line and no rate readout here: 31250 is the known-good
; rate and the title screen no longer advertises changing it. OPTION still
; cycles the rate (see title_baud_select) -- silently, as an escape hatch --
; and the connection-failed/unstable screens still show and offer it, which
; is where a player actually needs it.
        dta TITLE_END

connection_failed_lines
        dta 7,11
        dta 35,47,46,46,37,35,52,41,47,46,0,38,33,41,44,37,36,TITLE_LINE_END
        dta 10,11
        dta 46,47,0,51,37,50,54,37,50,0,38,47,53,46,36,TITLE_LINE_END
        dta 13,10
        dta 48,50,37,51,51,0,38,41,50,37,0,52,47,0,50,37,52,50,57,TITLE_LINE_END
        dta 19,8
        dta 47,48,52,41,47,46,0,34,33,53,36,TITLE_LINE_END
        dta TITLE_END

connection_unstable_lines
        dta 7,10
        dta 35,47,46,46,37,35,52,41,47,46,0,53,46,51,52,33,34,44,37,TITLE_LINE_END
        dta 10,13
        dta 52,50,57,0,44,47,55,37,50,0,34,33,53,36,TITLE_LINE_END
        dta 13,10
        dta 48,50,37,51,51,0,38,41,50,37,0,52,47,0,50,37,52,50,57,TITLE_LINE_END
        dta 19,8
        dta 47,48,52,41,47,46,0,34,33,53,36,TITLE_LINE_END
        dta TITLE_END

netstream_connect_lines
        dta 11,4
        dta 47,48,37,46,41,46,39,0,46,37,52,51,52,50,37,33,45,0,52,47,0,38,53,42,41,50,37,33,44,45,14,14,TITLE_LINE_END
        dta TITLE_END

netstream_pass_lines
        dta 7,12
        dta 46,37,52,51,52,50,37,33,45,0,48,33,51,51,TITLE_LINE_END
        dta 10,13
        dta 37,35,40,47,0,50,37,35,37,41,54,37,36,TITLE_LINE_END
        dta 13,10
        dta 35,47,46,52,41,46,53,41,46,39,0,39,33,45,37,TITLE_LINE_END
        dta TITLE_END

netstream_init_fail_lines
        dta 7,12
        dta 46,37,52,51,52,50,37,33,45,0,38,33,41,44,TITLE_LINE_END
        dta 10,15
        dta 41,46,41,52,0,38,33,41,44,37,36,TITLE_LINE_END
        dta 13,10
        dta 35,47,46,52,41,46,53,41,46,39,0,39,33,45,37,TITLE_LINE_END
        dta TITLE_END

netstream_send_fail_lines
        dta 7,12
        dta 46,37,52,51,52,50,37,33,45,0,38,33,41,44,TITLE_LINE_END
        dta 10,15
        dta 51,37,46,36,0,38,33,41,44,37,36,TITLE_LINE_END
        dta 13,10
        dta 35,47,46,52,41,46,53,41,46,39,0,39,33,45,37,TITLE_LINE_END
        dta TITLE_END

netstream_recv_fail_lines
        dta 7,12
        dta 46,37,52,51,52,50,37,33,45,0,38,33,41,44,TITLE_LINE_END
        dta 10,15
        dta 50,37,35,54,0,38,33,41,44,37,36,TITLE_LINE_END
        dta 13,10
        dta 35,47,46,52,41,46,53,41,46,39,0,39,33,45,37,TITLE_LINE_END
        dta TITLE_END

start_level_lines
        dta 8,15
        dta 39,37,52,0,50,37,33,36,57,TITLE_LINE_END
        dta 11,11
        dta 48,50,47,52,37,35,52,0,52,40,37,0,38,47,50,37,51,52,TITLE_LINE_END
        dta 14,13
        dta 44,37,54,37,44,0,51,52,33,50,52,41,46,39,TITLE_LINE_END
        dta TITLE_END

; ATASCII (not screen codes): printed through E: via PUT_RECORD, which
; also wants the terminating $9B EOL included in the buffer.
; "ENTER USERNAME (10 MAX):" + EOL
username_prompt_text
        dta 69,78,84,69,82,32,85,83,69,82,78,65,77,69,32,40,49,48,32,77,65,88,41,58,155
USERNAME_PROMPT_TEXT_LEN = *-username_prompt_text

; "NAME TAKEN. PICK ANOTHER." + EOL + "USERNAME (10 MAX):" + EOL
username_prompt_taken_text
        dta 78,65,77,69,32,84,65,75,69,78,46,32,80,73,67,75,32,65,78,79,84,72,69,82,46,155
        dta 85,83,69,82,78,65,77,69,32,40,49,48,32,77,65,88,41,58,155
USERNAME_PROMPT_TAKEN_TEXT_LEN = *-username_prompt_taken_text

; "ENTER SERVER HOST (32 MAX):" + EOL
server_host_prompt_text
        dta 69,78,84,69,82,32,83,69,82,86,69,82,32,72,79,83,84,32,40,51,50,32,77,65,88,41,58,155
SERVER_HOST_PROMPT_TEXT_LEN = *-server_host_prompt_text

        icl "generated/server_host_default.inc"

n_devicespec_prefix
        dta 78,49,58,84,67,80,58,47,47
N_DEVICESPEC_PREFIX_LEN = *-n_devicespec_prefix

read_keyboard_stick
        lda SKSTAT
        and #KEY_DOWN_MASK
        bne read_keyboard_stick_neutral
        lda KEY
        cmp #KEY_NONE
        beq read_keyboard_stick_neutral
        and #KEY_CODE_MASK
        cmp #KEY_W
        beq read_keyboard_stick_up
        cmp #KEY_S
        beq read_keyboard_stick_down
        cmp #KEY_A
        beq read_keyboard_stick_left
        cmp #KEY_D
        beq read_keyboard_stick_right
read_keyboard_stick_neutral
        lda #$0f
        rts
read_keyboard_stick_up
        lda #%1110
        rts
read_keyboard_stick_down
        lda #%1101
        rts
read_keyboard_stick_left
        lda #%1011
        rts
read_keyboard_stick_right
        lda #%0111
        rts

read_keyboard_realtime_actions
        lda SKSTAT
        and #KEY_DOWN_MASK
        bne read_keyboard_realtime_release
        lda KEY
        cmp #KEY_NONE
        beq read_keyboard_realtime_release
        and #KEY_CODE_MASK
        cmp net_key_repeat_latch
        beq read_keyboard_realtime_done
        sta net_key_repeat_latch
        cmp #KEY_RETURN
        bne read_keyboard_not_return
        inc net_pickup_counter
        rts
read_keyboard_not_return
        cmp #KEY_I
        bne read_keyboard_not_i
        lda #1
        sta net_modal_request
        rts
read_keyboard_not_i
        cmp #KEY_M
        bne read_keyboard_not_m_check
        lda #2
        sta net_modal_request
        rts
read_keyboard_not_m_check
        cmp #KEY_H
        bne read_keyboard_not_h
        lda #4
        sta net_modal_request
        rts
read_keyboard_not_h
        cmp #KEY_P
        bne read_keyboard_not_p
; PvP toggle: an incrementing counter, not a flag bit, so the toggle
; can't be silently dropped by the outgoing-packet send throttle (the
; same class of bug the fire button had before net_fire_counter was
; wired up). The server flips pvp_enabled on each new counter value it
; sees; this key never touches gameplay state directly.
        inc net_pvp_toggle_counter
        rts
read_keyboard_not_p
        cmp #KEY_V
        bne read_keyboard_not_v
        jmp netstream_cycle_walk_speed
read_keyboard_not_v
        cmp #KEY_ESC
        bne read_keyboard_not_esc
        sta net_modal_request
        rts
read_keyboard_not_esc
; SPACE fires once per fresh keydown, in the player's current facing
; direction (aim_dir) -- independent of WASD entirely. The keyboard can
; only latch one key at a time, so it can't reliably report "direction
; held + SPACE held" the way a joystick's separate stick/trigger lines
; can; rather than try to detect that combination, SPACE just always
; shoots once when pressed. net_key_repeat_latch (already updated above)
; guarantees this only fires on the transition into SPACE, not every
; frame it's held, and read_keyboard_realtime_release below re-arms it
; once SPACE (or whatever key) is released. maybe_spawn_bullet (not the
; bare spawn_bullet_visual) so input_buttons gets NET_BUTTON_FIRE set --
; the server keys its hit detection off that bit, not just the visual.
; Also nudges net_pickup_counter like RETURN/joystick fire, so SPACE next
; to an NPC talks to them instead of just shooting at nothing.
        cmp #KEY_SPACE
        bne read_keyboard_realtime_done
        inc net_pickup_counter
        lda last_cardinal_aim
        sta aim_dir
        jsr maybe_spawn_bullet
        rts
read_keyboard_realtime_release
        lda #KEY_NONE
        sta net_key_repeat_latch
read_keyboard_realtime_done
        rts

; Relocated network, remote-tracer, title identity, and rename helpers. This
; segment keeps the tight main and $8000 blocks below their guarded boundaries.
        org $5A00

; NET_RT_REMOTE_PLAYERS: count in the status byte (offset 3), followed by
; build-configurable x,y,facing,state records. State bits 2-3 carry the
; server's accepted-shot counter for cosmetic remote tracers.
netstream_apply_remote_players
        lda net_realtime_packet+NET_RT_REMOTE_COUNT_OFFSET
        cmp #NET_MAX_REMOTE_PLAYERS+1
        bcc netstream_remote_count_ok
        lda #NET_MAX_REMOTE_PLAYERS
netstream_remote_count_ok
        sta remote_count_tmp
        lda #0
        sta net_world_changed
        ldx #0
        ldy #NET_RT_REMOTE_PAYLOAD_OFFSET
netstream_remote_copy_loop
        cpx remote_count_tmp
        beq netstream_remote_clear_rest
        lda #0
        sta work
        lda net_realtime_packet,y
        cmp remote_x,x
        beq netstream_remote_x_same
        inc net_world_changed
        inc work
netstream_remote_x_same
        sta remote_x,x
        iny
        lda net_realtime_packet,y
        cmp remote_y,x
        beq netstream_remote_y_same
        inc net_world_changed
        inc work
netstream_remote_y_same
        sta remote_y,x
        iny
        lda net_realtime_packet,y
        sta remote_facing,x
        iny
        lda net_realtime_packet,y
        sta remote_state_tmp
        cmp remote_alive,x
        beq netstream_remote_state_same
        inc net_world_changed
netstream_remote_state_same
        lda remote_alive,x
        beq netstream_remote_store_fire_baseline
        lda remote_state_tmp
        and #REMOTE_STATE_FIRE_MASK
        cmp remote_prev_fire,x
        beq netstream_remote_store_state
        lda work
        pha
        jsr spawn_remote_bullet
        pla
        sta work
netstream_remote_store_fire_baseline
        lda remote_state_tmp
        and #REMOTE_STATE_FIRE_MASK
        sta remote_prev_fire,x
netstream_remote_store_state
        lda remote_state_tmp
        sta remote_alive,x
        lda work
        beq netstream_remote_not_moved
        lda remote_anim,x
        eor #1
        sta remote_anim,x
netstream_remote_not_moved
        iny
        inx
        jmp netstream_remote_copy_loop
netstream_remote_clear_rest
        cpx #NET_MAX_REMOTE_PLAYERS
        beq netstream_remote_copy_done
        lda remote_alive,x
        beq netstream_remote_clear_fire
        inc net_world_changed
        lda #0
        sta remote_alive,x
netstream_remote_clear_fire
        lda #0
        sta remote_prev_fire,x
        inx
        jmp netstream_remote_clear_rest
netstream_remote_copy_done
        lda net_world_changed
        beq netstream_remote_done
        inc perf_screen_dirty_sets
        lda #1
        sta net_screen_dirty
netstream_remote_done
        rts

; X is the remote-player slot and Y is the packet offset. rbullet_index is
; safe as parser-depth scratch; the frame update resets it before use.
spawn_remote_bullet
        tya
        pha
        stx rbullet_index
        lda remote_facing,x
        cmp #8
        bcs spawn_remote_bullet_done
        lda rbullet_next
        tax
        clc
        adc #1
        cmp #RBULLET_SLOTS
        bcc spawn_remote_bullet_store_next
        lda #0
spawn_remote_bullet_store_next
        sta rbullet_next
        lda rbullet_active,x
        beq spawn_remote_bullet_seed
        lda rbullet_drawn,x
        beq spawn_remote_bullet_seed
        txa
        pha
        lda rbullet_x,x
        sta target_x
        lda rbullet_y,x
        sta target_y
        jsr draw_target_world_cell
        pla
        tax
spawn_remote_bullet_seed
        ldy rbullet_index
        lda remote_x,y
        sta rbullet_x,x
        lda remote_y,y
        sta rbullet_y,x
        lda remote_facing,y
        sta rbullet_dir,x
        lda #0
        sta rbullet_steps,x
        sta rbullet_drawn,x
        lda RTCLOK
        sec
        sbc #BULLET_DELAY
        sta rbullet_clk,x
        lda #1
        sta rbullet_active,x
spawn_remote_bullet_done
        pla
        tay
        ldx rbullet_index
        rts

bullet_target_hits_terrain
remote_bullet_hits_terrain
        jsr world_cell_ptr
        ldy #0
        lda (ptr),y
        cmp #TREE_FULL
        beq remote_bullet_hits_terrain_yes
        cmp #TREE_DAMAGED
        beq remote_bullet_hits_terrain_yes
        cmp #BORDER
        beq remote_bullet_hits_terrain_yes
        cmp #TILE_WATER
        beq remote_bullet_hits_terrain_yes
        cmp #TILE_BUILDING
        beq remote_bullet_hits_terrain_yes
        cmp #TILE_CAVE_WALL
        beq remote_bullet_hits_terrain_yes
        cmp #BEAVER
        beq remote_bullet_hits_terrain_yes
        lda #0
        rts
remote_bullet_hits_terrain_yes
        lda #1
        rts

clear_remote_bullets
        lda #0
        sta rbullet_next
        sta rbullet_index
        ldx #0
clear_remote_bullets_loop
        cpx #RBULLET_SLOTS
        beq clear_remote_fire_baselines
        sta rbullet_active,x
        sta rbullet_drawn,x
        inx
        jmp clear_remote_bullets_loop
clear_remote_fire_baselines
        ldx #0
clear_remote_fire_loop
        cpx #NET_MAX_REMOTE_PLAYERS
        beq clear_remote_bullets_done
        sta remote_prev_fire,x
        inx
        jmp clear_remote_fire_loop
clear_remote_bullets_done
        lda #0
        rts

; Relocated from the main segment; gained request-new-fill flag handling.
netstream_send_resync_request
        lda #NET_RT_RESYNC_REQUEST
        jsr netstream_tx_prepare
; Report our window origin: a small gap is repaired by the server
; rewinding its edge stream; only large/unknown gaps get a row fill.
; During a map fill the cached origin is the OLD map's -- send an
; out-of-range origin (255) so the server always answers with a full fill.
        lda net_map_fill_pending
        beq netstream_resync_req_window_origin
        lda #255
        sta net_realtime_tx_packet+6
        sta net_realtime_tx_packet+7
        jmp netstream_resync_req_send
netstream_resync_req_window_origin
        lda net_window_origin_x
        sta net_realtime_tx_packet+6
        lda net_window_origin_y
        sta net_realtime_tx_packet+7
netstream_resync_req_send
; NACK: while a staged fill is active, report its origin and the 24-bit
; received-row bitmap so the server resends only the missing rows instead
; of restarting a full 24-row fill. With no fill active the bytes stay
; zero (tx_prepare cleared them), which requests the full fill.
        lda net_row_fill_active
        beq netstream_resync_req_no_fill_state
        lda net_pending_origin_x
        sta net_realtime_tx_packet+8
        lda net_pending_origin_y
        sta net_realtime_tx_packet+9
        lda net_window_row_mask0
        sta net_realtime_tx_packet+10
        lda net_window_row_mask1
        sta net_realtime_tx_packet+11
        lda net_window_row_mask2
        sta net_realtime_tx_packet+12
        lda net_fill_id
        sta net_realtime_tx_packet+NET_RT_RESYNC_FILL_ID_OFFSET
        lda #NET_RESYNC_FLAG_FILL_ACTIVE
        sta net_realtime_tx_packet+NET_RT_RESYNC_FLAGS_OFFSET
netstream_resync_req_no_fill_state
; After a dead-fill abort, ask the server to cancel its transaction and
; start a clean full fill regardless of gap heuristics.
        lda net_request_new_fill
        beq netstream_resync_req_flags_done
        lda net_realtime_tx_packet+NET_RT_RESYNC_FLAGS_OFFSET
        ora #NET_RESYNC_FLAG_NEW_FILL
        sta net_realtime_tx_packet+NET_RT_RESYNC_FLAGS_OFFSET
netstream_resync_req_flags_done
        jsr netstream_tx_send
        bcs netstream_resync_req_send_fail
        lda #0
        sta net_request_new_fill
        lda net_fill_commit_pending
        beq netstream_resync_commit_done
        jsr netstream_send_window_commit
netstream_resync_commit_done
; Row masks are never cleared here. The retry timer is shorter than a
; 24-row fill at one row per server tick, so a clear would wipe bits for
; rows already staged and the fill could never complete. Mask lifetime is
; owned by netstream_window_row_route's start-fill path.
        lda #1
        sta net_resync_pending
        lda RTCLOK
        sta net_resync_request_clk
        rts
netstream_resync_req_send_fail
        lda #0
        sta network_enabled
        sta network_realtime_enabled
        jsr NETSTREAM_END_STREAM
        rts

; Silence-retry service (was inline in main_loop). Accepted rows re-stamp
; net_resync_request_clk, so the delay measures a stalled fill/desync, not
; time since the last request. After NET_FILL_RETRY_LIMIT consecutive
; retries with no row progress the staged transaction is dead: drop it (the
; active cache stays valid and drawable) and request a clean fill.
netstream_resync_retry_check
; Any active staged fill arms the silence NACK -- including fills the
; SERVER initiated (origin gap, commit-timeout restart), which previously
; never NACKed their missing rows and could only recover via destructive
; full restarts.
        lda net_resync_pending
        ora net_map_fill_pending
        ora net_row_fill_active
        beq netstream_retry_check_done
        lda RTCLOK
        sec
        sbc net_resync_request_clk
        cmp #NET_RESYNC_RETRY_DELAY
        bcc netstream_retry_check_done
        lda net_row_fill_active
        beq netstream_retry_send
        lda net_fill_retry_count
        cmp #NET_FILL_RETRY_LIMIT
        bcs netstream_abort_dead_fill
        inc net_fill_retry_count
netstream_retry_send
        jsr netstream_send_resync_request
netstream_retry_check_done
        rts

netstream_abort_dead_fill
        lda #0
        sta net_row_fill_active
        sta net_fill_id
        sta net_fill_retry_count
        sta net_fill_commit_pending
        jsr netstream_clear_window_row_masks
        lda #1
        sta net_request_new_fill
        jmp netstream_send_resync_request

; Shared realtime service pass: outbound keepalive/player state, receive
; drain, and a paced retry of a pending WINDOW_COMMIT. Called from the main
; loop and (via the modal wrapper) from modal wait loops, so the server
; keeps hearing position/keepalives everywhere the client blocks.
netstream_service_realtime_io
        jsr netstream_send_auth_keepalive
; While a map change is queued but handle_map_change has not yet snapped
; the player to the new spawn (a modal can hold it off for seconds), the
; local position is still old-map coordinates. Reporting them against the
; new map would mislocate the player once the server's transition
; protection expires. AUTH keepalives above keep the session alive.
        lda net_map_change_pending
        bne netstream_service_io_skip_state
        jsr netstream_send_player_state_realtime
netstream_service_io_skip_state
        jsr netstream_recv_realtime_packets
        lda net_fill_commit_pending
        beq netstream_service_io_done
        lda net_row_fill_active
        bne netstream_service_io_done
        lda RTCLOK
        sec
        sbc net_fill_commit_clk
        cmp #NET_COMMIT_RETRY_DELAY
        bcc netstream_service_io_done
        jsr netstream_send_window_commit
netstream_service_io_done
        jsr netstream_send_net_stats_paced
        jmp netstream_poll_handler_status

; Poll the handler's sticky serial-error status (clear-on-read) roughly
; once per 32 frames. Bit 4 = input ring overflow; bits 7/6 = POKEY framing
; error / input overrun mirrored by the handler. On overflow, bytes were
; lost inside a possibly half-received packet: drop only the partial RX
; accumulator (the $AD scan re-frames on the next intact packet) and nudge
; a resync unless a fill is already staging -- its silence NACK recovers
; any missing rows without discarding staged progress.
netstream_poll_handler_status
        lda network_realtime_enabled
        beq netstream_poll_status_done
        lda RTCLOK
        and #$1f
        bne netstream_poll_status_done
        jsr NETSTREAM_GET_STATUS
        ora #0
        beq netstream_poll_status_done
        pha
        ora net_handler_last_status
        sta net_handler_last_status
        pla
        pha
        and #$c0
        beq netstream_poll_status_no_serial
        inc net_handler_serial_error_count
netstream_poll_status_no_serial
        pla
        and #$10
        beq netstream_poll_status_done
        inc net_handler_overflow_count
        lda #0
        sta net_rt_rx_index
        lda net_row_fill_active
        ora net_map_fill_pending
        bne netstream_poll_status_done
        lda #1
        sta net_terrain_desync
netstream_poll_status_done
        rts

; Modal variant: same service plus the attract-mode refresh the modal loop
; performed before it serviced the network.
netstream_service_modal_io
        jsr disable_attract_mode
        jmp netstream_service_realtime_io

; The commit must carry the transaction's own fill id (net_fill_id), never a
; byte from the RX packet buffer: on a retry the buffer holds whatever
; packet arrived last, not the final window row.
netstream_send_window_commit
        lda RTCLOK
        sta net_fill_commit_clk
        lda #NET_RT_WINDOW_COMMIT
        jsr netstream_tx_prepare
        lda net_fill_id
        sta net_realtime_tx_packet+6
        lda net_pending_origin_x
        sta net_realtime_tx_packet+7
        lda net_pending_origin_y
        sta net_realtime_tx_packet+8
        lda current_map_id
        sta net_realtime_tx_packet+9
        lda #1
        sta net_realtime_tx_packet+10
        jsr netstream_tx_send
        bcs netstream_window_commit_fail
; Pending stays set until the server's WINDOW_COMMIT_ACK clears it; the
; paced retry in the service routine re-sends until then (duplicates are
; re-acked server-side).
        clc
        rts
netstream_window_commit_fail
        sec
        rts

draw_hud_gold
        lda #39
        jsr status_store_tile
        inc screen_x
        lda #OS_COLON
        jsr status_store_tile
        inc screen_x
        lda inventory_gold_lo
        sta hud_digits_value_lo
        lda inventory_gold_hi
        sta hud_digits_value_hi
        jmp hud_draw_four_digits_value

; Relocated from the full $8000 block to leave room for Phase 37 cache
; transaction code and Phase 38 receive maintenance.
draw_remote_players
        lda #0
        sta enemy_index
draw_remote_players_loop
        ldx enemy_index
        cpx #NET_MAX_REMOTE_PLAYERS
        beq draw_remote_players_done
        lda remote_alive,x
        beq draw_remote_players_next
        lda remote_x,x
        sta target_x
        lda remote_y,x
        sta target_y
        jsr target_in_view
        beq draw_remote_players_next
        ldx enemy_index
        lda remote_alive,x
        and #REMOTE_PLAYER_STATE_PVP_ENABLED
        beq draw_remote_not_pvp
        lda #$80
        jmp draw_remote_recolor_store
draw_remote_not_pvp
        lda #0
draw_remote_recolor_store
        sta remote_recolor_bit
        lda remote_facing,x
        jsr select_remote_facing_base
        jmp draw_remote_player_frame
draw_remote_player_frame
        clc
        adc remote_anim,x
        jsr draw_remote_player_sprite_2x2
draw_remote_players_next
        inc enemy_index
        jmp draw_remote_players_loop
draw_remote_players_done
        rts

; Diagonal movement is allowed only when both orthogonal side cells are
; clear. This prevents cutting through a one-tile wall or water corner.
realtime_check_up_left
        lda player_x
        sec
        sbc #1
        sta target_x
        lda player_y
        sta target_y
        jsr realtime_check_diagonal_cell
        bcs realtime_check_up_left_second
        clc
        rts
realtime_check_up_left_second
        lda player_x
        sta target_x
        lda player_y
        sec
        sbc #1
        sta target_y
        jmp realtime_check_diagonal_cell
realtime_check_up_right
        lda player_x
        clc
        adc #1
        sta target_x
        lda player_y
        sta target_y
        jsr realtime_check_diagonal_cell
        bcs realtime_check_up_right_second
        clc
        rts
realtime_check_up_right_second
        lda player_x
        sta target_x
        lda player_y
        sec
        sbc #1
        sta target_y
        jmp realtime_check_diagonal_cell
realtime_check_down_left
        lda player_x
        sec
        sbc #1
        sta target_x
        lda player_y
        clc
        adc #1
        sta target_y
        jsr realtime_check_diagonal_cell
        bcs realtime_check_down_left_second
        clc
        rts
realtime_check_down_left_second
        lda player_x
        sta target_x
        lda player_y
        clc
        adc #1
        sta target_y
        jmp realtime_check_diagonal_cell
realtime_check_down_right
        lda player_x
        clc
        adc #1
        sta target_x
        lda player_y
        clc
        adc #1
        sta target_y
        jsr realtime_check_diagonal_cell
        bcs realtime_check_down_right_second
        clc
        rts
realtime_check_down_right_second
        lda player_x
        sta target_x
        lda player_y
        clc
        adc #1
        sta target_y
        jmp realtime_check_diagonal_cell
realtime_check_diagonal_cell
        jsr world_cell_ptr
        ldy #0
        lda (ptr),y
        cmp #TREE_FULL
        beq realtime_check_diagonal_fail
        cmp #TREE_DAMAGED
        beq realtime_check_diagonal_fail
        cmp #BORDER
        beq realtime_check_diagonal_fail
        cmp #TILE_WATER
        beq realtime_check_diagonal_fail
        cmp #TILE_BUILDING
        beq realtime_check_diagonal_fail
        cmp #TILE_CAVE_WALL
        beq realtime_check_diagonal_fail
        cmp #TILE_FARMER
        beq realtime_check_diagonal_fail
        cmp #TILE_GOBLIN_NPC
        beq realtime_check_diagonal_fail
        sec
        rts
realtime_check_diagonal_fail
        clc
        rts

title_refresh_identity
        lda #TITLE_IDENTITY_NEW
        sta title_identity_state
        jsr appkey_check_and_read
        lda has_identity
        beq title_refresh_identity_done
        jsr appkey_resume_identity
        bcs title_refresh_identity_unavailable
        lda #TITLE_IDENTITY_READY
        sta title_identity_state
title_refresh_identity_done
        rts
title_refresh_identity_unavailable
        lda #TITLE_IDENTITY_UNAVAILABLE
        sta title_identity_state
        rts

; Resume a known AppKey token and persist the server's canonical username.
; Carry set means no authoritative title identity is available.
appkey_resume_identity
        jsr n_login_open
        bcs appkey_resume_identity_fail
        jsr login_build_resume_request
        jsr login_checksum_and_send
        bcs appkey_resume_identity_close_fail
        jsr login_recv_response
        bcs appkey_resume_identity_close_fail
        jsr n_close
        jsr login_parse_resume_response
        bcs appkey_resume_identity_fail
        lda login_status
        bne appkey_resume_identity_fail
        jsr appkey_store_identity
        bcs appkey_resume_identity_fail
        clc
        rts
appkey_resume_identity_close_fail
        jsr n_close
appkey_resume_identity_fail
        sec
        rts

draw_title_identity
        jsr draw_title_change_option
        lda #14
        sta screen_y
        lda #20
        sta screen_x
        jsr screen_cell_ptr
        lda title_identity_state
        cmp #TITLE_IDENTITY_READY
        beq draw_title_identity_name
        cmp #TITLE_IDENTITY_UNAVAILABLE
        beq draw_title_identity_unavailable
        lda #<title_identity_new_text
        sta wptr
        lda #>title_identity_new_text
        sta wptr+1
        jmp draw_title_identity_static
draw_title_identity_unavailable
        lda #<title_identity_unavailable_text
        sta wptr
        lda #>title_identity_unavailable_text
        sta wptr+1
draw_title_identity_static
        ldy #0
draw_title_identity_static_loop
        lda (wptr),y
        cmp #TITLE_END
        beq draw_title_identity_done
        sta (ptr),y
        iny
        jmp draw_title_identity_static_loop
draw_title_identity_name
        ldy #0
draw_title_identity_name_loop
        cpy username_len
        beq draw_title_identity_done
        lda username_buf,y
        cmp #96
        bcs draw_title_identity_name_store
        sec
        sbc #32
draw_title_identity_name_store
        sta (ptr),y
        iny
        jmp draw_title_identity_name_loop
draw_title_identity_done
        rts

draw_title_change_option
draw_title_change_option_done
        rts

; Prompt and submit a rename for the title's already-resumed token. Empty
; input returns to the title without changing either server or AppKey state.
title_change_username_flow
        lda #USERNAME_PROMPT_NORMAL
        sta username_prompt_mode
title_change_username_prompt
        jsr username_prompt_screen
        bcs title_change_username_fail
        lda username_len
        beq title_change_username_done
        jsr login_rename
        bcs title_change_username_fail
        lda login_status
        beq title_change_username_accept
        cmp #LOGIN_STATUS_RENAME_TAKEN
        bne title_change_username_fail
        lda #USERNAME_PROMPT_TAKEN
        sta username_prompt_mode
        jmp title_change_username_prompt
title_change_username_accept
        jsr appkey_store_identity
        bcs title_change_username_fail
        lda #TITLE_IDENTITY_READY
        sta title_identity_state
title_change_username_done
        lda #USERNAME_PROMPT_NORMAL
        sta username_prompt_mode
        clc
        rts
title_change_username_fail
        lda #USERNAME_PROMPT_NORMAL
        sta username_prompt_mode
        sec
        rts

login_rename
        jsr n_login_open
        bcs login_rename_fail
        jsr login_build_rename_request
        jsr login_checksum_and_send
        bcs login_rename_close_fail
        jsr login_recv_response
        bcs login_rename_close_fail
        jsr n_close
        jsr login_parse_rename_response
        bcs login_rename_fail
        clc
        rts
login_rename_close_fail
        jsr n_close
login_rename_fail
        sec
        rts

login_build_rename_request
        lda #NET_PACKET_MAGIC
        sta login_pkt_buf+0
        lda #NETSTREAM_PROTOCOL_VERSION
        sta login_pkt_buf+1
        lda #LOGIN_PKT_RENAME_REQUEST
        sta login_pkt_buf+2
        lda token_len
        sta login_pkt_buf+4
        ldy #0
login_build_rename_token_loop
        cpy token_len
        beq login_build_rename_username_len
        lda token_buf,y
        sta login_pkt_buf+5,y
        iny
        jmp login_build_rename_token_loop
login_build_rename_username_len
        lda username_len
        sta login_pkt_buf+5,y
        iny
        ldx #0
login_build_rename_username_loop
        cpx username_len
        beq login_build_rename_done
        lda username_buf,x
        sta login_pkt_buf+5,y
        iny
        inx
        jmp login_build_rename_username_loop
login_build_rename_done
        lda token_len
        clc
        adc username_len
        adc #2
        sta login_payload_len
        sta login_pkt_buf+3
        rts

login_parse_rename_response
        jsr login_verify_checksum
        bcs login_parse_rename_fail
        lda login_pkt_buf+2
        cmp #LOGIN_PKT_RENAME_RESPONSE
        bne login_parse_rename_fail
        lda login_pkt_buf+3
        cmp #1
        bne login_parse_rename_fail
        lda login_pkt_buf+4
        cmp #LOGIN_STATUS_RENAME_TOKEN_UNKNOWN+1
        bcs login_parse_rename_fail
        sta login_status
        clc
        rts
login_parse_rename_fail
        sec
        rts

title_identity_new_text
        dta 46,37,55,0,48,44,33,57,37,50,TITLE_END
title_identity_unavailable_text
        dta 51,37,50,54,37,50,0,53,46,33,54,33,41,44,33,34,44,37,TITLE_END

title_change_username_down
        lda SKSTAT
        and #KEY_DOWN_MASK
        bne title_change_username_down_no
        lda KEY
        cmp #KEY_NONE
        beq title_change_username_down_no
        and #KEY_CODE_MASK
        cmp #KEY_C
        bne title_change_username_down_no
        lda #0
        rts
title_change_username_down_no
        lda #1
        rts

wait_title_action
title_wait_press
        jsr disable_attract_mode
        lda CONSOL
        and #4
        beq title_wait_option_release
        lda CONSOL
        and #2
        beq title_wait_select_release
        jsr title_help_down
        bne title_wait_fire_check
title_help_release
        jsr disable_attract_mode
        jsr title_help_down
        beq title_help_release
        lda #TITLE_ACTION_HELP
        rts
title_wait_fire_check
        jsr title_change_username_down
        bne title_wait_fire_check_after_change
title_change_username_release
        jsr disable_attract_mode
        jsr title_change_username_down
        beq title_change_username_release
        lda title_identity_state
        lda #KEY_NONE
        sta KEY
        lda #TITLE_ACTION_CHANGE_USERNAME
        rts
title_wait_fire_check_after_change
        jsr title_fire_or_space_down
        bne title_wait_press
title_wait_release
        jsr disable_attract_mode
        jsr title_fire_or_space_down
        beq title_wait_release
        lda #0
        rts
title_wait_select_release
        jsr disable_attract_mode
        lda CONSOL
        and #2
        beq title_wait_select_release
        lda #TITLE_ACTION_HOST
        rts
title_wait_option_release
        jsr disable_attract_mode
        lda CONSOL
        and #4
        beq title_wait_option_release
        lda #TITLE_ACTION_BAUD
        rts

        ert *>WORLD

; ---------------------------------------------------------------------------
; Realtime protocol v3 engine (Phase 39). Lives in the $6C00-$6FFF gap
; between the two 12-page terrain caches (WORLD uses $6000-$6BFF,
; WORLD_PENDING uses $7000-$7BFF; nothing addresses $6C00-$6FFF).
;
; Wire format: COBS(raw frame) + $00 delimiter. Raw frame:
;   +0 payload length N, +1 version(3), +2 type, +3 status, +4/5 seq,
;   +6.. payload, then CRC-16/CCITT-FALSE (lo,hi) over bytes 0..5+N.
; The v2 header offsets are preserved, so every apply handler reads the
; decoded frame unchanged; the tail beyond the sent payload is re-padded
; with zeros (the server strips trailing zeros on encode).
        org $6C00

; CRC-16/CCITT-FALSE nibble tables (poly $1021).
netstream_crc16_tab_hi
        dta $00,$10,$20,$30,$40,$50,$60,$70,$81,$91,$A1,$B1,$C1,$D1,$E1,$F1
netstream_crc16_tab_lo
        dta $00,$21,$42,$63,$84,$A5,$C6,$E7,$08,$29,$4A,$6B,$8C,$AD,$CE,$EF

; Payload lengths for the frame types this client transmits (indexed by
; type; types the client never sends stay zero).
netstream_v3_txlen_tab
        dta 0,10,0,0,0,0,0,0,0,0,0,0,0,4,0,9,0,0,0,3,5,4,0,10

netstream_rt3_preamble_data
        dta 82,84,51,10                 ; "RT3" + newline

net_crc_lo
        dta 0
net_crc_hi
        dta 0
net_crc_nib
        dta 0
net_v3_len
        dta 0
net_v3_in
        dta 0
net_v3_out
        dta 0
net_v3_code
        dta 0
net_v3_code_pos
        dta 0
net_v3_tx_len
        dta 0
net_v3_raw_len
        dta 0
; Phase 40 acknowledged cache steps: last applied revision, the pending
; step's revision, and the pre-apply origin for success detection.
net_cache_rev_lo
        dta 0
net_cache_rev_hi
        dta 0
net_cache_rev_pend_lo
        dta 0
net_cache_rev_pend_hi
        dta 0
net_edge_prev_origin_x
        dta 0
net_edge_prev_origin_y
        dta 0
net_stats_clk
        dta 0
; Walk cadence: frames a held direction waits between tile steps. Preset
; cycle via the W key; slower cadence keeps sustained walks inside the
; acknowledged cache-step throughput on high-latency links.
net_move_repeat_cfg
        dta 8
net_walk_speed_index
        dta 1
netstream_walk_speed_tab
        dta 6,8,10,12,15

; Send the raw realtime-v3 classification preamble. Carry set on failure.
netstream_send_rt3_preamble
        ldx #0
netstream_rt3_preamble_loop
        lda netstream_rt3_preamble_data,x
        stx net_v3_in
        jsr netstream_send_raw_byte
        ldx net_v3_in
        bcs netstream_rt3_preamble_fail
        inx
        cpx #4
        bne netstream_rt3_preamble_loop
        clc
        rts
netstream_rt3_preamble_fail
        sec
        rts

; CRC-16 update: A = data byte, accumulates into net_crc_lo/hi.
netstream_crc16_update
        pha
        lsr
        lsr
        lsr
        lsr
        jsr netstream_crc16_nibble
        pla
        and #$0f
; falls through
netstream_crc16_nibble
        sta net_crc_nib
        lda net_crc_hi
        lsr
        lsr
        lsr
        lsr
        eor net_crc_nib
        tax
        asl net_crc_lo
        rol net_crc_hi
        asl net_crc_lo
        rol net_crc_hi
        asl net_crc_lo
        rol net_crc_hi
        asl net_crc_lo
        rol net_crc_hi
        lda net_crc_lo
        eor netstream_crc16_tab_lo,x
        sta net_crc_lo
        lda net_crc_hi
        eor netstream_crc16_tab_hi,x
        sta net_crc_hi
        rts

; One received stream byte in A. Nonzero bytes accumulate into the RX
; buffer; a zero delimiter completes a frame. An over-long encoded frame
; enters discard-until-delimiter state.
netstream_v3_rx_byte
        cmp #0
        beq netstream_v3_rx_delimiter
        ldx net_v3_discard
        bne netstream_v3_rx_done
        ldx net_rt_rx_index
        cpx #NET_REALTIME_PACKET_BYTES
        bcs netstream_v3_rx_overflow
        sta net_realtime_packet,x
        inc net_rt_rx_index
netstream_v3_rx_done
        rts
netstream_v3_rx_overflow
        inc net_rx_drops
        lda #1
        sta net_v3_discard
        rts
netstream_v3_rx_delimiter
        lda net_v3_discard
        beq netstream_v3_rx_frame
        lda #0
        sta net_v3_discard
        sta net_rt_rx_index
        rts
netstream_v3_rx_frame
        lda net_rt_rx_index
        beq netstream_v3_rx_done
        jsr netstream_v3_process_frame
        lda #0
        sta net_rt_rx_index
        rts

; COBS-decode the accumulated frame in place, validate the raw frame, pad
; the tail with zeros, and dispatch it. Invalid frames just bump the drop
; counter; the stream is already aligned by the delimiter.
netstream_v3_process_frame
        lda net_rt_rx_index
        sta net_v3_len
        lda #0
        sta net_v3_in
        sta net_v3_out
netstream_v3_cobs_loop
        lda net_v3_in
        cmp net_v3_len
        bcs netstream_v3_cobs_done
        tax
        lda net_realtime_packet,x
        beq netstream_v3_frame_bad_near
        sta net_v3_code
        inc net_v3_in
        dec net_v3_code
        jmp netstream_v3_cobs_copy
netstream_v3_frame_bad_near
        jmp netstream_v3_frame_bad
netstream_v3_cobs_copy
        lda net_v3_code
        beq netstream_v3_cobs_block_done
        lda net_v3_in
        cmp net_v3_len
        bcs netstream_v3_frame_bad_near
        tax
        lda net_realtime_packet,x
        ldx net_v3_out
        sta net_realtime_packet,x
        inc net_v3_in
        inc net_v3_out
        dec net_v3_code
        jmp netstream_v3_cobs_copy
netstream_v3_cobs_block_done
        lda net_v3_in
        cmp net_v3_len
        bcs netstream_v3_cobs_done
        ldx net_v3_out
        lda #0
        sta net_realtime_packet,x
        inc net_v3_out
        jmp netstream_v3_cobs_loop
netstream_v3_cobs_done
; net_v3_out = decoded raw length. Validate: length >= 8, version 3,
; declared payload length matches, CRC-16 over bytes 0..len-3.
        lda net_v3_out
        cmp #NET_REALTIME_V3_HEAD_BYTES+2
        bcc netstream_v3_frame_bad
        lda net_realtime_packet+1
        cmp #NET_REALTIME_V3_VERSION
        bne netstream_v3_frame_bad
        lda net_v3_out
        sec
        sbc #NET_REALTIME_V3_HEAD_BYTES+2
        cmp net_realtime_packet
        bne netstream_v3_frame_bad
        sta net_v3_raw_len
        lda #$ff
        sta net_crc_lo
        sta net_crc_hi
        lda net_v3_raw_len
        clc
        adc #NET_REALTIME_V3_HEAD_BYTES
        sta net_v3_len
        ldx #0
netstream_v3_crc_loop
        cpx net_v3_len
        beq netstream_v3_crc_check
        lda net_realtime_packet,x
        stx net_v3_in
        jsr netstream_crc16_update
        ldx net_v3_in
        inx
        jmp netstream_v3_crc_loop
netstream_v3_crc_check
        lda net_realtime_packet,x
        cmp net_crc_lo
        bne netstream_v3_frame_bad
        inx
        lda net_realtime_packet,x
        cmp net_crc_hi
        bne netstream_v3_frame_bad
; Zero-pad from the CRC position to the end of the workspace so per-type
; handlers read zeros beyond the sent payload.
        ldx net_v3_len
        lda #0
netstream_v3_pad_loop
        cpx #NET_REALTIME_PACKET_BYTES
        beq netstream_v3_dispatch
        sta net_realtime_packet,x
        inx
        jmp netstream_v3_pad_loop
netstream_v3_dispatch
        jmp netstream_apply_realtime_packet
netstream_v3_frame_bad
        inc net_rx_drops
        rts

; Phase 43 telemetry: report the link-health counters every NET_STATS_DELAY
; frames so the server can log handler overflows, serial errors, and frame
; drops without an emulator attached.
netstream_send_net_stats_paced
        lda network_realtime_enabled
        beq netstream_net_stats_done
        lda RTCLOK
        sec
        sbc net_stats_clk
        cmp #NET_STATS_DELAY
        bcc netstream_net_stats_done
        lda RTCLOK
        sta net_stats_clk
        lda #NET_RT_NET_STATS
        jsr netstream_tx_prepare
        lda net_rx_drops
        sta net_realtime_tx_packet+6
        lda net_handler_overflow_count
        sta net_realtime_tx_packet+7
        lda net_handler_serial_error_count
        sta net_realtime_tx_packet+8
        lda net_handler_last_status
        sta net_realtime_tx_packet+9
        lda net_fill_id
        sta net_realtime_tx_packet+10
        lda net_fill_commit_pending
        sta net_realtime_tx_packet+11
        lda net_window_origin_x
        sta net_realtime_tx_packet+12
        lda net_window_origin_y
        sta net_realtime_tx_packet+13
        lda net_cache_rev_lo
        sta net_realtime_tx_packet+14
        lda net_cache_rev_hi
        sta net_realtime_tx_packet+15
        jmp netstream_tx_send
netstream_net_stats_done
        rts

; Cycle the walk-speed presets and show the active frames-per-step value
; at the right edge of the HUD status row.
netstream_cycle_walk_speed
        ldx net_walk_speed_index
        inx
        cpx #5
        bcc netstream_walk_speed_store
        ldx #0
netstream_walk_speed_store
        stx net_walk_speed_index
        lda netstream_walk_speed_tab,x
        sta net_move_repeat_cfg
        lda #HUD_LINE1_Y
        sta screen_y
        lda #37
        sta screen_x
        lda net_move_repeat_cfg
        jsr hud_draw_two_digits
        jmp copy_status_to_back

; Acknowledge the applied (or duplicate) cache step: the committed revision
; plus the active window origin. A lost ACK is healed by the server's
; retransmit of the same step, which the duplicate check re-ACKs.
netstream_send_cache_step_ack
        lda #NET_RT_CACHE_STEP_ACK
        jsr netstream_tx_prepare
        lda net_cache_rev_lo
        sta net_realtime_tx_packet+6
        lda net_cache_rev_hi
        sta net_realtime_tx_packet+7
        lda net_window_origin_x
        sta net_realtime_tx_packet+8
        lda net_window_origin_y
        sta net_realtime_tx_packet+9
        jmp netstream_tx_send

; Finalize the prepared TX packet as a v3 wire frame: stamp the per-type
; payload length, append CRC-16, COBS-encode into net_packet_payload, and
; leave the encoded length in net_v3_tx_len (the caller sends the bytes
; plus a zero delimiter).
netstream_v3_tx_finalize
        ldx net_realtime_tx_packet+2
        lda netstream_v3_txlen_tab,x
        sta net_realtime_tx_packet
        clc
        adc #NET_REALTIME_V3_HEAD_BYTES
        sta net_v3_raw_len
        lda #$ff
        sta net_crc_lo
        sta net_crc_hi
        ldx #0
netstream_v3_tx_crc_loop
        cpx net_v3_raw_len
        beq netstream_v3_tx_crc_done
        lda net_realtime_tx_packet,x
        stx net_v3_in
        jsr netstream_crc16_update
        ldx net_v3_in
        inx
        jmp netstream_v3_tx_crc_loop
netstream_v3_tx_crc_done
        lda net_crc_lo
        sta net_realtime_tx_packet,x
        inx
        lda net_crc_hi
        sta net_realtime_tx_packet,x
        inx
        stx net_v3_len
; COBS encode net_realtime_tx_packet[0..net_v3_len) into net_packet_payload.
        lda #0
        sta net_v3_in
        sta net_v3_code_pos
        lda #1
        sta net_v3_out
        sta net_v3_code
netstream_v3_tx_cobs_loop
        lda net_v3_in
        cmp net_v3_len
        bcs netstream_v3_tx_cobs_done
        tax
        lda net_realtime_tx_packet,x
        beq netstream_v3_tx_cobs_zero
        ldx net_v3_out
        sta net_packet_payload,x
        inc net_v3_out
        inc net_v3_code
        inc net_v3_in
        jmp netstream_v3_tx_cobs_loop
netstream_v3_tx_cobs_zero
        lda net_v3_code
        ldx net_v3_code_pos
        sta net_packet_payload,x
        lda net_v3_out
        sta net_v3_code_pos
        inc net_v3_out
        lda #1
        sta net_v3_code
        inc net_v3_in
        jmp netstream_v3_tx_cobs_loop
netstream_v3_tx_cobs_done
        lda net_v3_code
        ldx net_v3_code_pos
        sta net_packet_payload,x
        lda net_v3_out
        sta net_v3_tx_len
        rts

; Phase 70: relocated from the completely full main segment. Joystick-only
; diagonal aim uses the four exact raw stick nibbles. Keyboard Space enters at
; maybe_spawn_bullet only after loading last_cardinal_aim.
aim_and_fire
        lda input_stick_raw
        cmp #15
        bne aim_has_direction
        lda #0
        sta fire_latch
        jmp aim_done
aim_has_direction
        cmp #$0a
        bne aim_not_up_left
        lda #DIR_UP_LEFT
        jmp aim_store_diagonal
aim_not_up_left
        cmp #$06
        bne aim_not_up_right
        lda #DIR_UP_RIGHT
        jmp aim_store_diagonal
aim_not_up_right
        cmp #$09
        bne aim_not_down_left
        lda #DIR_DOWN_LEFT
        jmp aim_store_diagonal
aim_not_down_left
        cmp #$05
        bne aim_cardinal
        lda #DIR_DOWN_RIGHT
aim_store_diagonal
        sta aim_dir
        jmp maybe_spawn_bullet
aim_cardinal
        and #1
        bne aim_not_up
        lda #DIR_UP
        jmp aim_store_cardinal
aim_not_up
        lda input_stick_raw
        and #2
        bne aim_not_down
        lda #DIR_DOWN
        jmp aim_store_cardinal
aim_not_down
        lda input_stick_raw
        and #4
        bne aim_not_left
        lda #DIR_LEFT
        jmp aim_store_cardinal
aim_not_left
        lda input_stick_raw
        and #8
        bne aim_done
        lda #DIR_RIGHT
aim_store_cardinal
        sta aim_dir
        sta last_cardinal_aim
maybe_spawn_bullet
        lda fire_latch
        bne aim_done
        lda #1
        sta fire_latch
        lda #SFX_SHOOT
        jsr sfx_request
        lda input_buttons
        ora #NET_BUTTON_FIRE
        sta input_buttons
; The incrementing counter survives frames where throttling skips PLAYER_STATE.
        inc net_fire_counter
spawn_bullet_visual
        lda #NET_DIR_NONE
        sta input_dir
        lda #$0f
        sta input_stick_raw
        lda player_x
        sta bullet_x
        lda player_y
        sta bullet_y
        lda aim_dir
        sta bullet_dir
        lda RTCLOK
        sec
        sbc #BULLET_DELAY
        sta bullet_clk
        lda #0
        sta bullet_drawn
        sta bullet_steps
        lda #1
        sta bullet_active
        jsr update_network_bullet_fast
aim_done
        rts

; Guard: the v3 engine must stay inside the $6C00-$6FFF cache gap.
        ert *>WORLD_PENDING

        org $4E80
display_list_text
        dta $70,$70,$70
        dta $42
        dta <SCREEN
        dta >SCREEN
        :23 dta $02
        dta $41,<display_list_text,>display_list_text

display_list_game
        dta $70,$70,$F0
        dta $44
game_display_lms_lo
        dta <SCREEN
game_display_lms_hi
        dta >SCREEN
        :19 dta $04
        dta $84
        dta $02
        dta $02
        dta $82
        dta $41,<display_list_game,>display_list_game

        org $4F00
        icl "generated/fujirealm_art.inc"
; The generated include owns the effective font, cave buffer allocation,
; dedicated local/remote player frames, and both 52-entry terrain tables.

; A fresh, non-Overworld-starting AUTH gets an explicit MAP_CHANGE back
; almost immediately (the server synthesizes one whenever the player isn't
; on Overworld); its art fields (current_tileset_id/current_palette_id)
; land here during packet parsing -- well before handle_map_change would
; normally apply them at main_loop depth. Poll briefly for it before the
; game screen ever becomes visible, so a cave/PvP start never flashes the
; Overworld palette. Exits the instant a MAP_CHANGE is seen; the bounded
; timeout covers the common Overworld case (no MAP_CHANGE is ever sent)
; and any lost-packet edge case, falling back to the title screen's
; already-correct Overworld defaults either way. Lives here (rather than
; alongside connection_ok near main_loop, or in the $5400-$5600 gap) because
; neither the main $2000 segment (see "ert *>SCREEN") nor that gap (its
; remote-player state arrays scale with REMOTE_PLAYER_SLOTS, so its free
; space shrinks as that build option grows) have reliable headroom.
NETSTREAM_INITIAL_ART_WAIT_FRAMES = 20
netstream_wait_for_initial_art
        lda #0
        sta net_map_change_pending
        lda #NETSTREAM_INITIAL_ART_WAIT_FRAMES
        sta netstream_timeout
netstream_wait_for_initial_art_loop
        jsr netstream_recv_realtime_packets
        lda net_map_change_pending
        bne netstream_wait_for_initial_art_done
        jsr wait_frame_tick
        dec netstream_timeout
        bne netstream_wait_for_initial_art_loop
netstream_wait_for_initial_art_done
        rts

; Projectiles occupy only the upper two character cells of a logical tile.
; Both local and remote paths share this renderer. Erasure restores only the
; cached terrain's upper row, leaving the lower terrain characters untouched.
draw_bullet_top_at_target
        jsr target_in_view
        beq draw_bullet_top_not_visible
        jsr screen_cell_ptr
        ldx #BULLET
        ldy #0
        lda tile2x2_tl,x
        sta (ptr),y
        iny
        lda tile2x2_tr,x
        sta (ptr),y
        lda #1
        rts
draw_bullet_top_not_visible
        lda #0
        rts

restore_target_top_cell
        jsr target_in_view
        beq restore_target_top_done
        jsr world_cell_ptr_to_wptr
        ldy #0
        lda (wptr),y
        sta work
        jsr screen_cell_ptr
        ldx work
        ldy #0
        lda tile2x2_tl,x
        sta (ptr),y
        iny
        lda tile2x2_tr,x
        sta (ptr),y
restore_target_top_done
        rts

inventory_modal_lines
        dta 4,15
        dta 41,46,54,37,46,52,47,50,57,TITLE_LINE_END
        dta 7,12
        dta 51,52,41,35,43,51,0,56,0,0,0,TITLE_LINE_END
        dta 9,12
        dta 39,47,44,36,0,0,0,0,0,0,0,TITLE_LINE_END
        dta 14,13
        dta 50,37,52,53,50,46,0,35,44,47,51,37,TITLE_LINE_END
        dta TITLE_END

map_modal_lines
        dta 2,18
        dta 45,33,48,TITLE_LINE_END
        dta 14,5
        dta 48,0,48,44,33,57,37,50,0,52,0,52,47,55,46,TITLE_LINE_END
        dta 16,5
        dta 35,0,35,33,54,37,0,39,0,39,50,33,54,37,TITLE_LINE_END
        dta 19,13
        dta 50,37,52,53,50,46,0,35,44,47,51,37,TITLE_LINE_END
        dta TITLE_END

; Static chrome only -- the NPC name/quest name and the offer's flavor
; text are server-sent and drawn separately in show_quest_offer_modal
; from hud_quest_text/hud_message_text, the same buffers the in-game HUD
; quest/message lines use. No quest-specific text lives here anymore.
quest_offer_modal_lines
        dta 3,15
        dta 46,37,55,0,49,53,37,51,52,TITLE_LINE_END
        dta 16,9
        dta 48,50,37,51,51,0,50,37,52,53,50,46,0,52,47,0,33,35,35,37,48,52,TITLE_LINE_END
        dta TITLE_END

help_modal_lines
        dta 2,18
        dta 40,37,44,48,TITLE_LINE_END
        dta 6,6
        dta 55,33,51,36,0,13,0,45,47,54,37,TITLE_LINE_END
        dta 8,6
        dta 51,48,33,35,37,0,13,0,38,41,50,37,TITLE_LINE_END
        dta 10,6
        dta 42,47,57,51,52,41,35,43,0,13,0,45,47,54,37,0,11,0,38,41,50,37,TITLE_LINE_END
        dta 12,6
        dta 50,37,52,53,50,46,0,13,0,41,46,52,37,50,33,35,52,15,33,35,35,37,48,52,TITLE_LINE_END
        dta 14,6
        dta 41,0,13,0,41,46,54,37,46,52,47,50,57,TITLE_LINE_END
        dta 16,6
        dta 45,0,13,0,45,33,48,TITLE_LINE_END
        dta 18,6
        dta 40,0,13,0,40,37,44,48,0,8,52,40,41,51,0,51,35,50,37,37,46,9,TITLE_LINE_END
        dta 20,6
        dta 48,0,13,0,52,47,39,39,44,37,0,48,54,48,TITLE_LINE_END
        dta 22,8
        dta 48,50,37,51,51,0,50,37,52,53,50,46,0,52,47,0,35,47,46,52,41,46,53,37,TITLE_LINE_END
        dta TITLE_END

show_inventory_modal
        lda #0
        sta net_modal_request
        sta input_dir
        sta input_buttons
        jsr wait_frame_tick
        ldx #<display_list_text
        ldy #>display_list_text
        lda #OS_FONT_PAGE
        jsr apply_display_now
        jsr set_text_palette
        jsr init_screen_buffers
        jsr clear_screen
        lda #<inventory_modal_lines
        sta wptr
        lda #>inventory_modal_lines
        sta wptr+1
        jsr draw_text_lines
        jsr draw_inventory_values
        jsr wait_inventory_close
        jsr init_screen_buffers
        jsr wait_frame_tick
        ldx #<display_list_game
        ldy #>display_list_game
        lda current_font_page
        jsr apply_display_now
        jsr apply_palette
        lda #1
        sta net_snapshot_dirty
        rts

show_map_modal
        lda #0
        sta net_modal_request
        sta input_dir
        sta input_buttons
        jsr wait_frame_tick
        ldx #<display_list_text
        ldy #>display_list_text
        lda #OS_FONT_PAGE
        jsr apply_display_now
        jsr set_text_palette
        jsr init_screen_buffers
        jsr clear_screen
        lda #<map_modal_lines
        sta wptr
        lda #>map_modal_lines
        sta wptr+1
        jsr draw_text_lines
        jsr draw_map_values
        jsr wait_inventory_close
        jsr init_screen_buffers
        jsr wait_frame_tick
        ldx #<display_list_game
        ldy #>display_list_game
        lda current_font_page
        jsr apply_display_now
        jsr apply_palette
        lda #1
        sta net_snapshot_dirty
        rts

show_help_modal
        lda #0
        sta net_modal_request
        sta input_dir
        sta input_buttons
        jsr wait_frame_tick
        ldx #<display_list_text
        ldy #>display_list_text
        lda #OS_FONT_PAGE
        jsr apply_display_now
        jsr set_text_palette
        jsr init_screen_buffers
        jsr clear_screen
        lda #<help_modal_lines
        sta wptr
        lda #>help_modal_lines
        sta wptr+1
        jsr draw_text_lines
        jsr wait_inventory_close
        jsr init_screen_buffers
        jsr wait_frame_tick
        ldx #<display_list_game
        ldy #>display_list_game
        lda current_font_page
        jsr apply_display_now
        jsr apply_palette
        lda #1
        sta net_snapshot_dirty
        rts

show_quest_offer_modal
        lda #0
        sta net_modal_request
        sta input_dir
        sta input_buttons
        jsr wait_frame_tick
        ldx #<display_list_text
        ldy #>display_list_text
        lda #OS_FONT_PAGE
        jsr apply_display_now
        jsr set_text_palette
        jsr init_screen_buffers
        jsr clear_screen
        lda #<quest_offer_modal_lines
        sta wptr
        lda #>quest_offer_modal_lines
        sta wptr+1
        jsr draw_text_lines
        lda #7
        sta screen_y
        lda #0
        sta screen_x
        lda #<hud_quest_text
        sta wptr
        lda #>hud_quest_text
        sta wptr+1
        jsr status_draw_text_ptr
        lda #11
        sta screen_y
        lda #0
        sta screen_x
        lda #<hud_message_text
        sta wptr
        lda #>hud_message_text
        sta wptr+1
        jsr status_draw_text_ptr
        jsr wait_quest_accept
        jsr init_screen_buffers
        jsr wait_frame_tick
        ldx #<display_list_game
        ldy #>display_list_game
        lda current_font_page
        jsr apply_display_now
        jsr apply_palette
        lda #1
        sta net_snapshot_dirty
        rts

draw_map_values
        lda map_summary_valid
        beq draw_map_no_data
        lda #0
        sta map_cell_index
        sta map_row_tmp
draw_map_row_loop
        lda map_row_tmp
        cmp #MAP_SUMMARY_H
        beq draw_map_done
        clc
        adc #5
        sta screen_y
        lda #16
        sta screen_x
        lda #0
        sta map_col_tmp
draw_map_col_loop
        lda map_col_tmp
        cmp #MAP_SUMMARY_W
        beq draw_map_next_row
        ldx map_cell_index
        lda map_summary_cells,x
        jsr map_cell_char
        sta map_char_tmp
        jsr screen_cell_ptr
        ldy #0
        lda map_char_tmp
        sta (ptr),y
        inc screen_x
        inc map_cell_index
        inc map_col_tmp
        jmp draw_map_col_loop
draw_map_next_row
        inc map_row_tmp
        jmp draw_map_row_loop
draw_map_done
        rts
draw_map_no_data
        lda #8
        sta screen_y
        lda #15
        sta screen_x
        lda #46
        sta map_char_tmp
        jsr screen_cell_ptr
        ldy #0
        lda #46
        sta (ptr),y
        iny
        lda #47
        sta (ptr),y
        iny
        lda #0
        sta (ptr),y
        iny
        lda #45
        sta (ptr),y
        iny
        lda #33
        sta (ptr),y
        iny
        lda #48
        sta (ptr),y
        iny
        lda #0
        sta (ptr),y
        iny
        lda #36
        sta (ptr),y
        iny
        lda #33
        sta (ptr),y
        iny
        lda #52
        sta (ptr),y
        iny
        lda #33
        sta (ptr),y
        rts

map_cell_char
        pha
        and #MAP_CELL_CURRENT
        beq map_cell_not_current
        pla
        lda #48
        rts
map_cell_not_current
        pla
        pha
        and #MAP_CELL_MARKER_MASK
        cmp #MAP_CELL_MARKER_CAVE
        beq map_cell_cave
        cmp #MAP_CELL_MARKER_GRAVE
        beq map_cell_grave
        cmp #MAP_CELL_MARKER_TOWN
        beq map_cell_town
        pla
        and #MAP_CELL_VISITED
        beq map_cell_unknown
        lda #14
        rts
map_cell_unknown
        lda #0
        rts
map_cell_cave
        pla
        lda #35
        rts
map_cell_grave
        pla
        lda #39
        rts
map_cell_town
        pla
        lda #52
        rts

draw_inventory_values
        lda #7
        sta screen_y
        lda #21
        sta screen_x
        lda inventory_sticks_count
        jsr draw_modal_two_digits
        lda #9
        sta screen_y
        lda #21
        sta screen_x
        lda inventory_gold_hi
        beq draw_inventory_gold_low
        lda #99
        jmp draw_modal_two_digits
draw_inventory_gold_low
        lda inventory_gold_lo
        cmp #100
        bcc draw_modal_two_digits
        lda #99
draw_modal_two_digits
        sta inventory_value_tmp
        lda #0
        sta inventory_tens_tmp
draw_modal_tens_loop
        lda inventory_value_tmp
        cmp #10
        bcc draw_modal_digits
        sec
        sbc #10
        sta inventory_value_tmp
        inc inventory_tens_tmp
        jmp draw_modal_tens_loop
draw_modal_digits
        jsr screen_cell_ptr
        ldy #0
        lda inventory_tens_tmp
        clc
        adc #DIGIT0
        sta (ptr),y
        iny
        lda inventory_value_tmp
        clc
        adc #DIGIT0
        sta (ptr),y
        rts

wait_inventory_close
        lda TRIG0
        beq wait_inventory_close
        lda SKSTAT
        and #KEY_DOWN_MASK
        beq wait_inventory_close
wait_inventory_close_loop
        jsr netstream_service_modal_io
        lda TRIG0
        beq wait_inventory_closed
        lda SKSTAT
        and #KEY_DOWN_MASK
        bne wait_inventory_close_loop
        lda KEY
        and #KEY_CODE_MASK
        cmp #KEY_RETURN
        bne wait_inventory_close_loop
wait_inventory_closed
        lda #KEY_NONE
        sta net_key_repeat_latch
        rts

wait_quest_accept
        jsr wait_inventory_close
        inc net_pickup_counter
        lda #KEY_RETURN
        sta net_key_repeat_latch
        rts

netstream_apply_inventory
        lda net_realtime_packet+NET_RT_INVENTORY_GOLD_LO_OFFSET
        sta inventory_gold_lo
        lda net_realtime_packet+NET_RT_INVENTORY_GOLD_HI_OFFSET
        sta inventory_gold_hi
        lda #0
        sta inventory_sticks_count
        lda net_realtime_packet+NET_RT_INVENTORY_COUNT_OFFSET
        sta inventory_slot_count
        ldx #0
        ldy #NET_RT_INVENTORY_SLOT_OFFSET
netstream_inventory_loop
        cpx inventory_slot_count
        beq netstream_inventory_done
        cpx #8
        beq netstream_inventory_done
        lda net_realtime_packet,y
        cmp #ITEM_STICKS
        bne netstream_inventory_next
        iny
        lda net_realtime_packet,y
        sta inventory_sticks_count
        jmp netstream_inventory_advance_done
netstream_inventory_next
        iny
netstream_inventory_advance_done
        iny
        inx
        jmp netstream_inventory_loop
netstream_inventory_done
        rts

netstream_apply_map_summary
        lda net_realtime_packet+NET_RT_MAP_SUMMARY_MAP_ID_OFFSET
        sta map_summary_map_id
        lda net_realtime_packet+NET_RT_MAP_SUMMARY_WIDTH_OFFSET
        sta map_summary_width
        lda net_realtime_packet+NET_RT_MAP_SUMMARY_HEIGHT_OFFSET
        sta map_summary_height
        ldx #0
netstream_apply_map_summary_loop
        cpx #MAP_SUMMARY_CELL_COUNT
        beq netstream_apply_map_summary_done
        lda net_realtime_packet+NET_RT_MAP_SUMMARY_CELLS_OFFSET,x
        sta map_summary_cells,x
        inx
        jmp netstream_apply_map_summary_loop
netstream_apply_map_summary_done
        lda #1
        sta map_summary_valid
        rts

netstream_tx_finalize
        jmp netstream_v3_tx_finalize

apply_palette_and_clear
        jsr apply_palette
        jmp clear_screen

netstream_clear_window_row_masks
        lda #0
        sta net_window_row_mask0
        sta net_window_row_mask1
        sta net_window_row_mask2
        rts

netstream_window_row_complete_check
        jsr netstream_mark_window_row_received
; Reached once per accepted row: row progress rearms the dead-fill retry
; budget and cancels any pending clean-fill request.
        lda #0
        sta net_fill_retry_count
        sta net_request_new_fill
; A queued map change means handle_map_change has not run yet (it only runs
; at main_loop depth; a modal can hold it off for seconds). Completing now
; would activate/commit the new map's cache with the old palette, an
; unsnapped player, and no MAP_READY. Defer: handle_map_change re-runs this
; check after it arms net_map_fill_pending, so a fill that finished during
; the modal completes there in one clean cut. Until then the server's
; commit timeout simply restreams the fill.
        lda net_map_change_pending
        beq netstream_window_row_check_masks
        rts
netstream_window_row_check_masks
        lda net_window_row_mask0
        cmp #$ff
        bne netstream_window_row_not_complete
        lda net_window_row_mask1
        cmp #$ff
        bne netstream_window_row_not_complete
        lda net_window_row_mask2
        cmp #$ff
        bne netstream_window_row_not_complete
; All rows arrived: swap the pending cache/origin into active ownership. If
; this fill delivered a new map, apply the deferred tileset/palette now, then
; snap the view and full-redraw once.
        lda #0
        sta net_resync_pending
        sta net_row_fill_active
        lda #1
        sta net_fill_commit_pending
        lda net_fill_id
        sta net_last_committed_fill_id
        jsr net_activate_pending_window
        jsr netstream_send_window_commit
        lda net_map_fill_pending
        beq netstream_window_row_no_map_fill
        lda #0
        sta net_map_fill_pending
        jsr apply_tileset
        jsr apply_palette_and_clear
        jsr netstream_snap_view_to_window
        jsr netstream_send_map_ready
        rts
netstream_window_row_no_map_fill
; Keep the viewport still when the player is already on-screen: the fill
; replaced the terrain cache UNDER the view, so a full redraw at the same
; position shows the recovered world without a jarring viewport jump. The
; normal one-tile-per-step scroll then follows the player as usual. Snap
; only when the player is off-view (teleport-class repositions), where a
; jump is expected.
        lda player_x
        sta target_x
        lda player_y
        sta target_y
        jsr target_in_view
        beq netstream_window_row_snap_view
        lda #1
        sta net_snapshot_dirty
        rts
netstream_window_row_snap_view
        jmp netstream_snap_view_to_window
netstream_window_row_not_complete
        rts

netstream_mark_window_row_received
        lda net_realtime_packet+NET_RT_WINDOW_ROW_INDEX_OFFSET
        cmp #NET_WINDOW_H
        bcc netstream_mark_window_row_valid
        rts
netstream_mark_window_row_valid
        cmp #8
        bcc netstream_mark_window_row_0
        cmp #16
        bcc netstream_mark_window_row_1
        sec
        sbc #16
        tax
        lda row_bit_mask,x
        ora net_window_row_mask2
        sta net_window_row_mask2
        rts
netstream_mark_window_row_1
        sec
        sbc #8
        tax
        lda row_bit_mask,x
        ora net_window_row_mask1
        sta net_window_row_mask1
        rts
netstream_mark_window_row_0
        tax
        lda row_bit_mask,x
        ora net_window_row_mask0
        sta net_window_row_mask0
        rts

row_bit_mask
        dta 1,2,4,8,16,32,64,128

; Phase 14b item-drop overlay: code and state live here (in the spacious
; $8000 block, alongside the tile tables and inventory modal) rather than
; inline near the enemy/remote-player overlay code that inspired them --
; the main $2000 segment has essentially no headroom left below SCREEN
; (see the "ert *>SCREEN" guard). Callers reference these by name via
; ordinary jsr/jmp exactly like netstream_apply_inventory/show_inventory_modal
; already do from way up in the $2000 segment.

install_hud_dli
        lda #<hud_font_dli
        sta VDSLST
        lda #>hud_font_dli
        sta VDSLST+1
        lda #$c0
        sta NMIEN
        rts

hud_font_dli
        pha
        lda VCOUNT
        cmp #80
        bcc hud_dli_restore_game
        cmp #106
        bcs hud_dli_restore_game
        sta WSYNC
        lda #OS_FONT_PAGE
        sta CHBASE
        pla
        rti
hud_dli_restore_game
        sta WSYNC
        lda current_font_page
        sta CHBASE
        pla
        rti

; X/Y = display list lo/hi, A = font page. Call only immediately after
; wait_frame_tick so live ANTIC register writes land in early VBlank. The
; OS shadows are written too, making any later Stage-2 VBI copy idempotent.
apply_display_now
        stx SDLSTL
        sty SDLSTL+1
        stx DLISTL
        sty DLISTH
        sta CHBAS
        sta CHBASE
        rts

; Per-iteration OS housekeeping for the realtime loop. CRITIC=1 keeps the
; VBI down to stage-1 so it can't mask IRQs across serial byte times (the
; real-hardware terrain-corruption cause -- see the CRITIC equate note).
; With stage-2 gone, KEYDEL is never decremented; left alone it would
; latch nonzero after the first keypress and make the OS keyboard IRQ
; swallow every repeat of the same key, so it is zeroed here each frame
; (the game's own key latching handles debounce). The CHBAS refresh moved
; here from main_loop unchanged.
main_loop_os_sync
        lda current_font_page
        sta CHBAS
        lda #0
        sta KEYDEL
        lda #1
        sta CRITIC
        rts

; Copy the COLOR0-4 shadows to the color hardware directly -- the stage-2
; VBI that normally does this is suppressed by CRITIC=1 during realtime
; play. Shadows are still written first by the palette setters (which
; tail-jump here) so any stage-2 pass that does run stays consistent.
sync_colors_hw
        lda COLOR0
        sta COLPF0
        lda COLOR1
        sta COLPF1
        lda COLOR2
        sta COLPF2
        lda COLOR3
        sta COLPF3
        lda COLOR4
        sta COLBK
        rts

perf_world_packets
        dta 0
perf_terrain_packets
        dta 0
perf_full_redraws
        dta 0
perf_partial_redraws
        dta 0
perf_scroll_dirty_sets
        dta 0
perf_screen_dirty_sets
        dta 0
perf_snapshot_dirty_sets
        dta 0
perf_frames_waited
        dta 0
perf_dirty_cell_frames
        dta 0
perf_dirty_enemy_restores
        dta 0
perf_dirty_player_restores
        dta 0
perf_edge_clk_start
        dta 0
perf_edge_frames_max
        dta 0

net_modal_request
        dta 0
inventory_gold_lo
        dta 0
inventory_gold_hi
        dta 0
inventory_sticks_count
        dta 0
inventory_slot_count
        dta 0
inventory_value_tmp
        dta 0
inventory_tens_tmp
        dta 0
net_key_repeat_latch
        dta KEY_NONE
; keyboard_dir_* moved to the $5400 data gap (near remote_recolor_bit):
; this block sits a handful of bytes under APPKEY_DATA_BUFFER.
net_rx_drops
        dta 0
net_realtime_type
        dta 0
net_send_checksum
        dta 0
net_send_byte
        dta 0
net_send_retry
        dta 0
hud_clock_lo
        dta 0
hud_clock_hi
        dta 0
hud_quest_state
        dta 0
hud_quest_done_hidden
        dta 0
hud_quest_done_clk_lo
        dta 0
hud_quest_done_clk_hi
        dta 0
hud_message_id
        dta 0
hud_message_clk_lo
        dta 0
hud_message_clk_hi
        dta 0
; hud_message_id doubles as a message classification (for sfx_for_message)
; and, at value 0, the client's MSG_NONE. Generic attack/kill text (bats,
; snakes, slimes, Gorvak, etc.) is legitimately sent with id MSG_NONE, so
; "id == 0" cannot also mean "no message queued" -- this flag tracks that
; separately, set whenever a message packet lands and cleared on timeout.
hud_message_active
        dta 0
; Filled verbatim (as ATASCII->internal codes) from server MESSAGE/
; QUEST_UPDATE packets -- the client has no per-message/per-quest text
; tables of its own, so new quests/messages need no client changes.
hud_message_text
        :NET_RT_TEXT_MAX_LEN+1 dta 0
hud_quest_text
        :NET_RT_TEXT_MAX_LEN+1 dta 0

; Called once per main-loop iteration regardless of other dirty flags, so a
; message/quest-done line clears itself out even if the player stands still
; and nothing else would otherwise trigger a HUD redraw.
hud_message_timeout_check
        lda hud_message_active
        beq hud_message_timeout_done
        lda hud_clock_lo
        sec
        sbc hud_message_clk_lo
        sta work
        lda hud_clock_hi
        sbc hud_message_clk_hi
        cmp #>HUD_MESSAGE_TIMEOUT_FRAMES
        bne hud_message_timeout_hi_decides
        lda work
        cmp #<HUD_MESSAGE_TIMEOUT_FRAMES
hud_message_timeout_hi_decides
        bcc hud_message_timeout_done
        lda #0
        sta hud_message_id
        sta hud_message_active
        lda #1
        sta status_dirty
        sta message_dirty
hud_message_timeout_done
        rts

hud_quest_done_timeout_check
        lda hud_quest_state
        cmp #QUEST_STATE_COMPLETE
        bne hud_quest_done_timeout_done
        lda hud_quest_done_hidden
        bne hud_quest_done_timeout_done
        lda hud_clock_lo
        sec
        sbc hud_quest_done_clk_lo
        sta work
        lda hud_clock_hi
        sbc hud_quest_done_clk_hi
        cmp #>HUD_QUEST_DONE_TIMEOUT_FRAMES
        bne hud_quest_done_timeout_hi_decides
        lda work
        cmp #<HUD_QUEST_DONE_TIMEOUT_FRAMES
hud_quest_done_timeout_hi_decides
        bcc hud_quest_done_timeout_done
        lda #1
        sta hud_quest_done_hidden
        sta status_dirty
        sta quest_dirty
hud_quest_done_timeout_done
        rts

; True full HUD redraw: clears and repaints all 3 rows including the static
; labels. Only needed where the screen buffer content can't be trusted --
; level init, and returning from a modal/map change that overwrote it.
draw_status_full
        lda #HUD_LINE1_Y
        jsr clear_hud_row
        lda #HUD_LINE2_Y
        jsr clear_hud_row
        lda #HUD_LINE3_Y
        jsr clear_hud_row

        lda #HUD_LINE1_Y
        sta screen_y
        lda #0
        sta screen_x
        lda #<hud_line_hp
        sta wptr
        lda #>hud_line_hp
        sta wptr+1
        jsr status_draw_text_ptr
        jsr compute_heart_full_count
        ldx #0
draw_status_heart_loop
        cpx #HEART_COUNT
        beq draw_status_after_hearts
        txa
        cmp heart_full_count
        bcs draw_status_empty_heart
        lda #OS_HEART
        jmp draw_status_store_heart
draw_status_empty_heart
        lda #0
draw_status_store_heart
        jsr status_store_tile
        inc screen_x
        inx
        jmp draw_status_heart_loop
draw_status_after_hearts
        lda #HUD_LEVEL_LABEL_X
        sta screen_x
        lda #<hud_line_level
        sta wptr
        lda #>hud_line_level
        sta wptr+1
        jsr status_draw_text_ptr
        lda level_num
        jsr hud_draw_two_digits
        lda #HUD_GOLD_X
        sta screen_x
        jsr draw_hud_gold
        lda #HUD_PVP_X
        sta screen_x
        lda hud_pvp_enabled
        beq draw_status_pvp_clear
        lda #<hud_line_pvp
        sta wptr
        lda #>hud_line_pvp
        sta wptr+1
        jsr status_draw_text_ptr
        jsr draw_hud_pvp_kills
        jmp draw_status_pvp_done
draw_status_pvp_clear
        lda #<hud_line_pvp_blank
        sta wptr
        lda #>hud_line_pvp_blank
        sta wptr+1
draw_status_pvp_draw
        jsr status_draw_text_ptr
draw_status_pvp_done
        jsr draw_quest_status_line
        jsr draw_message_status_line
        jsr copy_status_to_back
        rts

hud_line_hp
        dta 40,48,0,TITLE_LINE_END
hud_line_level
        dta 0,44,OS_COLON,TITLE_LINE_END
hud_line_pvp
        dta OS_P,OS_V,OS_P,TITLE_LINE_END
hud_line_pvp_blank
        dta 0,0,0,0,0,0,0,0,TITLE_LINE_END

; Lives here (rather than alongside redraw_hud_level near the other
; per-field HUD redraws) because the main $2000 segment has no headroom
; left below SCREEN -- see the "ert *>SCREEN" guard.
redraw_hud_pvp
        lda #HUD_LINE1_Y
        sta screen_y
        lda #HUD_PVP_X
        sta screen_x
        lda hud_pvp_enabled
        beq redraw_hud_pvp_clear
        lda #<hud_line_pvp
        sta wptr
        lda #>hud_line_pvp
        sta wptr+1
        jsr status_draw_text_ptr
        jmp draw_hud_pvp_kills
redraw_hud_pvp_clear
        lda #<hud_line_pvp_blank
        sta wptr
        lda #>hud_line_pvp_blank
        sta wptr+1
redraw_hud_pvp_draw
        jsr status_draw_text_ptr
        rts

; Same mechanics as draw_player_sprite_2x2. Remote frame definitions reuse
; the local player's glyphs with bit 7 already set, freeing 108-125 for story
; NPCs. remote_recolor_bit remains ORed for protocol compatibility.
draw_remote_player_sprite_2x2
        sta work
        jsr screen_cell_ptr
        ldx work
        ldy #0
        lda player_sprite_tl,x
        ora remote_recolor_bit
        sta (ptr),y
        iny
        lda player_sprite_tr,x
        ora remote_recolor_bit
        sta (ptr),y
        clc
        lda ptr
        adc #SCREEN_W
        sta ptr
        bcc draw_remote_sprite_bottom_ok
        inc ptr+1
draw_remote_sprite_bottom_ok
        ldx work
        ldy #0
        lda player_sprite_bl,x
        ora remote_recolor_bit
        sta (ptr),y
        iny
        lda player_sprite_br,x
        ora remote_recolor_bit
        sta (ptr),y
        rts

; Both lines below just display whatever text the server last sent -- the
; client has no per-quest or per-message text of its own to keep in sync.
draw_quest_status_line
        lda hud_quest_state
        cmp #QUEST_STATE_COMPLETE
        bne draw_quest_status_show
        lda hud_quest_done_hidden
        beq draw_quest_status_show
        rts
draw_quest_status_show
        lda #HUD_LINE2_Y
        sta screen_y
        lda #0
        sta screen_x
        lda #<hud_quest_text
        sta wptr
        lda #>hud_quest_text
        sta wptr+1
        jmp status_draw_text_ptr

draw_message_status_line
        lda hud_message_active
        beq draw_message_status_done
        lda #HUD_LINE3_Y
        sta screen_y
        lda #0
        sta screen_x
        lda #<hud_message_text
        sta wptr
        lda #>hud_message_text
        sta wptr+1
        jmp status_draw_text_ptr
draw_message_status_done
        rts

status_draw_text_ptr
        ldy #0
status_draw_text_loop
        lda (wptr),y
        cmp #TITLE_LINE_END
        beq status_draw_text_done
        sta work
        tya
        pha
        lda work
        jsr status_store_tile
        pla
        tay
        inc screen_x
        iny
        jmp status_draw_text_loop
status_draw_text_done
        rts

hud_draw_digit
        clc
        adc #DIGIT0
        jmp status_store_tile

hud_draw_two_digits
        sta work
        lda #0
        sta inventory_tens_tmp
hud_tens_loop
        lda work
        cmp #10
        bcc hud_tens_done
        sec
        sbc #10
        sta work
        inc inventory_tens_tmp
        jmp hud_tens_loop
hud_tens_done
        lda inventory_tens_tmp
        jsr hud_draw_digit
        inc screen_x
        lda work
        jmp hud_draw_digit

; Copies a server-supplied text field out of net_realtime_packet into a HUD
; RAM buffer, converting ATASCII (32-95, guaranteed by the server's sender)
; to internal screen codes with a single SBC #32 per byte -- the same
; TITLE_LINE_END-terminated shape the hand-authored tables used to have.
; X = offset of the length byte within net_realtime_packet; the text bytes
; are the ones immediately following it. wptr = destination buffer.
net_copy_realtime_text
        lda net_realtime_packet,x
        cmp #NET_RT_TEXT_MAX_LEN+1
        bcc net_copy_realtime_text_len_ok
        lda #NET_RT_TEXT_MAX_LEN
net_copy_realtime_text_len_ok
        sta work
        inx
        ldy #0
net_copy_realtime_text_loop
        cpy work
        beq net_copy_realtime_text_done
        lda net_realtime_packet,x
        sec
        sbc #32
        sta (wptr),y
        inx
        iny
        jmp net_copy_realtime_text_loop
net_copy_realtime_text_done
        lda #TITLE_LINE_END
        sta (wptr),y
        rts

netstream_apply_quest_update
        lda net_realtime_packet+NET_RT_QUEST_STATE_OFFSET
        sta hud_quest_state
        lda #<hud_quest_text
        sta wptr
        lda #>hud_quest_text
        sta wptr+1
        ldx #NET_RT_QUEST_TEXT_LEN_OFFSET
        jsr net_copy_realtime_text
        lda #0
        sta hud_quest_done_hidden
        lda hud_quest_state
        cmp #QUEST_STATE_COMPLETE
        bne netstream_quest_update_not_done
        lda hud_clock_lo
        sta hud_quest_done_clk_lo
        lda hud_clock_hi
        sta hud_quest_done_clk_hi
netstream_quest_update_not_done
        lda #1
        sta status_dirty
        sta quest_dirty
        rts

netstream_apply_message
        lda net_realtime_packet+NET_RT_MESSAGE_ID_OFFSET
        sta hud_message_id
        lda #1
        sta hud_message_active
        lda hud_message_id
        cmp #MSG_QUEST_OFFER
        bne netstream_message_not_offer
        lda #3
        sta net_modal_request
netstream_message_not_offer
        lda #<hud_message_text
        sta wptr
        lda #>hud_message_text
        sta wptr+1
        ldx #NET_RT_MESSAGE_TEXT_LEN_OFFSET
        jsr net_copy_realtime_text
        lda hud_clock_lo
        sta hud_message_clk_lo
        lda hud_clock_hi
        sta hud_message_clk_hi
        lda #1
        sta status_dirty
        sta message_dirty
        lda hud_message_id
        jsr sfx_for_message
        rts

netstream_apply_hud_update
        lda net_realtime_packet+NET_RT_HUD_MAXHP_OFFSET
        cmp player_max_health
        beq netstream_hud_update_check_level
        sta player_max_health
        lda #1
        sta status_dirty
        sta hp_dirty
netstream_hud_update_check_level
        lda net_realtime_packet+NET_RT_HUD_LEVEL_OFFSET
        cmp level_num
        beq netstream_hud_update_check_gold
        sta level_num
        lda #1
        sta status_dirty
        sta level_dirty
netstream_hud_update_check_gold
        lda net_realtime_packet+NET_RT_HUD_GOLD_LO_OFFSET
        cmp inventory_gold_lo
        bne netstream_hud_update_store_gold
        lda net_realtime_packet+NET_RT_HUD_GOLD_HI_OFFSET
        cmp inventory_gold_hi
        beq netstream_hud_update_check_pvp
netstream_hud_update_store_gold
        lda net_realtime_packet+NET_RT_HUD_GOLD_LO_OFFSET
        sta inventory_gold_lo
        lda net_realtime_packet+NET_RT_HUD_GOLD_HI_OFFSET
        sta inventory_gold_hi
        lda #1
        sta status_dirty
        sta level_dirty
netstream_hud_update_check_pvp
        lda net_realtime_packet+NET_RT_HUD_FLAGS_OFFSET
        and #HUD_FLAG_PVP_ENABLED
        cmp hud_pvp_enabled
        beq netstream_hud_update_check_kills
        sta hud_pvp_enabled
        lda #1
        sta status_dirty
        sta level_dirty
netstream_hud_update_check_kills
        lda net_realtime_packet+NET_RT_HUD_KILLS_LO_OFFSET
        cmp hud_pvp_kills_lo
        bne netstream_hud_update_store_kills
        lda net_realtime_packet+NET_RT_HUD_KILLS_HI_OFFSET
        cmp hud_pvp_kills_hi
        beq netstream_hud_update_done
netstream_hud_update_store_kills
        lda net_realtime_packet+NET_RT_HUD_KILLS_LO_OFFSET
        sta hud_pvp_kills_lo
        lda net_realtime_packet+NET_RT_HUD_KILLS_HI_OFFSET
        sta hud_pvp_kills_hi
        lda #1
        sta status_dirty
        sta level_dirty
netstream_hud_update_done
        rts

; NET_RT_ITEM_DROPS: up to NET_MAX_ITEM_DROPS world item drops in the
; player's window. Unlike remote players' 4th field (a literal alive
; state), the wire's 4th field is quantity, which the overlay does not
; render; item_alive is tracked locally instead of copied from the wire.
netstream_apply_item_drops
        lda net_realtime_packet+NET_RT_ITEM_COUNT_OFFSET
        cmp #NET_MAX_ITEM_DROPS+1
        bcc netstream_item_count_ok
        lda #NET_MAX_ITEM_DROPS
netstream_item_count_ok
        sta remote_count_tmp
        lda #0
        sta net_world_changed
        ldx #0
        ldy #NET_RT_ITEM_PAYLOAD_OFFSET
netstream_item_copy_loop
        cpx remote_count_tmp
        beq netstream_item_clear_rest
        lda net_realtime_packet,y
        cmp item_x,x
        beq netstream_item_x_same
        inc net_world_changed
netstream_item_x_same
        sta item_x,x
        iny
        lda net_realtime_packet,y
        cmp item_y,x
        beq netstream_item_y_same
        inc net_world_changed
netstream_item_y_same
        sta item_y,x
        iny
        lda net_realtime_packet,y
        cmp item_kind,x
        beq netstream_item_kind_same
        inc net_world_changed
netstream_item_kind_same
        sta item_kind,x
        iny
        iny
        lda item_alive,x
        bne netstream_item_already_alive
        inc net_world_changed
        lda #1
        sta item_alive,x
netstream_item_already_alive
        inx
        jmp netstream_item_copy_loop
netstream_item_clear_rest
        cpx #NET_MAX_ITEM_DROPS
        beq netstream_item_copy_done
        lda item_alive,x
        beq netstream_item_clear_next
        inc net_world_changed
        lda #0
        sta item_alive,x
netstream_item_clear_next
        inx
        jmp netstream_item_clear_rest
netstream_item_copy_done
        lda net_world_changed
        beq netstream_item_done
        lda #1
        sta net_screen_dirty
netstream_item_done
        rts

; Item drops use the generic terrain-style 2x2 tile table (like enemies),
; not the player sprite tables -- they are static ground icons.
draw_items
        lda #0
        sta enemy_index
draw_items_loop
        ldx enemy_index
        cpx #NET_MAX_ITEM_DROPS
        beq draw_items_done
        lda item_alive,x
        beq draw_items_next
        lda item_x,x
        sta target_x
        lda item_y,x
        sta target_y
        jsr target_in_view
        beq draw_items_next
        ldx enemy_index
        lda item_kind,x
        cmp #ITEM_GOLD
        beq draw_item_gold
        cmp #ITEM_WARDEN_KEY
        beq draw_item_charm
        lda #ITEM_TILE_STICKS
        jmp draw_item_tile
draw_item_gold
        lda #ITEM_TILE_GOLD
        jmp draw_item_tile
draw_item_charm
        lda #ITEM_TILE_WARDEN_KEY
draw_item_tile
        jsr draw_tile_id_2x2
draw_items_next
        inc enemy_index
        jmp draw_items_loop
draw_items_done
        rts

; Both call sites that need to restore old dynamic-overlay cells always
; want all four kinds together; one shared entry point costs one jsr at
; each site instead of four, saving room in the tight $2000 segment.
restore_old_dynamic_overlays
        jsr restore_old_player_cell
        jsr restore_old_enemy_cells
        jsr restore_old_remote_cells
        jmp restore_old_item_cells

restore_old_item_cells
        lda #0
        sta enemy_index
restore_old_item_loop
        ldx enemy_index
        cpx #NET_MAX_ITEM_DROPS
        beq restore_old_item_done
        lda old_item_alive,x
        beq restore_old_item_next
        lda old_item_x,x
        sta target_x
        lda old_item_y,x
        sta target_y
        jsr draw_target_world_cell
restore_old_item_next
        inc enemy_index
        jmp restore_old_item_loop
restore_old_item_done
        rts

; Tail-called from net_capture_enemy_cells (ends with rts, returning to
; that routine's own caller).
net_capture_item_cells
        ldx #0
net_capture_item_loop
        cpx #NET_MAX_ITEM_DROPS
        beq net_capture_item_done
        lda item_x,x
        sta old_item_x,x
        lda item_y,x
        sta old_item_y,x
        lda item_alive,x
        sta old_item_alive,x
        inx
        jmp net_capture_item_loop
net_capture_item_done
        rts

; Called from netstream_restore_clear_dynamic; clears both slot arrays
; (A is 0 on entry and holds 0 throughout, but the caller reloads it after
; return rather than relying on that).
net_clear_item_state
        lda #0
        ldx #0
net_clear_item_state_loop
        cpx #NET_MAX_ITEM_DROPS
        beq net_clear_item_state_done
        sta item_alive,x
        sta old_item_alive,x
        inx
        jmp net_clear_item_state_loop
net_clear_item_state_done
        rts

; Item-drop overlay slots (Phase 14b). Filled from NET_RT_ITEM_DROPS;
; persists between packets (server sends change-driven updates only).
; item_kind holds the server item_id (1=gold, 2=sticks) used to pick
; ITEM_TILE_GOLD/ITEM_TILE_STICKS at draw time.
item_x
        dta 0,0,0,0
item_y
        dta 0,0,0,0
item_kind
        dta 0,0,0,0
item_alive
        dta 0,0,0,0
old_item_x
        dta 0,0,0,0
old_item_y
        dta 0,0,0,0
old_item_alive
        dta 0,0,0,0

; Redraw remote tracers after terrain/dynamic repaint paths. This block has
; enough guarded headroom for the routine without pressuring WORLD at $6000.
draw_remote_bullets
        lda #0
        sta rbullet_index
draw_remote_bullets_loop
        ldx rbullet_index
        cpx #RBULLET_SLOTS
        beq draw_remote_bullets_done
        lda rbullet_active,x
        beq draw_remote_bullets_next
        lda rbullet_x,x
        sta target_x
        lda rbullet_y,x
        sta target_y
        jsr draw_bullet_top_at_target
        ldx rbullet_index
        sta rbullet_drawn,x
        jmp draw_remote_bullets_next
draw_remote_bullets_next
        inc rbullet_index
        jmp draw_remote_bullets_loop
draw_remote_bullets_done
        rts
; Guard: the high client code/data block must not grow into the fixed
; AppKey/login/NetStream scratch buffers at $8C00-$8FFF.
        ert *>APPKEY_DATA_BUFFER

; ============================================================
; Phase 57: paged dialogue modal, housed in the reclaimed cave-font region
; ($7C00-$8000). Self-contained code + data + buffers; must stay below the
; player sprites at $8000.
; ============================================================
        org DIALOGUE_CODE
dialogue_speaker
        dta 0
dialogue_page_index
        dta 0
dialogue_page_count
        dta 0
dialogue_flags
        dta 0
dialogue_page_dirty
        dta 0
dialogue_active
        dta 0
dialogue_shown_index
        dta DLG_SHOWN_NONE
dialogue_waiting
        dta 0
dialogue_close_flag
        dta 0
dialogue_prev_action
        dta 0
net_dialogue_decline
        dta 0
dialogue_text_len
        dta 0
dialogue_next_chunk
        dta 0
dlg_row
        dta 0
dlg_col
        dta 0
dlg_i
        dta 0
dlg_wordlen
        dta 0
dialogue_text
        :DIALOGUE_PAGE_MAX+1 dta 0

; DIALOGUE_PAGE handler: a display page arrives as one or more in-order chunks
; that are appended into dialogue_text. Chunk 0 resets the accumulator; an
; out-of-order chunk (a gap from a CRC drop) is ignored, and the server's page
; retransmit re-sends from chunk 0. The page is flagged for the modal only when
; its CHUNK_END chunk lands.
netstream_apply_dialogue_page
        lda net_realtime_packet+NET_RT_DLG_CHUNK_IDX_OFFSET
        bne netstream_dialogue_not_first
        lda #0
        sta dialogue_text_len
        sta dialogue_next_chunk
netstream_dialogue_not_first
        lda net_realtime_packet+NET_RT_DLG_CHUNK_IDX_OFFSET
        cmp dialogue_next_chunk
        bne netstream_apply_dialogue_page_done      ; gap -> wait for retransmit
        lda net_realtime_packet+NET_RT_DLG_SPEAKER_OFFSET
        sta dialogue_speaker
        lda net_realtime_packet+NET_RT_DLG_PAGE_IDX_OFFSET
        sta dialogue_page_index
        lda net_realtime_packet+NET_RT_DLG_PAGE_CNT_OFFSET
        sta dialogue_page_count
        ldx #NET_RT_DLG_TEXT_LEN_OFFSET
        jsr net_append_dialogue_chunk
        inc dialogue_next_chunk
        lda net_realtime_packet+NET_RT_DLG_FLAGS_OFFSET
        and #DLG_FLAG_CHUNK_END
        beq netstream_apply_dialogue_page_done       ; more chunks coming
; dialogue_flags is only committed here, on the chunk that actually carries
; CHUNK_END, never per-chunk. The server retransmits an unacked page from
; chunk 0 on a timer (DIALOGUE_RESEND_INTERVAL_TICKS); committing on every
; chunk meant a retransmit's chunk 0 -- which never carries LAST_PAGE --
; briefly zeroed dialogue_flags while later chunks were still in flight. A
; player advancing past a multi-chunk final page in that window read
; LAST_PAGE as unset, waited for a next page the server had already closed
; out, and hung forever (the reported quest-turn-in freeze).
        lda net_realtime_packet+NET_RT_DLG_FLAGS_OFFSET
        sta dialogue_flags
        lda #1
        sta dialogue_page_dirty
        lda dialogue_active
        bne netstream_apply_dialogue_page_done
        lda #MODAL_REQ_DIALOGUE
        sta net_modal_request
netstream_apply_dialogue_page_done
        rts

; Append one chunk's text (ATASCII->screen codes) to dialogue_text at
; dialogue_text_len, capped at DIALOGUE_PAGE_MAX. X points at the packet's
; text-length byte. Terminates the buffer and updates dialogue_text_len.
net_append_dialogue_chunk
        lda net_realtime_packet,x
        cmp #NET_RT_DIALOGUE_CHUNK_MAX+1
        bcc net_append_dialogue_len_ok
        lda #NET_RT_DIALOGUE_CHUNK_MAX
net_append_dialogue_len_ok
        sta work
        inx
        lda #<dialogue_text
        sta wptr
        lda #>dialogue_text
        sta wptr+1
        ldy dialogue_text_len
        lda #0
        sta dlg_i
net_append_dialogue_loop
        lda dlg_i
        cmp work
        beq net_append_dialogue_done
        cpy #DIALOGUE_PAGE_MAX
        beq net_append_dialogue_done
        lda net_realtime_packet,x
        sec
        sbc #32
        sta (wptr),y
        inx
        iny
        inc dlg_i
        jmp net_append_dialogue_loop
net_append_dialogue_done
        sty dialogue_text_len
        lda #TITLE_LINE_END
        sta (wptr),y
        rts

; Blocking paged dialogue modal. Movement is frozen but realtime I/O keeps
; running, so the watchdog stays healthy and page acks reach the server. The
; server paces pages: the client acks the current page with a pickup bump and
; waits for the next DIALOGUE_PAGE before re-rendering.
show_dialogue_modal
        lda #0
        sta net_modal_request
        sta input_dir
        sta input_buttons
        sta dialogue_waiting
        sta dialogue_close_flag
        sta net_dialogue_decline
        sta dialogue_prev_action
        lda #1
        sta dialogue_active
        lda #DLG_SHOWN_NONE
        sta dialogue_shown_index
        jsr wait_frame_tick
        ldx #<display_list_text
        ldy #>display_list_text
        lda #OS_FONT_PAGE
        jsr apply_display_now
        jsr set_text_palette
        jsr init_screen_buffers
dialogue_modal_loop
        jsr netstream_service_modal_io
        lda dialogue_close_flag
        bne dialogue_modal_exit
; ESC is an unconditional local escape hatch. In particular, keep polling it
; while dialogue_waiting is set: that state can otherwise last forever when
; the next page cannot arrive because the network is down. The decline path
; bumps the persistent pickup counter and leaves net_dialogue_decline set, so
; the server cancels the active/pending quest dialogue once connectivity
; returns even though the modal has already closed locally.
        jsr dialogue_poll_escape
        bne dialogue_modal_decline
        lda dialogue_page_dirty
        beq dialogue_modal_input
        lda #0
        sta dialogue_page_dirty
; Ignore a retransmit of the page already shown; only a new index re-renders
; and re-enables input.
        lda dialogue_page_index
        cmp dialogue_shown_index
        beq dialogue_modal_input
        sta dialogue_shown_index
        lda #0
        sta dialogue_waiting
        jsr dialogue_render_page
dialogue_modal_input
        lda dialogue_waiting
        bne dialogue_modal_loop
        jsr dialogue_poll_input
        beq dialogue_modal_loop
        cmp #2
        beq dialogue_modal_decline
        jsr dialogue_send_ack
        lda dialogue_flags
        and #DLG_FLAG_LAST_PAGE
        beq dialogue_modal_wait_next
        lda #1
        sta dialogue_close_flag
        jmp dialogue_modal_loop
dialogue_modal_wait_next
        lda #1
        sta dialogue_waiting
        jmp dialogue_modal_loop
dialogue_modal_decline
        lda #NET_BUTTON_DIALOGUE_DECLINE
        sta net_dialogue_decline
        jsr dialogue_send_ack
        lda #1
        sta dialogue_close_flag
        jmp dialogue_modal_loop
dialogue_modal_exit
        lda #0
        sta dialogue_active
        jsr init_screen_buffers
        jsr wait_frame_tick
        ldx #<display_list_game
        ldy #>display_list_game
        lda current_font_page
        jsr apply_display_now
        jsr apply_palette
        lda #1
        sta net_snapshot_dirty
        rts

dialogue_send_ack
        inc net_pickup_counter
        rts

; Returns A: 1 when ESC is currently down, 0 otherwise. This deliberately
; ignores dialogue_prev_action: escape must work even if fire/RETURN is held
; or the modal is waiting for network data.
dialogue_poll_escape
        lda SKSTAT
        and #KEY_DOWN_MASK
        bne dialogue_poll_escape_idle
        lda KEY
        and #KEY_CODE_MASK
        cmp #KEY_ESC
        bne dialogue_poll_escape_idle
        lda #1
        rts
dialogue_poll_escape_idle
        lda #0
        rts

; Returns A: 1 = advance/accept (fire or RETURN), 2 = decline (ESC), 0 = none.
; Rising-edge gated via dialogue_prev_action so a held button fires once.
dialogue_poll_input
        ldx #0
        lda TRIG0
        bne dialogue_poll_keys
        ldx #1
        jmp dialogue_poll_edge
dialogue_poll_keys
        lda SKSTAT
        and #KEY_DOWN_MASK
        bne dialogue_poll_edge
        lda KEY
        and #KEY_CODE_MASK
        cmp #KEY_RETURN
        bne dialogue_poll_not_ret
        ldx #1
        jmp dialogue_poll_edge
dialogue_poll_not_ret
        cmp #KEY_ESC
        bne dialogue_poll_edge
        ldx #2
dialogue_poll_edge
        cpx #0
        beq dialogue_poll_idle
        lda dialogue_prev_action
        bne dialogue_poll_held
        stx dialogue_prev_action
        txa
        rts
dialogue_poll_held
        lda #0
        rts
dialogue_poll_idle
        stx dialogue_prev_action
        lda #0
        rts

dialogue_render_page
        jsr clear_screen
        jsr dialogue_draw_speaker
        lda #<dialogue_text
        sta wptr
        lda #>dialogue_text
        sta wptr+1
        jsr dialogue_draw_body
        jsr dialogue_draw_prompt
        jsr dialogue_draw_page_counter
        rts

dialogue_draw_speaker
        lda #DLG_SPEAKER_ROW
        sta screen_y
        lda #DLG_LEFT_MARGIN
        sta screen_x
        jsr dialogue_speaker_ptr
        jsr status_draw_text_ptr
        rts

; Word-wrap dialogue_text (screen codes; space=0; TITLE_LINE_END terminator)
; into the modal body. wptr already points at dialogue_text.
dialogue_draw_body
        lda #DLG_BODY_ROW
        sta dlg_row
        lda #0
        sta dlg_col
        sta dlg_i
dlg_body_loop
        ldy dlg_i
        lda (wptr),y
        cmp #TITLE_LINE_END
        beq dlg_body_done
        cmp #0
        bne dlg_body_word
        inc dlg_i
        lda dlg_col
        beq dlg_body_loop
        cmp #DLG_WRAP_WIDTH
        bcs dlg_body_space_wrap
        inc dlg_col
        jmp dlg_body_loop
dlg_body_space_wrap
        jsr dlg_body_newline
        jmp dlg_body_loop
dlg_body_word
        jsr dlg_measure_word
        lda dlg_col
        beq dlg_place_word
        clc
        adc dlg_wordlen
        cmp #DLG_WRAP_WIDTH+1
        bcc dlg_place_word
        jsr dlg_body_newline
dlg_place_word
        ldy dlg_i
        lda (wptr),y
        cmp #TITLE_LINE_END
        beq dlg_body_done
        cmp #0
        beq dlg_body_loop
        pha
        lda dlg_row
        sta screen_y
        lda dlg_col
        clc
        adc #DLG_LEFT_MARGIN
        sta screen_x
        jsr screen_cell_ptr
        pla
        ldy #0
        sta (ptr),y
        inc dlg_col
        inc dlg_i
        lda dlg_col
        cmp #DLG_WRAP_WIDTH
        bcc dlg_place_word
        jsr dlg_body_newline
        jmp dlg_place_word
dlg_body_done
        rts
dlg_body_newline
        inc dlg_row
        lda #0
        sta dlg_col
        rts
dlg_measure_word
        lda #0
        sta dlg_wordlen
        ldy dlg_i
dlg_measure_loop
        lda (wptr),y
        cmp #TITLE_LINE_END
        beq dlg_measure_done
        cmp #0
        beq dlg_measure_done
        inc dlg_wordlen
        iny
        jmp dlg_measure_loop
dlg_measure_done
        rts

dialogue_draw_prompt
        lda #DLG_PROMPT_ROW
        sta screen_y
        lda #DLG_LEFT_MARGIN
        sta screen_x
        lda dialogue_flags
        and #DLG_FLAG_LAST_PAGE
        beq dialogue_prompt_more
        lda dialogue_flags
        and #DLG_FLAG_QUEST_OFFER
        bne dialogue_prompt_offer
        lda #<dlg_prompt_close
        sta wptr
        lda #>dlg_prompt_close
        sta wptr+1
        jmp dialogue_prompt_draw
dialogue_prompt_offer
        lda #<dlg_prompt_offer
        sta wptr
        lda #>dlg_prompt_offer
        sta wptr+1
        jmp dialogue_prompt_draw
dialogue_prompt_more
        lda #<dlg_prompt_more
        sta wptr
        lda #>dlg_prompt_more
        sta wptr+1
dialogue_prompt_draw
        jsr status_draw_text_ptr
        rts

dialogue_draw_page_counter
        lda #DLG_PAGE_ROW
        sta screen_y
        lda #DLG_LEFT_MARGIN
        sta screen_x
        lda dialogue_page_index
        clc
        adc #1
        clc
        adc #16
        jsr status_store_tile
        inc screen_x
        lda #15
        jsr status_store_tile
        inc screen_x
        lda dialogue_page_count
        clc
        adc #16
        jsr status_store_tile
        rts

; Speaker id (NPC subtype) -> client-local name string in wptr.
dialogue_speaker_ptr
        lda dialogue_speaker
        cmp #3
        bne dlg_spk_not_nerissa
        lda #<dlg_name_nerissa
        sta wptr
        lda #>dlg_name_nerissa
        sta wptr+1
        rts
dlg_spk_not_nerissa
        cmp #4
        bne dlg_spk_not_daniel
        lda #<dlg_name_daniel
        sta wptr
        lda #>dlg_name_daniel
        sta wptr+1
        rts
dlg_spk_not_daniel
        cmp #5
        bne dlg_spk_not_wilhelm
        lda #<dlg_name_wilhelm
        sta wptr
        lda #>dlg_name_wilhelm
        sta wptr+1
        rts
dlg_spk_not_wilhelm
        cmp #6
        bne dlg_spk_not_lucian
        lda #<dlg_name_lucian
        sta wptr
        lda #>dlg_name_lucian
        sta wptr+1
        rts
dlg_spk_not_lucian
        cmp #7
        bne dlg_spk_unknown
        lda #<dlg_name_grix
        sta wptr
        lda #>dlg_name_grix
        sta wptr+1
        rts
dlg_spk_unknown
        lda #<dlg_name_unknown
        sta wptr
        lda #>dlg_name_unknown
        sta wptr+1
        rts

dlg_name_nerissa
        dta 46,37,50,41,51,51,33,TITLE_LINE_END
dlg_name_daniel
        dta 36,33,46,41,37,44,TITLE_LINE_END
dlg_name_wilhelm
        dta 55,41,44,40,37,44,45,TITLE_LINE_END
dlg_name_lucian
        dta 44,53,35,41,33,46,TITLE_LINE_END
dlg_name_grix
        dta 39,50,41,56,TITLE_LINE_END
dlg_name_unknown
        dta 31,TITLE_LINE_END
dlg_prompt_more
        dta 38,41,50,37,29,46,37,56,52,TITLE_LINE_END
dlg_prompt_close
        dta 38,41,50,37,29,36,47,46,37,TITLE_LINE_END
dlg_prompt_offer
        dta 38,41,50,37,29,57,37,51,0,37,51,35,29,46,47,TITLE_LINE_END
; Guard: the dialogue block must stay below the player sprites at $8000.
        ert *>$8000

        org SFX_CODE
draw_hud_pvp_kills
        lda #HUD_PVP_X+3
        sta screen_x
        lda #OS_COLON
        jsr status_store_tile
        inc screen_x
        jmp hud_draw_four_digits

hud_draw_four_digits
        lda hud_pvp_kills_lo
        sta hud_digits_value_lo
        lda hud_pvp_kills_hi
        sta hud_digits_value_hi
hud_draw_four_digits_value
        cmp #$27
        bcc hud_four_digits_clamped
        bne hud_four_digits_set_max
        lda hud_digits_value_lo
        cmp #$10
        bcc hud_four_digits_clamped
hud_four_digits_set_max
        lda #$0f
        sta hud_digits_value_lo
        lda #$27
        sta hud_digits_value_hi
hud_four_digits_clamped
        lda #0
        sta hud_digits_tmp
hud_four_thousands_loop
        lda hud_digits_value_hi
        cmp #$03
        bcc hud_four_thousands_done
        bne hud_four_thousands_sub
        lda hud_digits_value_lo
        cmp #$e8
        bcc hud_four_thousands_done
hud_four_thousands_sub
        sec
        lda hud_digits_value_lo
        sbc #$e8
        sta hud_digits_value_lo
        lda hud_digits_value_hi
        sbc #$03
        sta hud_digits_value_hi
        inc hud_digits_tmp
        jmp hud_four_thousands_loop
hud_four_thousands_done
        lda hud_digits_tmp
        jsr hud_draw_digit
        inc screen_x
        lda #0
        sta hud_digits_tmp
hud_four_hundreds_loop
        lda hud_digits_value_hi
        bne hud_four_hundreds_sub
        lda hud_digits_value_lo
        cmp #100
        bcc hud_four_hundreds_done
hud_four_hundreds_sub
        sec
        lda hud_digits_value_lo
        sbc #100
        sta hud_digits_value_lo
        lda hud_digits_value_hi
        sbc #0
        sta hud_digits_value_hi
        inc hud_digits_tmp
        jmp hud_four_hundreds_loop
hud_four_hundreds_done
        lda hud_digits_tmp
        jsr hud_draw_digit
        inc screen_x
        lda #0
        sta hud_digits_tmp
hud_four_tens_loop
        lda hud_digits_value_hi
        bne hud_four_tens_sub
        lda hud_digits_value_lo
        cmp #10
        bcc hud_four_tens_done
hud_four_tens_sub
        sec
        lda hud_digits_value_lo
        sbc #10
        sta hud_digits_value_lo
        lda hud_digits_value_hi
        sbc #0
        sta hud_digits_value_hi
        inc hud_digits_tmp
        jmp hud_four_tens_loop
hud_four_tens_done
        lda hud_digits_tmp
        jsr hud_draw_digit
        inc screen_x
        lda hud_digits_value_lo
        jmp hud_draw_digit

netstream_cycle_baud
        inc netstream_baud_index
        lda netstream_baud_index
        cmp #4
        bcc netstream_apply_baud
        lda #0
        sta netstream_baud_index
netstream_apply_baud
        lda netstream_baud_index
        asl
        tax
        lda netstream_baud_table,x
        sta netstream_args
        sta netstream_realtime_args
        lda netstream_baud_table+1,x
        sta netstream_args+1
        sta netstream_realtime_args+1
        rts

draw_title_baud
        lda #19
        sta screen_y
        lda #20
        sta screen_x
        jsr screen_cell_ptr
        lda netstream_baud_index
        asl
        asl
        clc
        adc netstream_baud_index
        tax
        ldy #0
draw_title_baud_digit_loop
        lda netstream_baud_digits,x
        sta (ptr),y
        inx
        iny
        cpy #5
        bne draw_title_baud_digit_loop
        rts

netstream_baud_table
        dta <31250,>31250
        dta <38400,>38400
        dta <40500,>40500
        dta <19200,>19200
netstream_baud_digits
        dta DIGIT0+3,DIGIT0+1,DIGIT0+2,DIGIT0+5,DIGIT0+0
        dta DIGIT0+3,DIGIT0+8,DIGIT0+4,DIGIT0+0,DIGIT0+0
        dta DIGIT0+4,DIGIT0+0,DIGIT0+5,DIGIT0+0,DIGIT0+0
        dta DIGIT0+1,DIGIT0+9,DIGIT0+2,DIGIT0+0,DIGIT0+0

title_help_down
        lda SKSTAT
        and #KEY_DOWN_MASK
        bne title_help_down_no
        lda KEY
        cmp #KEY_NONE
        beq title_help_down_no
        and #KEY_CODE_MASK
        cmp #KEY_H
        bne title_help_down_no
        lda #0
        rts
title_help_down_no
        lda #1
        rts

; SPACE acts like the joystick fire button on any "press fire" screen --
; here, that's "press fire to start." Returns with the zero flag set
; (via a following BEQ/BNE) exactly like a bare STRIG0 check would.
title_fire_or_space_down
        lda TRIG0
        beq title_fire_down_yes
        lda SKSTAT
        and #KEY_DOWN_MASK
        bne title_fire_down_no
        lda KEY
        cmp #KEY_NONE
        beq title_fire_down_no
        and #KEY_CODE_MASK
        cmp #KEY_SPACE
        bne title_fire_down_no
title_fire_down_yes
        lda #0
        rts
title_fire_down_no
        lda #1
        rts

net_parse_len_valid
        lda net_packet_type
        cmp #NET_PKT_WELCOME
        beq net_parse_len_valid_welcome
        cmp #NET_PKT_WINDOW
        beq net_parse_len_valid_window
        cmp #NET_PKT_SNAPSHOT
        beq net_parse_len_valid_snapshot
        sec
        rts
net_parse_len_valid_welcome
        lda net_packet_len
        cmp #5
        beq net_parse_len_valid_ok
        sec
        rts
net_parse_len_valid_window
        lda net_packet_len
        cmp #NET_WINDOW_HEAD_LEN
        bcc net_parse_len_valid_bad
        clc
        rts
net_parse_len_valid_snapshot
        lda net_packet_len
        cmp #NET_SNAPSHOT_PAYLOAD_LEN
        beq net_parse_len_valid_ok
net_parse_len_valid_bad
        sec
        rts
net_parse_len_valid_ok
        clc
        rts

net_parse_mid_magic_resync
        inc net_rx_drops
        jmp net_parse_magic_ok

; WINDOW_ROW routing. Three cases, in stream order guarantees:
; 1. Row for the already-committed window origin (straggler of a fill that
;    completed early off accumulated masks, or a same-origin refresh after a
;    reattach): apply straight to the ACTIVE cache like a terrain patch.
;    Same origin means there is no mixed-origin hazard, and arming the fill
;    state here would block terrain edges waiting for 24 rows that will
;    never arrive.
; 2. Row continuing the staged fill (matches pending origin): stage it.
; 3. Anything else starts a fresh staged fill at that row's origin.
; During a map transition the same numeric origin can belong to the new
; map, so case 1 is disabled from MAP_CHANGE parse until the fill commits.
netstream_window_row_route
        lda net_realtime_packet+NET_RT_WINDOW_ROW_INDEX_OFFSET
        cmp #NET_WINDOW_H
        bcc netstream_window_row_index_ok
        rts
netstream_window_row_index_ok
        lda net_realtime_packet+NET_RT_WINDOW_ROW_OY_OFFSET
        sec
        sbc net_realtime_packet+NET_RT_WINDOW_ROW_INDEX_OFFSET
        sta net_resync_row_origin_y
        lda net_realtime_packet+NET_RT_WINDOW_ROW_FILL_ID_OFFSET
        ora net_map_fill_pending
        ora net_map_change_pending
        bne netstream_window_row_staged
        lda net_row_fill_active
        bne netstream_window_row_staged
        lda net_realtime_packet+NET_RT_WINDOW_ROW_OX_OFFSET
        cmp net_window_origin_x
        bne netstream_window_row_staged
        lda net_resync_row_origin_y
        cmp net_window_origin_y
        beq netstream_window_row_in_place
netstream_window_row_staged
        lda net_row_fill_active
        beq netstream_window_row_start_fill
        lda net_realtime_packet+NET_RT_WINDOW_ROW_FILL_ID_OFFSET
        cmp net_fill_id
        bne netstream_window_row_start_fill
        lda net_realtime_packet+NET_RT_WINDOW_ROW_OX_OFFSET
        cmp net_pending_origin_x
        bne netstream_window_row_start_fill
        lda net_resync_row_origin_y
        cmp net_pending_origin_y
        beq netstream_window_row_apply
netstream_window_row_start_fill
; A late duplicate row from the fill just committed must not re-arm a fresh
; one-row transaction (the server would never complete it).
        lda net_realtime_packet+NET_RT_WINDOW_ROW_FILL_ID_OFFSET
        beq netstream_window_row_start_ok
        cmp net_last_committed_fill_id
        bne netstream_window_row_start_ok
        rts
netstream_window_row_start_ok
        jsr netstream_clear_window_row_masks
        lda #0
        sta net_window_rows_loaded
        lda #1
        sta net_row_fill_active
        lda net_realtime_packet+NET_RT_WINDOW_ROW_OX_OFFSET
        sta net_pending_origin_x
        lda net_realtime_packet+NET_RT_WINDOW_ROW_FILL_ID_OFFSET
        sta net_fill_id
        lda #0
        sta net_pending_origin_x_hi
        lda net_resync_row_origin_y
        sta net_pending_origin_y
        lda #0
        sta net_pending_origin_y_hi
netstream_window_row_apply
        jsr netstream_store_pending_window_row
; Fill progress re-stamps the retry clock: the retry timer then fires only
; after NET_RESYNC_RETRY_DELAY frames without a row (stalled/broken fill),
; instead of racing a healthy fill that outlives the request interval.
        lda RTCLOK
        sta net_resync_request_clk
        jmp netstream_window_row_complete_check

; Case 1: rebuild the 32x1 absolute patch the pre-atomic path used and let
; net_apply_window_patch write/draw it against the active cache. Receiving
; our own origin's data also means the server is answering us, so a pending
; resync request is satisfied.
netstream_window_row_in_place
        lda #0
        sta net_resync_pending
        lda net_realtime_packet+NET_RT_WINDOW_ROW_OX_OFFSET
        sta net_packet_payload+2
        lda #0
        sta net_packet_payload+3
        lda net_realtime_packet+NET_RT_WINDOW_ROW_OY_OFFSET
        sta net_packet_payload+4
        lda #0
        sta net_packet_payload+5
        lda #NET_WINDOW_W
        sta net_packet_payload+6
        lda #1
        sta net_packet_payload+7
        lda #0
        sta net_packet_payload+8
        lda #1
        sta net_packet_payload+9
        ldx #0
netstream_window_row_in_place_copy
        lda net_realtime_packet+NET_RT_WINDOW_ROW_TILES_OFFSET,x
        sta net_packet_payload+NET_WINDOW_TILE_OFFSET,x
        inx
        cpx #NET_WINDOW_W
        bne netstream_window_row_in_place_copy
        jmp net_apply_window_patch

; MAP_CHANGE and the new map's first WINDOW_ROWs can arrive in one recv
; batch, so stale fill state must reset here at parser depth, before those
; rows are staged. handle_map_change runs a main-loop later and must not
; touch the bitmap (it would wipe bits for rows already staged).
netstream_map_change_reset_fill
        jsr netstream_clear_window_row_masks
        lda #0
        sta net_row_fill_active
        rts

netstream_store_pending_window_row
        lda net_realtime_packet+NET_RT_WINDOW_ROW_INDEX_OFFSET
        sta cache_local_y
        lsr
        clc
        adc cache_pending_hi
        sta ptr+1
        lda cache_local_y
        and #1
        beq netstream_store_pending_row_even
        lda #$80
        jmp netstream_store_pending_row_ptr
netstream_store_pending_row_even
        lda #0
netstream_store_pending_row_ptr
        sta ptr
        ldx #0
        ldy #0
netstream_store_pending_row_loop
        lda net_realtime_packet+NET_RT_WINDOW_ROW_TILES_OFFSET,x
        sta (ptr),y
        inc ptr
        inx
        cpx #NET_WINDOW_W
        bne netstream_store_pending_row_loop
        rts

netstream_reset_bootstrap_receive
        lda #0
        sta network_got_welcome
        sta network_got_window
        sta net_window_rows_loaded
        sta net_parser_state
        sta net_parser_index
        sta net_parser_checksum
        sta net_snapshot_pending
        rts

netstream_bootstrap_retry
        lda network_got_welcome
        beq netstream_bootstrap_retry_no_welcome
        sta netstream_final_flags
netstream_bootstrap_retry_no_welcome
        dec netstream_result
        beq netstream_bootstrap_retry_fail
        jsr netstream_reset_bootstrap_receive
        jsr netstream_send_hello
        bcs netstream_bootstrap_retry_fail
        jmp netstream_bootstrap_begin
netstream_bootstrap_retry_fail
        sec
        rts

netstream_bootstrap_start
        lda #0
        sta netstream_final_flags
        lda #3
        sta netstream_result
netstream_bootstrap_begin
        lda #1
        sta network_enabled
        lda #180
        sta netstream_timeout
        clc
        rts

; Tells FujiNet to tear down its active Netstream TCP session by reusing
; the normal enable-stream command ($70/$F0) with host "STOP" -- the same
; trick systemBus::setStreamHostWithOptions() checks for firmware-side.
; appkey_data_buf is idle here (title/game-boundary transition, no appkey
; transaction in flight) so it doubles as the scratch payload buffer.
netstream_send_stop
        lda #83                        ; 'S'
        sta appkey_data_buf+0
        lda #84                        ; 'T'
        sta appkey_data_buf+1
        lda #79                        ; 'O'
        sta appkey_data_buf+2
        lda #80                        ; 'P'
        sta appkey_data_buf+3
        lda #0
        ldx #4
netstream_send_stop_zero
        sta appkey_data_buf,x
        inx
        cpx #64
        bne netstream_send_stop_zero
        lda #FUJI_DEVICE
        sta DDEVIC
        lda #FUJI_UNIT
        sta DUNIT
        lda #FUJICMD_ENABLE_UDPSTREAM
        sta DCOMND
        lda #$80
        sta DSTATS
        lda #<appkey_data_buf
        sta DBUFLO
        lda #>appkey_data_buf
        sta DBUFHI
        lda #64
        sta DBYTLO
        lda #0
        sta DBYTHI
        sta DAUX1
        sta DAUX2
        jsr SIOV
        rts

disable_attract_mode
        lda #0
        sta ATRACT
        rts

; v2 size-table/magic-resync parser helpers retired by realtime v3
; (COBS delimiters realign the stream; CRC-16 validates frames).
netstream_resync_none
        lda #0
        sta net_rt_rx_index
        rts

cio_put_prompt
        lda username_prompt_mode
        beq cio_put_prompt_normal
        lda #<username_prompt_taken_text
        sta ICBAL
        lda #>username_prompt_taken_text
        sta ICBAH
        lda #USERNAME_PROMPT_TAKEN_TEXT_LEN
        sta ICBLL
        jmp cio_put_prompt_common
cio_put_prompt_normal
        lda #<username_prompt_text
        sta ICBAL
        lda #>username_prompt_text
        sta ICBAH
        lda #USERNAME_PROMPT_TEXT_LEN
        sta ICBLL
cio_put_prompt_common
        lda #0
        sta ICBLH
        lda #CIO_PUT_RECORD
        sta ICCMD
        ldx #IOCB1_X
        jsr CIOV
        cpy #1
        bne cio_put_prompt_fail
        clc
        rts
cio_put_prompt_fail
        sec
        rts

sfx_update
        stx sfx_update_save_x
        sty sfx_update_save_y
        lda wptr
        sta sfx_update_save_wptr
        lda wptr+1
        sta sfx_update_save_wptr+1
        lda RTCLOK
        cmp sfx_clk
        bne sfx_update_go
        jmp sfx_update_restore
sfx_update_go
        sta sfx_clk
        ldx sfx_ch1_id
        beq sfx_ch1_skip
        dec sfx_ch1_step
        bne sfx_ch1_play
        lda #0
        sta sfx_ch1_id
        sta sfx_ch1_prio
        sta AUDC1
        jmp sfx_ch2_begin
sfx_ch1_play
        lda sfx_audf_lo,x
        sta wptr
        lda sfx_audf_hi,x
        sta wptr+1
        ldy sfx_ch1_step
        lda (wptr),y
        sta AUDF1
        lda sfx_audc_lo,x
        sta wptr
        lda sfx_audc_hi,x
        sta wptr+1
        lda (wptr),y
        sta AUDC1
sfx_ch1_skip
sfx_ch2_begin
        ldx sfx_ch2_id
        beq sfx_ch2_skip
        dec sfx_ch2_step
        bne sfx_ch2_play
        lda #0
        sta sfx_ch2_id
        sta sfx_ch2_prio
        sta AUDC2
        jmp sfx_update_done
sfx_ch2_play
        lda sfx_audf_lo,x
        sta wptr
        lda sfx_audf_hi,x
        sta wptr+1
        ldy sfx_ch2_step
        lda (wptr),y
        sta AUDF2
        lda sfx_audc_lo,x
        sta wptr
        lda sfx_audc_hi,x
        sta wptr+1
        lda (wptr),y
        sta AUDC2
sfx_ch2_skip
sfx_update_done
        lda sfx_update_save_wptr
        sta wptr
        lda sfx_update_save_wptr+1
        sta wptr+1
        ldx sfx_update_save_x
        ldy sfx_update_save_y
        rts
sfx_update_restore
        lda sfx_update_save_wptr
        sta wptr
        lda sfx_update_save_wptr+1
        sta wptr+1
        ldx sfx_update_save_x
        ldy sfx_update_save_y
        rts

sfx_request
        sta sfx_request_id
        stx sfx_request_save_x
        sty sfx_request_save_y
        lda wptr
        sta sfx_request_save_wptr
        lda wptr+1
        sta sfx_request_save_wptr+1
        ldx sfx_request_id
        lda sfx_channel,x
        cmp #1
        bne sfx_req_ch2
        lda sfx_ch1_id
        beq sfx_req_ch1_start
        lda sfx_prio,x
        cmp sfx_ch1_prio
        bcc sfx_req_done
sfx_req_ch1_start
        stx sfx_ch1_id
        lda sfx_len,x
        sta sfx_ch1_step
        lda sfx_prio,x
        sta sfx_ch1_prio
        lda sfx_audf_lo,x
        sta wptr
        lda sfx_audf_hi,x
        sta wptr+1
        ldy sfx_ch1_step
        lda (wptr),y
        sta AUDF1
        lda sfx_audc_lo,x
        sta wptr
        lda sfx_audc_hi,x
        sta wptr+1
        lda (wptr),y
        sta AUDC1
        jmp sfx_req_done
sfx_req_ch2
        lda sfx_ch2_id
        beq sfx_req_ch2_start
        lda sfx_prio,x
        cmp sfx_ch2_prio
        bcc sfx_req_done
sfx_req_ch2_start
        stx sfx_ch2_id
        lda sfx_len,x
        sta sfx_ch2_step
        lda sfx_prio,x
        sta sfx_ch2_prio
        lda sfx_audf_lo,x
        sta wptr
        lda sfx_audf_hi,x
        sta wptr+1
        ldy sfx_ch2_step
        lda (wptr),y
        sta AUDF2
        lda sfx_audc_lo,x
        sta wptr
        lda sfx_audc_hi,x
        sta wptr+1
        lda (wptr),y
        sta AUDC2
sfx_req_done
        lda sfx_request_save_wptr
        sta wptr
        lda sfx_request_save_wptr+1
        sta wptr+1
        ldx sfx_request_save_x
        ldy sfx_request_save_y
        rts

sfx_for_message
        cmp #22
        bcs sfx_for_message_done
        tax
        lda sfx_message_map,x
        beq sfx_for_message_done
        jsr sfx_request
sfx_for_message_done
        rts

sfx_shoot_audf
        dta 0,40,32,24,16,10
sfx_shoot_audc
        dta 0,$a2,$a4,$a6,$a8,$a8
sfx_hurt_audf
        dta 0,140,160,180,200
sfx_hurt_audc
        dta 0,$c4,$c8,$cc,$ce
sfx_death_audf
        dta 0,90,80,70,60,50,40,30,20
sfx_death_audc
        dta 0,$a2,$a4,$a6,$a8,$aa,$ac,$ae,$ae
sfx_kill_audf
        dta 0,60,50,40,30
sfx_kill_audc
        dta 0,$84,$88,$8c,$8e
sfx_lvl_audf
        dta 0,$17,$17,$17,$1d,$1d,$1d,$23,$23,$23
sfx_lvl_audc
        dta 0,$a8,$a8,$a8,$a8,$a8,$a8,$a8,$a8,$a8

sfx_audf_lo
        dta 0,<sfx_shoot_audf,<sfx_hurt_audf,<sfx_death_audf,<sfx_kill_audf,<sfx_lvl_audf
sfx_audf_hi
        dta 0,>sfx_shoot_audf,>sfx_hurt_audf,>sfx_death_audf,>sfx_kill_audf,>sfx_lvl_audf
sfx_audc_lo
        dta 0,<sfx_shoot_audc,<sfx_hurt_audc,<sfx_death_audc,<sfx_kill_audc,<sfx_lvl_audc
sfx_audc_hi
        dta 0,>sfx_shoot_audc,>sfx_hurt_audc,>sfx_death_audc,>sfx_kill_audc,>sfx_lvl_audc
sfx_len
        dta 0,5,4,8,4,9
sfx_channel
        dta 0,1,1,1,2,2
sfx_prio
        dta 0,1,2,3,1,2
sfx_message_map
        dta 0,0,0,0,0,SFX_KILL,0,0,0,0,SFX_LEVELUP,SFX_DEATH
        dta SFX_DEATH,SFX_DEATH,0,SFX_KILL,0,0,0,0,0,0

; Phase 70 common local/remote projectile step. A=DIR_* (0-7),
; target_x/target_y=current cell. Returns carry set with target advanced, or
; clear at an edge/closed corner. Clobbers A/X/Y, ptr, and cache pointer
; scratch through bullet_target_hits_terrain.
shot_step_target
        cmp #8
        bcs shot_step_blocked
        tax
        cpx #4
        bcc shot_step_advance
; Diagonal rays require both orthogonal side cells to be terrain-clear.
        lda target_x
        clc
        adc shot_dx,x
        sta target_x
        jsr bullet_target_hits_terrain
        pha
        lda target_x
        sec
        sbc shot_dx,x
        sta target_x
        pla
        bne shot_step_blocked
        lda target_y
        clc
        adc shot_dy,x
        sta target_y
        jsr bullet_target_hits_terrain
        pha
        lda target_y
        sec
        sbc shot_dy,x
        sta target_y
        pla
        bne shot_step_blocked
shot_step_advance
        lda target_x
        clc
        adc shot_dx,x
        cmp #1
        bcc shot_step_blocked
        cmp #127
        bcs shot_step_blocked
        sta target_x
        lda target_y
        clc
        adc shot_dy,x
        cmp #1
        bcc shot_step_blocked
        cmp #95
        bcs shot_step_blocked
        sta target_y
        sec
        rts
shot_step_blocked
        clc
        rts

shot_dx
        dta 0,0,$ff,1,$ff,1,$ff,1
shot_dy
        dta $ff,1,0,0,$ff,$ff,1,1

; A=facing (0-7). Return the existing remote sprite base; diagonal values use
; their horizontal component. Invalid values retain the safe front frame.
select_remote_facing_base
        cmp #DIR_LEFT
        bcc select_remote_facing_front
        cmp #8
        bcs select_remote_facing_front
        and #1
        beq select_remote_facing_left
        lda #REMOTE_RIGHT_0
        rts
select_remote_facing_left
        lda #REMOTE_LEFT_0
        rts
select_remote_facing_front
        lda #REMOTE_FRONT_0
        rts

; Guard: helper/SFX block must not grow into the $A000 cartridge area.
        ert *>$A000

        run start
