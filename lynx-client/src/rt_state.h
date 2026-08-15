#ifndef FUJIREALM_RT_STATE_H
#define FUJIREALM_RT_STATE_H

/* Realtime v3 frame parsing and live game state (host-testable, no Lynx
 * dependencies). Raw frame layout after COBS decode:
 *   [0] payload len N (0..54)   [1] version = 3   [2] type   [3] status
 *   [4-5] seq LE   [6..6+N) payload   [6+N..6+N+2) CRC-16/CCITT-FALSE LE
 * Trailing zero payload bytes are stripped on the wire; rt_apply re-pads.
 */

#define RTS_VERSION 3
#define RTS_MAX_RAW 62
#define RTS_WORKSPACE 64

/* rt_apply() return for a frame that failed validation (bad length,
 * version, or CRC), as distinct from 0, which means a well-formed frame of
 * a type this client does not handle. Counting the two separately is what
 * makes a corrupted-reception rate measurable. */
#define RTS_INVALID 0xFF

#define RTS_PLAYER_STATE 1
#define RTS_WORLD_STATE 2
#define RTS_TERRAIN_EDGE 3
#define RTS_MAP_CHANGE 5
#define RTS_AUTH 13
#define RTS_REMOTE_PLAYERS 14
#define RTS_HUD_UPDATE 7
#define RTS_MESSAGE 8
#define RTS_QUEST_UPDATE 9
#define RTS_DIALOGUE_PAGE 24
#define RTS_RESYNC_REQUEST 15
#define RTS_WINDOW_ROW 16
#define RTS_ITEM_DROPS 17
#define RTS_MAP_READY 19
#define RTS_WINDOW_COMMIT 20
#define RTS_CACHE_STEP_ACK 21
#define RTS_WINDOW_COMMIT_ACK 22

#define RTS_MAX_BEAVERS 6
#define RTS_MAX_REMOTE_PLAYERS 12
#define RTS_MAX_ITEMS 4
#define RTS_TEXT_MAX 39

/* Item ids on the wire (server items.py / entities.py subtypes). Id 5 was the
 * Lost Charm before The Dam Below reused the slot for the Warden Key; the
 * server keeps them aliased for save compatibility. */
#define RTS_ITEM_GOLD 1
#define RTS_ITEM_STICKS 2
#define RTS_ITEM_HERB 3
#define RTS_ITEM_POTION 4
#define RTS_ITEM_WARDEN_KEY 5
#define RTS_ITEM_OIL_SAMPLE 6
#define RTS_ITEM_RUST_SAMPLE 7

/* Art selection for an item drop, as returned by rt_item_art_index(). Kept
 * out of the renderer so the id -> art mapping is host-testable. */
#define RTS_ART_ITEM_NONE 0
#define RTS_ART_ITEM_GOLD 1
#define RTS_ART_ITEM_STICKS 2
#define RTS_ART_ITEM_HERB 3
#define RTS_ART_ITEM_POTION 4
#define RTS_ART_ITEM_KEY 5

/* Low 7 bits of a dynamic-entity kind byte are the species; bit 7 is a
 * transient "damage just landed" pulse (server ENEMY_KIND_HIT_PULSE). Kinds 7
 * and 8 are not enemies at all -- Wilhelm shares the entity slots. */
#define RTS_KIND_MASK 0x7F
#define RTS_KIND_HIT_PULSE 0x80
#define RTS_KIND_BEAVER 1
#define RTS_KIND_SNAKE 2
#define RTS_KIND_BAT 3
#define RTS_KIND_SLIME 4
#define RTS_KIND_GOBLIN 5
#define RTS_KIND_GORVAK 6
#define RTS_KIND_WILHELM 7
#define RTS_KIND_WILHELM_WORKING 8
#define RTS_KIND_MAX 8
/* Frames an entity blinks for after a hit pulse arrives. */
#define RTS_HIT_FLASH_FRAMES 8

#define RTS_REMOTE_ALIVE 0x01
#define RTS_REMOTE_PVP 0x02
/* Bits 2-3 of the remote-player state byte carry the low two bits of the
 * server's accepted-shot counter; a change spawns a cosmetic tracer. */
