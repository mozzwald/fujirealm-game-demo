#include <lynx.h>

#include "sfx.h"

/* Tables are in play order, one row of SFX_STEPS per effect id.
 *
 * The pitch column is Mikey's timer reload: with the 8us clock selected in
 * sfx_init, the channel toggles every (reload + 1) * 8us, so the tone is
 * 62500 / (reload + 1) Hz -- 10 is about 5.7 kHz, 200 about 310 Hz. The
 * Atari client's AUDF values are divisors too, so its effect shapes carry
 * over directly; its tables are stored backwards and played high index to
 * low, which is why these look reversed next to fujirealm.asm.
 *
 * The volume column is a plain amplitude, unlike POKEY's packed
 * distortion/volume byte: each entry is the Atari's volume nibble times 8.
 *
 * None of this has been heard on hardware -- there is no Lynx emulator -- so
 * treat the numbers as a starting point for a tuning pass, not as final. */
static const unsigned char sfx_pitch[(SFX_COUNT - 1) * SFX_STEPS] = {
    10, 16, 24, 32, 40, 0, 0, 0,                   /* SFX_SHOOT */
    200, 180, 160, 140, 0, 0, 0, 0,                /* SFX_HURT */
    20, 30, 40, 50, 60, 70, 80, 90,                /* SFX_DEATH */
    30, 40, 50, 60, 0, 0, 0, 0,                    /* SFX_KILL */
    0x23, 0x23, 0x1D, 0x1D, 0x1D, 0x17, 0x17, 0x17 /* SFX_LEVELUP */
};

static const unsigned char sfx_vol[(SFX_COUNT - 1) * SFX_STEPS] = {
    64, 64, 48, 32, 16, 0, 0, 0,
    112, 96, 64, 32, 0, 0, 0, 0,
    112, 112, 96, 80, 64, 48, 32, 16,
    112, 96, 64, 32, 0, 0, 0, 0,
    64, 64, 64, 64, 64, 64, 64, 64
};

/* Indexed straight by the server's MSG_* id (server/quests.py); anything not
 * listed, including id 0, is silent. Same choices the Atari client's
 * sfx_message_map makes, extended over the ids added since: it stops at 21,
 * so PVP_KILL had no sound there. Damage is not in here -- a bite arrives as
 * a message, but the reliable signal is the health drop in WORLD_STATE, which
 * is where both clients trigger SFX_HURT. */
static const unsigned char sfx_message_map[26] = {
    SFX_NONE,    /*  0 MSG_NONE */
    SFX_NONE,    /*  1 MSG_QUEST_STARTED */
    SFX_NONE,    /*  2 MSG_QUEST_PROGRESS */
    SFX_NONE,    /*  3 MSG_QUEST_READY */
    SFX_NONE,    /*  4 MSG_QUEST_COMPLETE */
    SFX_KILL,    /*  5 MSG_BEAVER_KILLED */
    SFX_NONE,    /*  6 MSG_GOT_STICKS */
    SFX_NONE,    /*  7 MSG_BEAVER_BITES */
    SFX_NONE,    /*  8 MSG_QUEST_REMINDER */
    SFX_NONE,    /*  9 MSG_FARMER_THANKS */
    SFX_LEVELUP, /* 10 MSG_LEVEL_UP */
    SFX_DEATH,   /* 11 MSG_PLAYER_DIED */
    SFX_DEATH,   /* 12 MSG_RESPAWN_GRAVE */
    SFX_DEATH,   /* 13 MSG_RESPAWN_CAVE */
    SFX_NONE,    /* 14 MSG_GOT_GOLD */
    SFX_KILL,    /* 15 MSG_GOBLIN_KILLED */
    SFX_NONE,    /* 16 MSG_GOBLIN_BITES */
    SFX_NONE,    /* 17 MSG_QUEST_OFFER */
    SFX_NONE,    /* 18 MSG_WELCOME_NEW */
    SFX_NONE,    /* 19 MSG_WELCOME_BACK */
    SFX_NONE,    /* 20 MSG_GOBLIN_THANKS */
    SFX_NONE,    /* 21 MSG_PVP_HIT */
    SFX_NONE,    /* 22 MSG_PLAYER_ENTERED */
    SFX_NONE,    /* 23 MSG_PLAYER_LEFT */
    SFX_KILL,    /* 24 MSG_PVP_KILL */
    SFX_NONE     /* 25 MSG_PVP_ARENA_LOCKED */
};

unsigned char sfx_at;
unsigned char sfx_end;

void sfx_init(void)
{
    /* Tap 0 alone makes the shift register alternate, i.e. a square wave
       rather than the noise the wider taps give. The register has to be
       seeded: with every tap fed from zeros it can sit at zero and never
       toggle, which is silence that looks like broken wiring. */
    MIKEY.channel_a.feedback = 0x01;
    MIKEY.channel_a.other = 0x00;
    MIKEY.channel_a.shiftlo = 0x01;
    /* Enable count + reload from backup, 8us clock. */
    MIKEY.channel_a.control = 0x1B;
    MIKEY.channel_a.volume = 0;
    /* Bits here *disable* a channel per side, and their power-on state is not
       guaranteed; clearing them is what actually lets the speaker hear this. */
    MIKEY.mstereo = 0;
    sfx_at = 0;
    sfx_end = 0;
}

void sfx_play(unsigned char id)
{
    if (id == SFX_NONE || id >= SFX_COUNT) {
        return;
    }
    /* Rows are indexed from id 1: SFX_NONE never plays, so giving it a row of
       zeros would be 16 bytes of table that is only ever skipped. */
    sfx_at = (unsigned char)((id - 1) * SFX_STEPS);
    sfx_end = (unsigned char)(sfx_at + SFX_STEPS);
}

void sfx_step(void)
{
    unsigned char vol;

    /* sfx_end 0 is the idle state, and no playing effect can have it: an
       effect's end is always at least one whole row in. The distinction
       matters -- running out of steps and being silent are a frame apart, and
       collapsing them leaves the last tone sounding forever. */
    if (sfx_end == 0) {
        return;
    }
    vol = sfx_at != sfx_end ? sfx_vol[sfx_at] : 0;
    if (vol == 0) {
        /* Out of steps, or into the zero padding that ends a short row. */
        MIKEY.channel_a.volume = 0;
        sfx_end = 0;
        return;
    }
    MIKEY.channel_a.reload = sfx_pitch[sfx_at];
    MIKEY.channel_a.volume = vol;
    ++sfx_at;
}

void sfx_for_message(unsigned char message_id)
{
    if (message_id < sizeof(sfx_message_map)) {
        sfx_play(sfx_message_map[message_id]);
    }
}
