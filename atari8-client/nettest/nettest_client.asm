; ============================================================================
; nettest_client.asm -- standalone FujiNet Netstream serial-integrity tester
;
; Purpose: measure raw byte corruption on the FujiNet<->Atari POKEY serial
; link, isolated from all game/protocol code, using the SAME bundled Netstream
; handler the game uses. Pairs with tools/serial_test_server.py.
;
; The server streams a constant byte ($AA) downstream; this client verifies
; each received byte against it -- the on-screen RX ERR is the POKEY RECEIVE
; path corruption. It streams the same constant upstream, which the server
; verifies to measure the POKEY TRANSMIT path. Full-duplex needs exactly one
; direction externally clocked, so the default mode ($07) uses internal-async
; RX (clean downlink) and EXTERNAL-clock TX, making the server's uplink error
; rate isolate the TX-external loss the game sees. SELECT swaps which direction
; is external ($07<->$0B); baud is the NET_BAUD constant (rebuild to change).
;
; On-screen (OS GR.0 text): RX errors, framing-status hits, overrun hits,
; XOR-of-flipped-bits, RX kilobytes, and the active flags/AUDF3/pattern.
; Console keys: OPTION = exit (cold start), SELECT = swap RX/TX external clock.
;
; Built to $2000 and combined with NSENGINE.OBX at $9000 (see Makefile).
; ============================================================================

; ---- OS / hardware ----
RTCLOK   = $14          ; low byte ticks every VBI (~1/60 s NTSC)
SAVMSC   = $58          ; pointer to GR.0 screen RAM
CONSOL   = $D01F        ; console keys (bit1 SELECT, bit2 OPTION; 0=pressed)
COLDSV   = $E477        ; cold start vector

; ---- Netstream handler ABI (base $9000) ----
NS_BASE          = $9000
NS_BEGIN_STREAM  = NS_BASE+0
NS_END_STREAM    = NS_BASE+3
NS_SEND_BYTE     = NS_BASE+12
NS_RECV_BYTE     = NS_BASE+15
NS_BYTES_AVAIL   = NS_BASE+18
NS_GET_STATUS    = NS_BASE+21
NS_INIT          = NS_BASE+27
NS_GET_FINAL_FLAGS = NS_BASE+30
NS_GET_FINAL_AUDF3 = NS_BASE+33

; ---- config ----
NET_BAUD         = 31250            ; nominal; handler maps to AUDF3
; Clock modes. Full-duplex needs exactly one direction externally clocked
; (both-internal $03 breaks TX -- POKEY has a single internal serial clock).
; $07 = RX internal async + TX EXTERNAL clock: matches the game and puts the
; external clock on the UPLINK, so the server's uplink error rate measures the
; TX-external loss. $0B = RX external + TX internal (downlink external).
; SELECT swaps which direction is externally clocked ($07 <-> $0B).
NET_FLAGS_RXINT  = $07             ; RX internal, TX external (default)
NET_FLAGS_RXEXT  = $0B             ; RX external, TX internal
PORT_SWAPPED     = $2823           ; 9000, network byte order
; Constant test byte, both directions. Drop/insert-immune corruption metric:
; every received byte must equal NET_PATTERN, so a lost byte does not desync
; the count (unlike a rolling counter). $AA = 10101010, every bit toggles --
; worst case for slow edges / clock skew. Rebuild with $55, $00, $FF to
; compare transition sensitivity. The server must run with a matching
; --pattern.
NET_PATTERN      = $AA

C_SP     = $82          ; handler reads init args via (C_SP)

; ---- zero page working vars ($CB..$DF are free under OS w/o BASIC) ----
zp       = $CB
scrptr   = zp+0         ; 2  screen write pointer
srcptr   = zp+2         ; 2  string source pointer
tmp      = zp+4         ; 1
tmp2     = zp+5         ; 1

        org $2000

start
        jsr init_screen
        lda #NET_FLAGS_RXINT
        sta cur_flags
restart
        jsr clear_screen
        jsr draw_labels
        jsr reset_counters
        jsr connect
        bcc run_loop
        ; connect failed: show message and wait for OPTION (exit).
        lda #14
        jsr row_ptr
        lda #<fail_msg
        sta srcptr
        lda #>fail_msg
        sta srcptr+1
        jsr print_str
fail_wait
        jsr poll_console
        jmp fail_wait

; ---------------------------------------------------------------------------
run_loop
; Drain the receive ring (bounded so display/keys stay responsive), verify
; each byte, then transmit upstream, poll status, and redraw throttled.
        lda #0
        sta rx_budget          ; per-pass RX budget (wraps at 256)
rx_drain
        jsr NS_BYTES_AVAIL     ; returns count lo in A, hi in X (clobbers X)
        sta tmp
        cpx #0
        bne rx_have
        lda tmp
        beq rx_done