#define RTS_REMOTE_STATE_FIRE_MASK 0x0C
#define RTS_BUTTON_FIRE 0x01
/* Answers a quest offer with "no" on the same PLAYER_STATE that bumps the
 * pickup counter (server PLAYER_DIALOGUE_DECLINE_BUTTON). Bit 1 is otherwise
 * unread, so a stray set here silently declines quests: only the dialogue ack
 * path may ever set it. */
#define RTS_BUTTON_DIALOGUE_DECLINE 0x02
/* Bit 0 of the HUD_UPDATE flags byte: this player currently has PvP enabled. */
#define RTS_HUD_FLAG_PVP_ENABLED 0x01

/* Shots travel at most this many tiles before fizzling; they also stop on the
 * first blocking tile or actor, whichever comes first. */
#define RTS_BULLET_RANGE 6
/* One local shot plus a few concurrent remote tracers. */
#define RTS_MAX_TRACERS 4

#define RTS_WINDOW_W 32
#define RTS_WINDOW_H 24

/* TERRAIN_EDGE strips are one row (RTS_WINDOW_W tiles) or one column
 * (RTS_WINDOW_H tiles); 48 is the wire cap (54-byte max v3 payload minus the
 * 6-byte edge header). */
#define RTS_EDGE_MAX_TILES 48

/* Client facing codes (server CLIENT_AIM_*). 4-7 are the Phase 70 diagonals;
 * the server refuses anything outside 0-7 rather than clamping it. */
#define RTS_FACE_UP 0
#define RTS_FACE_DOWN 1
#define RTS_FACE_LEFT 2
#define RTS_FACE_RIGHT 3
#define RTS_FACE_UP_LEFT 4
#define RTS_FACE_UP_RIGHT 5
#define RTS_FACE_DOWN_LEFT 6
#define RTS_FACE_DOWN_RIGHT 7
#define RTS_FACE_COUNT 8
/* Diagonals are the codes at or above this; cardinals sit below it. */
#define RTS_FACE_FIRST_DIAGONAL 4

/* DIALOGUE_PAGE. A display page is up to RTS_DLG_PAGE_MAX characters, streamed
 * as RTS_DLG_CHUNK_MAX-byte chunks (one per server tick, split on byte
 * boundaries, so a chunk can end mid-word). After the last chunk the server
 * waits for an ack, then retransmits the whole page from chunk 0 every 20
 * ticks up to 6 times -- so reassembly must be idempotent on a replay. */
#define RTS_DLG_CHUNK_MAX 47
#define RTS_DLG_PAGE_MAX 141
#define RTS_DLG_FLAG_QUEST_OFFER 0x01
#define RTS_DLG_FLAG_ACK_ONLY 0x02
#define RTS_DLG_FLAG_LAST_PAGE 0x04
#define RTS_DLG_FLAG_CHUNK_END 0x08
/* No page has been rendered yet (Atari DLG_SHOWN_NONE). */
#define RTS_DLG_SHOWN_NONE 0xFF

/* Dialogue speaker ids are NPC subtypes (server entities.py); 0 means the
 * scene has no speaker, as in the Deep Pump controls. */
#define RTS_SPEAKER_NONE 0
#define RTS_SPEAKER_NERISSA 3
#define RTS_SPEAKER_DANIEL 4
#define RTS_SPEAKER_WILHELM 5
#define RTS_SPEAKER_LUCIAN 6
#define RTS_SPEAKER_GRIX 7

struct rt_beaver {
    unsigned char x;
    unsigned char y;
    unsigned char hp;
    /* Species only: rt_apply masks off the hit-pulse bit. */
    unsigned char kind;
    /* Counts down in frames while the entity blinks from a hit. */
    unsigned char hit_timer;
};

struct rt_remote_player {
    unsigned char x;
    unsigned char y;
    unsigned char facing;
    unsigned char state;
};

struct rt_item {
    unsigned char x;
    unsigned char y;
    unsigned char item_id;
    unsigned char quantity;
};

/* A moving shot marker. Local fire and remote-player fire share one array so
 * the same range/collision rules apply to every shot on screen. */
struct rt_tracer {
    unsigned char active;
    unsigned char x;
    unsigned char y;
    unsigned char dir;
    unsigned char steps;
};

/* Raw TERRAIN_EDGE payload, refreshed each time rt_apply returns
 * RTS_TERRAIN_EDGE. Applying it to the active terrain cache (idempotent
 * shift, revision/adjacency checks) is cache-layer logic, not codec work. */
