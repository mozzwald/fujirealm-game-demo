; blit.s -- fast 8x8 4bpp terrain-tile copy into the strided framebuffer.
;
; The C version of this copy compiled to ~59 cycles/byte under cc65, which is
; why the CPU blitter barely beat Suzy. This does the same 32-byte copy in
; tight assembly: 8 scanlines of 4 bytes, source contiguous, destination
; advancing by one framebuffer row (80 bytes) between scanlines.
;
; C interface (see render.c):
;   extern unsigned char *blit_src;   // tile's raw 32 bytes (contiguous)
;   extern unsigned char *blit_dst;   // top-left byte of the cell
;   extern void blit_tile_asm(void);  // copies blit_src -> blit_dst
;
; Pointers are passed through globals rather than the C argument stack so the
; per-tile call is a plain jsr with no stack juggling. ptr1/ptr2 are the cc65
; runtime's zero-page scratch, free to use inside a leaf routine.

        .export         _blit_tile_asm
        .import          _blit_src, _blit_dst
        .importzp       ptr1, ptr2

FB_STRIDE = 80                  ; bytes per framebuffer scanline (160px * 4bpp)

        .segment        "CODE"

_blit_tile_asm:
        lda     _blit_src
        sta     ptr1
        lda     _blit_src+1
        sta     ptr1+1
        lda     _blit_dst
        sta     ptr2
        lda     _blit_dst+1
        sta     ptr2+1

        ldx     #8              ; 8 scanlines
@row:
        ldy     #3              ; 4 bytes, high to low
        lda     (ptr1),y
        sta     (ptr2),y
        dey
        lda     (ptr1),y
        sta     (ptr2),y
        dey
        lda     (ptr1),y
        sta     (ptr2),y
        dey
        lda     (ptr1),y
        sta     (ptr2),y

        lda     ptr1            ; src += 4 (next scanline is contiguous)
        clc
        adc     #4
        sta     ptr1
        bcc     @src_ok
        inc     ptr1+1
@src_ok:
        lda     ptr2            ; dst += 80 (next framebuffer scanline)
        clc
        adc     #FB_STRIDE
        sta     ptr2
        bcc     @dst_ok
        inc     ptr2+1
@dst_ok:
        dex
        bne     @row
        rts
