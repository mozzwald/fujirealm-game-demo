#include "sound.h"
#include "gime.h"
#include <cmoc.h>

/* tools/sound_gen.py's segments (format there) and each effect's offset. */
extern const unsigned char sound_segs[];
extern const unsigned sound_start[];

/* One voice, so a new effect replaces one of lower or equal priority. */
static const unsigned char priority[SND_COUNT] = { 0, 1, 2, 4, 2, 3 };

unsigned char sound_on = 1;

/* The segment playing, as the FIRQ handler steps it. */
static const unsigned char *snd_seg;
static unsigned snd_count;      /* timer count: a half cycle, or a noise step */
static int snd_dcount;          /* added each glide step */
static unsigned char snd_vol;   /* DAC level, as $FF20 bits 7-2 */
static unsigned char snd_dvol;
static unsigned char snd_ticks; /* glide steps left */
static unsigned char snd_flags;
static unsigned char snd_div;   /* FIRQs per half cycle */
static unsigned char snd_divcnt;
static unsigned char snd_phase; /* $FF in a tone's high half */
static unsigned snd_lfsr;
static unsigned snd_acc;        /* timer counts toward the next glide step */
static unsigned char snd_prio;  /* 0: silent */
static unsigned char saved_firq[3];
static unsigned char snd_ready = 0; /* read before sound_init() can run */

void sound_init(void)
{
    INTS_OFF();
    memcpy(saved_firq, (void *)0xFEF4, 3);
    snd_ready = 1;
    snd_prio = 0;
    *(unsigned char *)0xFF90 = 0x5C;  /* INIT0 $4C plus FEN */
    *(unsigned char *)0xFF91 = 0x20;  /* task 0; timer counts at 3.58 MHz */
    *(unsigned char *)0xFF01 &= 0xF7; /* sound mux: the DAC */
    *(unsigned char *)0xFF03 &= 0xF7;
    *(unsigned char *)0xFF23 |= 0x08; /* sound on */
    asm {
        leax snd_firq,pcr
        stx $FEF5
        lda #$7E
        sta $FEF4
        lbra snd_init_done

; Starts segment X, or ends the effect at its 0-step terminator.
snd_load
        lda 6,x
        beq snd_load_end
        stx :snd_seg
        ldd ,x
        std :snd_count
        stb $FF95
        sta $FF94
        ldd 2,x
        std :snd_dcount
        lda 4,x
        sta :snd_vol
        lda 5,x
        sta :snd_dvol
        lda 6,x
        sta :snd_ticks
        lda 7,x
        sta :snd_flags
        anda #$30
        lsra
        lsra
        lsra
        lsra
        ldb #1
snd_div_loop
        tsta
        beq snd_div_done
        lslb
        deca
        bra snd_div_loop
snd_div_done
        stb :snd_div
        stb :snd_divcnt
        rts
snd_load_end
        clr $FF93
        clr $FF94
        clr $FF95
        lda $FF20
        anda #3
        sta $FF20
        clr :snd_prio
        rts

; FIRQ stacks only PC and CC.
snd_firq
        pshs a,b,x
        lda $FF93
        lda :snd_flags
        lsra
        bcs snd_noise
        dec :snd_divcnt
        bne snd_tone_out
        lda :snd_div
        sta :snd_divcnt
        com :snd_phase
snd_tone_out
        lda :snd_vol
        anda :snd_phase
        bra snd_out
; 16-bit Galois shift register, taps $B400; its output bit picks the level.
snd_noise
        ldd :snd_lfsr
        lsra
        rorb
        bcc snd_noise_low
        eora #$B4
        std :snd_lfsr
        lda :snd_vol
        bra snd_out
snd_noise_low
        std :snd_lfsr
        clra
; Bits 1-0 of $FF20 are the RS-232 out and cassette lines: keep them.
snd_out
        anda #$FC
        ldb $FF20
        andb #3
        pshs b
        ora ,s+
        sta $FF20
        ldd :snd_acc
        addd :snd_count
        cmpa #$80
        blo snd_no_step
        anda #$7F
        std :snd_acc
        lda :snd_vol
        adda :snd_dvol
        sta :snd_vol
        ldd :snd_count
        addd :snd_dcount
        std :snd_count
        stb $FF95
        sta $FF94
        dec :snd_ticks
        bne snd_ret
        ldx :snd_seg
        leax 8,x
        lbsr snd_load
        bra snd_ret
snd_no_step
        std :snd_acc
snd_ret
        puls a,b,x
        rti

snd_init_done
    }
    INTS_RESTORE();
}

void sound_play(unsigned char id)
{
    const unsigned char *s;

    if (!sound_on || id == 0 || id >= SND_COUNT ||
        priority[id] < snd_prio) {
        return;
    }
    s = &sound_segs[sound_start[id]];
    INTS_OFF();
    snd_prio = priority[id];
    snd_acc = 0;
    snd_phase = 0;
    snd_lfsr = 1;
    *(unsigned char *)0xFF93 = 0x20; /* timer FIRQ */
    asm {
        ldx :s
        jsr snd_load
    }
    INTS_RESTORE();
}

void sound_shutdown(void)
{
    if (!snd_ready) {
        return;
    }
    snd_ready = 0;
    INTS_OFF();
    *(unsigned char *)0xFF93 = 0;
    *(unsigned char *)0xFF94 = 0;
    *(unsigned char *)0xFF95 = 0;
    *(unsigned char *)0xFF20 &= 0x03;
    memcpy((void *)0xFEF4, saved_firq, 3);
    snd_prio = 0;
    INTS_RESTORE();
}