rx_have
        ; BYTES_AVAIL already confirmed >=1 byte; NS_RecvByte restores entry
        ; flags via PLP so its carry is unreliable -- trust A, not carry.
        jsr NS_RECV_BYTE       ; byte -> A
        jsr verify_rx
        inc rx_budget
        lda rx_budget
        cmp #0                 ; wrap at 256 -> one pass chunk
        bne rx_drain
rx_done
        jsr tx_burst
        jsr poll_status
        jsr maybe_redraw
        jsr poll_console
        jmp run_loop

; ---------------------------------------------------------------------------
; verify_rx: A = received byte. It must equal NET_PATTERN; a miss is one
; corruption event (drop/insert-immune, since the expectation is constant).
verify_rx
        cmp #NET_PATTERN
        beq vr_ok
        eor #NET_PATTERN       ; A = recv ^ pattern (which bits flipped)
        ora rx_xor
        sta rx_xor
        inc rx_err
        bne vr_ok
        inc rx_err+1
vr_ok
        ; rx_total (24-bit) ++
        inc rx_total
        bne vr_done
        inc rx_total+1
        bne vr_done
        inc rx_total+2
vr_done
        rts

; ---------------------------------------------------------------------------
; tx_burst: send up to 128 upstream NET_PATTERN bytes (stop early if ring full).
tx_burst
        lda #128
        sta tmp
tx_loop
        lda #NET_PATTERN
        jsr NS_SEND_BYTE       ; A=0 ok, nonzero = busy/full
        cmp #0
        bne tx_done
        dec tmp
        bne tx_loop
tx_done
        rts

; ---------------------------------------------------------------------------
; poll_status: sample the sticky handler status (~every 8 ticks). Bit7=POKEY
; framing error, bit6=input overrun, bit4=ring overflow. Sticky+clear-on-read,
; so these are "intervals with >=1 event", a sampled lower bound.
poll_status
        lda RTCLOK
        and #$07
        bne ps_done
        jsr NS_GET_STATUS
        sta tmp
        and #$80
        beq ps_no_frame
        inc st_frame
        bne ps_ovr
        inc st_frame+1
ps_ovr
        lda tmp
        and #$50               ; bit6 overrun | bit4 overflow
        beq ps_done
        inc st_over
        bne ps_done
        inc st_over+1
ps_no_frame
ps_done
        rts

; ---------------------------------------------------------------------------
; maybe_redraw: refresh the numbers ~4x/second.
maybe_redraw
        lda RTCLOK
        sec
        sbc last_draw
        cmp #15
        bcc mr_done
        lda RTCLOK
        sta last_draw
        jsr draw_values
mr_done
        rts

; ---------------------------------------------------------------------------
; poll_console: OPTION -> cold start; SELECT -> toggle RX clock flag + restart.
poll_console
        lda CONSOL
        and #$04
        bne pc_check_select
        jsr NS_END_STREAM
        jmp COLDSV
pc_check_select
        lda CONSOL
        and #$02
        bne pc_done
        ; debounce release
pc_sel_rel
        lda CONSOL
        and #$02
        beq pc_sel_rel
        lda cur_flags
        eor #$0c               ; swap which direction is external ($07<->$0B)
        sta cur_flags
        jsr NS_END_STREAM
        jmp restart
pc_done
        rts

; ---------------------------------------------------------------------------
; connect: point C_SP at the arg block (with current flags), INIT, BEGIN,
; settle ~30 frames. Carry set on INIT failure.
connect
        lda cur_flags
        sta ns_args+2
        lda #<ns_args
        sta C_SP
        lda #>ns_args
        sta C_SP+1
        lda #<PORT_SWAPPED
        ldx #>PORT_SWAPPED
        jsr NS_INIT
        cmp #0
        beq cn_ok
        sec
        rts
cn_ok
        jsr NS_BEGIN_STREAM
        lda #30
        sta tmp
cn_settle
        jsr wait_vbi
        dec tmp
        bne cn_settle
        jsr NS_GET_FINAL_FLAGS
        sta final_flags
        jsr NS_GET_FINAL_AUDF3
        sta final_audf3
        clc
        rts

wait_vbi
        lda RTCLOK
wv1     cmp RTCLOK
        beq wv1
        rts

; ---------------------------------------------------------------------------
reset_counters
        ldx #0
        lda #0
rc_loop
        sta counter_block,x
        inx
        cpx #counter_block_len
        bne rc_loop
        rts

; ---------------------------------------------------------------------------
; screen helpers (OS GR.0, 40 cols; screen memory uses internal codes).
init_screen
        rts

clear_screen
        lda SAVMSC
        sta scrptr
        lda SAVMSC+1
        sta scrptr+1
        ldy #0
        ldx #4                 ; ~960 bytes (24*40)
        lda #0
cs_loop
        sta (scrptr),y
        iny
        bne cs_loop
        inc scrptr+1
        dex
        bne cs_loop
        rts