struct rt_terrain_edge {
    unsigned char origin_x;
    unsigned char origin_y;
    unsigned char width;
    unsigned char height;
    unsigned revision;
    unsigned char tile_count;
    unsigned char tiles[RTS_EDGE_MAX_TILES];
};

/* Raw WINDOW_ROW payload, refreshed each time rt_apply returns
 * RTS_WINDOW_ROW. Self-describing per the wire protocol: absolute origin is
 * (origin_x, origin_y - row_index). */
struct rt_window_row {
    unsigned char origin_x;
    unsigned char origin_y;
    unsigned char row_index;
    unsigned char fill_id;
    unsigned char tiles[RTS_WINDOW_W];
};

struct rt_window_commit_ack {
    unsigned char fill_id;
    unsigned char origin_x;
    unsigned char origin_y;
};

/* Raw MAP_CHANGE payload, refreshed each time rt_apply returns
 * RTS_MAP_CHANGE. The server sends this when the player steps onto a map
 * transition (cave entrance/exit); it then streams the new map's terrain as
 * a full WINDOW_ROW fill on the same connection. */
struct rt_map_change {
    unsigned char map_id;
    unsigned char spawn_x;
    unsigned char spawn_y;
    unsigned char tileset_id;
    unsigned char palette_id;
    unsigned char flags;
};

/* One display page of dialogue, reassembled from its chunks. */
struct rt_dialogue {
    unsigned char id;
    unsigned char speaker;
    unsigned char page_index;
    unsigned char page_count;
    /* Committed only by the chunk carrying CHUNK_END -- see
     * apply_dialogue_page for why anything else freezes a quest turn-in. */
    unsigned char flags;
    /* The chunk_index we expect next; anything else is a gap. */
    unsigned char next_chunk;
    unsigned char len;
    /* A complete page is ready to render. The modal clears it. */
    unsigned char dirty;
    /* The modal should open. main.c clears it when it does. */
    unsigned char request;
    /* Set by the modal loop while it owns the screen. */
    unsigned char active;
    char text[RTS_DLG_PAGE_MAX + 1];
};

struct rt_state {
    unsigned char world_seen;
    unsigned char player_x;
    unsigned char player_y;
    unsigned char health;
    unsigned char correction_flags;
    unsigned last_server_seq;
    unsigned echo_client_seq;
    unsigned char beaver_count;
    struct rt_beaver beavers[RTS_MAX_BEAVERS];
    unsigned char remote_count;
    struct rt_remote_player remotes[RTS_MAX_REMOTE_PLAYERS];
    unsigned char item_count;
    struct rt_item items[RTS_MAX_ITEMS];
    struct rt_tracer tracers[RTS_MAX_TRACERS];
    unsigned char tracer_next;
    /* Per-slot baseline of the remote fire bits so a change can be detected.
     * Indexed like remotes[]; the slot's occupant can shift as the server
     * re-sorts by distance, which at worst drops or doubles a cosmetic tracer. */
    unsigned char remote_prev_fire[RTS_MAX_REMOTE_PLAYERS];
    unsigned char hud_seen;
    unsigned char hud_hp;
    unsigned char hud_max_hp;
    unsigned char hud_level;
    unsigned hud_gold;
    unsigned char hud_pvp_enabled;
    unsigned hud_pvp_kills;
    unsigned char message_len;
    unsigned char message_dirty;
    /* A MESSAGE has been received. message_id 0 (server MSG_NONE) is a
     * perfectly valid "just show this text" message -- bat attacks, kills and
     * Gorvak's lines all use it -- so presence must never be inferred from the
     * id. The Atari client shipped that bug and needed this same flag. */
    unsigned char message_seen;
    /* The server's MSG_* id for the message above (server/quests.py). Kept
     * only so a sound can be chosen for it; the HUD shows the text. */
    unsigned char message_id;
    unsigned char quest_seen;
    /* 0 means no active quest, which happens mid-campaign once a chain
     * completes; the HUD line must clear rather than keep the last text. */
    unsigned char quest_id;
    unsigned char quest_state;
    unsigned char quest_len;
    unsigned char quest_dirty;
    char quest_text[RTS_TEXT_MAX + 1];
    /* Set when a WORLD_STATE actually changed a terrain cell (a chopped
     * tree, a taken item). Lets the renderer skip a full repaint when
     * nothing under the viewport moved. The caller clears it. */
    unsigned char tile_changed;
    char message[RTS_TEXT_MAX + 1];
    struct rt_terrain_edge edge;
    struct rt_window_row window_row;
    struct rt_window_commit_ack window_commit_ack;
    struct rt_map_change map_change;
    struct rt_dialogue dlg;
};

