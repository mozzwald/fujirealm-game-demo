#ifndef SOUND_H
#define SOUND_H

/* The game's five sound events (the Atari client's), on one voice: the GIME
 * timer raises a FIRQ that drives the 6-bit DAC and glides each effect's
 * pitch and volume itself. The effects are in tools/sound_gen.py. */
#define SND_SHOOT 1
#define SND_HURT 2
#define SND_DEATH 3
#define SND_KILL 4
#define SND_LEVELUP 5
#define SND_COUNT 6

/* 0 silences sound_play(). */
extern unsigned char sound_on;

/* Installs the FIRQ handler and routes the DAC to the speaker. Writes $FF90
 * as $5C, so only for modes that use $4C (graphics, WIDTH 40/80). */
void sound_init(void);

/* Starts effect id unless one of higher priority is playing. */
void sound_play(unsigned char id);

/* Stops any effect and puts BASIC's FIRQ handler back; no-op before
 * sound_init(). */
void sound_shutdown(void);

#endif