; set scrptr = SAVMSC + A*40  (A = row)
row_ptr
        sta tmp
        lda SAVMSC
        sta scrptr
        lda SAVMSC+1
        sta scrptr+1
        ldx tmp
        beq rp_done
rp_add
        clc
        lda scrptr
        adc #40
        sta scrptr
        bcc rp_nc
        inc scrptr+1
rp_nc   dex
        bne rp_add
rp_done rts

; print a string (srcptr) at current scrptr. MADS stores dta "..." as Atari
; internal/screen codes already, so write bytes directly. Internal space is
; $00, so the terminator is $FF (never appears in our uppercase/punct text).
print_str
        ldy #0
ps_loop
        lda (srcptr),y
        cmp #$ff
        beq ps_end
        sta (scrptr),y
        iny
        bne ps_loop
ps_end
        rts

; print A as two hex digits at scrptr+X
print_hex
        pha
        lsr
        lsr
        lsr
        lsr
        jsr hex_nib
        pla
        and #$0f
hex_nib
        cmp #10
        bcc hn_dig
        clc
        adc #$17               ; A-F (10..15) -> internal $21..$26
        bne hn_put
hn_dig
        clc
        adc #$10               ; 0-9 -> internal $10..$19
hn_put
        sta (scrptr),y
        iny
        rts

; ---------------------------------------------------------------------------
draw_labels
        lda #1
        jsr row_ptr
        lda #<t_title
        sta srcptr
        lda #>t_title
        sta srcptr+1
        jsr print_str
        lda #4
        jsr row_ptr
        lda #<t_rxerr
        sta srcptr
        lda #>t_rxerr
        sta srcptr+1
        jsr print_str
        lda #5
        jsr row_ptr
        lda #<t_frame
        sta srcptr
        lda #>t_frame
        sta srcptr+1
        jsr print_str
        lda #6
        jsr row_ptr
        lda #<t_over
        sta srcptr
        lda #>t_over
        sta srcptr+1
        jsr print_str
        lda #7
        jsr row_ptr
        lda #<t_xor
        sta srcptr
        lda #>t_xor
        sta srcptr+1
        jsr print_str
        lda #8
        jsr row_ptr
        lda #<t_rxkb
        sta srcptr
        lda #>t_rxkb
        sta srcptr+1
        jsr print_str
        lda #10
        jsr row_ptr
        lda #<t_mode
        sta srcptr
        lda #>t_mode
        sta srcptr+1
        jsr print_str
        lda #12
        jsr row_ptr
        lda #<t_keys
        sta srcptr
        lda #>t_keys
        sta srcptr+1
        jsr print_str
        rts

; draw the numeric values at column 10 of their rows (Y=10 offset)
draw_values
        lda #4
        jsr row_ptr
        ldy #10
        lda rx_err+1
        jsr print_hex
        lda rx_err
        jsr print_hex
        lda #5
        jsr row_ptr
        ldy #10
        lda st_frame+1
        jsr print_hex
        lda st_frame
        jsr print_hex
        lda #6
        jsr row_ptr
        ldy #10
        lda st_over+1
        jsr print_hex
        lda st_over
        jsr print_hex
        lda #7
        jsr row_ptr
        ldy #10
        lda rx_xor
        jsr print_hex
        lda #8
        jsr row_ptr
        ldy #10
        lda rx_total+2         ; high byte ~= units of 64 KB
        jsr print_hex
        lda rx_total+1         ; ~= units of 256 B
        jsr print_hex
        lda #10
        jsr row_ptr
        ldy #10
        lda final_flags
        jsr print_hex
        iny
        lda final_audf3
        jsr print_hex
        iny
        lda #NET_PATTERN
        jsr print_hex
        rts

; ---------------------------------------------------------------------------
; data
cur_flags   dta NET_FLAGS_RXINT
final_flags dta 0
final_audf3 dta 0
rx_budget   dta 0
last_draw   dta 0

; init arg block: baud lo/hi, flags, host ptr lo/hi
ns_args
        dta <NET_BAUD,>NET_BAUD, NET_FLAGS_RXINT, <host_str,>host_str

host_str
        icl "../generated/server_host_default.inc"
        dta 0

t_title dta "NETSTREAM SERIAL TEST",$ff
t_rxerr dta "RX ERR  :",$ff
t_frame dta "RX FRAME:",$ff
t_over  dta "RX OVER :",$ff
t_xor   dta "XOR BITS:",$ff
t_rxkb  dta "RX x256B:",$ff
t_mode  dta "FL/A3/PAT:",$ff
t_keys  dta "OPTION=EXIT SELECT=CLKTOG",$ff
fail_msg dta "NETSTREAM INIT FAILED - OPTION",$ff

; ---- counters (cleared each run) ----
counter_block
rx_expected dta 0
rx_seeded   dta 0
tx_next     dta 0
rx_err      dta 0,0
rx_total    dta 0,0,0
rx_xor      dta 0
st_frame    dta 0,0
st_over     dta 0,0
counter_block_len = *-counter_block

        run start