unsigned rt_crc16(const unsigned char *data, unsigned char len);
unsigned char rt_cobs_decode(const unsigned char *in, unsigned char in_len,
                             unsigned char *out);
unsigned char rt_cobs_encode(const unsigned char *in, unsigned char in_len,
                             unsigned char *out);

void rt_state_init(struct rt_state *state);

/* Which sprite an item drop uses (RTS_ART_ITEM_*). Item id 0 draws nothing;
 * any other unrecognised id falls back to sticks, matching the Atari client so
 * a new server item is visible on both before either has real art. */
unsigned char rt_item_art_index(unsigned char item_id);

/* Seed a new shot at (x, y) travelling in dir (RTS_FACE_*), round-robin over
 * the tracer slots. Advancing and collision are the caller's job (they need
 * the live terrain and world), see update_tracers in main.c. */
void rt_spawn_tracer(struct rt_state *state, unsigned char x, unsigned char y,
                     unsigned char dir);

/* Validate a COBS-decoded raw frame and fold it into the state. terrain may
 * be NULL; when given, WORLD_STATE tile updates inside the window are
 * applied to the 32x24 buffer. Returns the applied frame type, 0 if the
 * frame was invalid or an ignored type. */
unsigned char rt_apply(struct rt_state *state, unsigned char *terrain,
                       unsigned origin_x, unsigned origin_y,
                       const unsigned char *raw, unsigned char raw_len);

/* Build outgoing wire frames (COBS + delimiter) into out; returns length.
 * out must hold at least RTS_MAX_RAW + 2 bytes. */
unsigned char rt_build_auth(unsigned char *out, unsigned long token);
unsigned char rt_build_player_state(unsigned char *out, unsigned seq,
                                    unsigned char x, unsigned char y,
                                    unsigned char facing,
                                    unsigned char buttons,
                                    unsigned char fire_counter,
                                    unsigned char pickup_counter,
                                    unsigned last_server_seq,
                                    unsigned char pvp_toggle_counter);

/* rows_have is the 24-bit WINDOW_ROW-received bitmap for an in-progress
 * fill; pass 0 to request a fresh full 24-row fill. */
unsigned char rt_build_resync_request(unsigned char *out, unsigned seq,
                                      unsigned char origin_x,
                                      unsigned char origin_y,
                                      unsigned char fill_origin_x,
                                      unsigned char fill_origin_y,
                                      unsigned long rows_have,
                                      unsigned char fill_id,
                                      unsigned char flags);
unsigned char rt_build_cache_step_ack(unsigned char *out, unsigned seq,
                                      unsigned revision,
                                      unsigned char origin_x,
                                      unsigned char origin_y);
unsigned char rt_build_window_commit(unsigned char *out, unsigned seq,
                                     unsigned char fill_id,
                                     unsigned char origin_x,
                                     unsigned char origin_y,
                                     unsigned char map_id,
                                     unsigned char flags);
unsigned char rt_build_map_ready(unsigned char *out, unsigned seq,
                                 unsigned char map_id,
                                 unsigned char origin_x,
                                 unsigned char origin_y);

/* Camera origin (in window tiles) that keeps pos centered, clamped. */
unsigned char rt_camera(unsigned char pos, unsigned char span,
                        unsigned char view);

/* Hysteretic camera: leaves cam alone while pos stays inside the band
 * [cam+margin, cam+view-1-margin], and otherwise moves it the least amount
 * that brings pos back inside. Result is clamped to [0, span-view].
 *
 * A camera that does not move needs no terrain repaint, only the cells the
 * entities were on, so local movement (fighting, turning, backtracking) stops
 * scrolling the whole viewport every step. It does NOT help a straight walk:
 * once pos is against the band edge, every further step pushes the camera. */
unsigned char rt_camera_track(unsigned char cam, unsigned char pos,
                              unsigned char span, unsigned char view,
                              unsigned char margin);

#endif
