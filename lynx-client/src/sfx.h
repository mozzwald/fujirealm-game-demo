#ifndef FUJIREALM_SFX_H
#define FUJIREALM_SFX_H

/* Sound effects, mirroring the Atari client's five (fujirealm.asm sfx_update /
 * sfx_request) so the two clients say the same things at the same moments.
 *
 * That client runs two POKEY channels with priority arbitration and a pointer
 * table per effect. This one runs a single Mikey channel over flat, fixed-
 * stride tables, because the pointer indirection alone costs ~450 bytes of
 * cc65 codegen and MAIN does not have it. A new effect simply replaces
 * whatever is playing, which for effects this short is inaudible.
 */

#define SFX_NONE 0
#define SFX_SHOOT 1
#define SFX_HURT 2
#define SFX_DEATH 3
#define SFX_KILL 4
#define SFX_LEVELUP 5
#define SFX_COUNT 6

/* Frames per effect. Fixed so the tables can be indexed as id * SFX_STEPS
 * with no per-effect length or pointer; shorter effects pad with a zero
 * volume, which ends them early. */
#define SFX_STEPS 8

/* Set up the channel and silence it. Call once, before the game loop. */
void sfx_init(void);

/* Start an effect. SFX_NONE and out-of-range ids are silent, so a table
 * lookup can be passed straight in. */
void sfx_play(unsigned char id);

/* Advance one step. Call exactly once per rendered frame. */
void sfx_step(void);

/* Play whatever the server's MESSAGE id maps to (server/quests.py MSG_*). */
void sfx_for_message(unsigned char message_id);

/* Where the playhead is, and where the effect ends; sfx_end 0 means idle.
 * Exposed as a test seam -- the schedule is host-testable even though the
 * register pokes are not. */
extern unsigned char sfx_at;
extern unsigned char sfx_end;

#endif
