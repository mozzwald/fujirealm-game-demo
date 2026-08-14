' bootstrap.bas -- the $BF-framed phase: HELLO -> WELCOME + 8 WINDOW chunks.
' Port of lynx-client/src/bootstrap.c's parser and window assembly.
'
' Frame: BF 01 type len payload... sum8 (checksum = low byte of the sum of
' all preceding bytes). The same parser also serves the login server's
' LOGIN_RESPONSE (login.bas drives bf_feed on the :9010 socket).
'
' A re-sent HELLO makes the server restart the bootstrap with a NEW tick:
' a tick/origin change discards partial rows and starts over.


' ---------------------------------------------------------------------------
' bf_feed: one stream byte (in bf_b) through the frame collector.
' ---------------------------------------------------------------------------
bf_feed: PROCEDURE
    IF bf_len = 0 THEN
        IF bf_b <> PKT_MAGIC THEN RETURN
    ELSEIF bf_len = 1 THEN
        IF bf_b <> PKT_VER THEN
            bf_len = 0
            RETURN
        END IF
    END IF
    POKE BFACC + bf_len, bf_b
    bf_len = bf_len + 1
    IF bf_len = 4 THEN
        bf_want = bf_b + 5
    END IF
    IF bf_len >= 5 THEN
        IF bf_len = bf_want THEN
            GOSUB bf_packet
            bf_len = 0
        END IF
    END IF
END

' ---------------------------------------------------------------------------
' bf_packet: verify sum8, dispatch by packet type.
' ---------------------------------------------------------------------------
bf_packet: PROCEDURE
    #bs_sum = 0
    FOR bs_i = 0 TO bf_want - 2
        #bs_sum = #bs_sum + (PEEK(BFACC + bs_i) AND 255)
    NEXT bs_i
    IF (#bs_sum AND 255) <> (PEEK(BFACC + bf_want - 1) AND 255) THEN RETURN

    bs_i = PEEK(BFACC + 2) AND 255
    IF bs_i = PT_WELCOME THEN
        welcome_seen = 1
        RETURN
    END IF
    IF bs_i = PT_LOGIN_RESP THEN
        GOSUB lg_response
        RETURN
    END IF
    IF bs_i <> PT_WINDOW THEN RETURN

    ' WINDOW payload: tick u16, origin_x u16, origin_y u16, w, h, chunk_y,
    ' chunk_h, tile_count u16, tiles[96] -- payload starts at BFACC+4.
    IF (PEEK(BFACC + 10) AND 255) <> WIN_W THEN RETURN
    IF (PEEK(BFACC + 11) AND 255) <> WIN_H THEN RETURN
    #t0 = (PEEK(BFACC + 4) AND 255) + (PEEK(BFACC + 5) AND 255) * 256
    IF #t0 <> #bs_tick THEN
        ' new bootstrap run (HELLO retry): restart assembly
        #bs_tick = #t0
        bs_mask = 0
        org_x = PEEK(BFACC + 6) AND 255
        org_y = PEEK(BFACC + 8) AND 255
    END IF
    bs_row = PEEK(BFACC + 12) AND 255           ' chunk_y: 0,3,...,21
    IF bs_row > 21 THEN RETURN
    ' copy 96 tiles into rows chunk_y..chunk_y+2 (ring offsets are zero
    ' during bootstrap)
    #t1 = TERR + row_tab(bs_row)
    FOR bs_i = 0 TO 95
        #t0 = PEEK(BFACC + 16 + bs_i) AND 255
        POKE #t1 + bs_i, #t0
    NEXT bs_i
    bs_mask = bs_mask OR bit_tab(bs_row / 3)
    IF bs_mask = 255 THEN
        IF welcome_seen THEN bs_done = 1
    END IF
END

' ---------------------------------------------------------------------------
' bs_hello: raw 12-byte $BF HELLO straight into FN_TX and out.
' flags 0 = default link profile; seed 1; token must be nonzero.
' ---------------------------------------------------------------------------
bs_hello: PROCEDURE
    POKE FN_TX + 0, PKT_MAGIC
    POKE FN_TX + 1, PKT_VER
    POKE FN_TX + 2, PT_HELLO
    POKE FN_TX + 3, 7
    POKE FN_TX + 4, 0                           ' flags: default profile
    POKE FN_TX + 5, 1                           ' seed lo
    POKE FN_TX + 6, 0                           ' seed hi
    POKE FN_TX + 7, tok0
    POKE FN_TX + 8, tok1
    POKE FN_TX + 9, tok2
    POKE FN_TX + 10, tok3
    #bs_sum = 0
    FOR bs_i = 0 TO 10
        #bs_sum = #bs_sum + (PEEK(FN_TX + bs_i) AND 255)
    NEXT bs_i
    POKE FN_TX + 11, #bs_sum AND 255
    fn_len = 12
    GOSUB net_write
END

' ---------------------------------------------------------------------------
' bs_run: drive the bootstrap to completion. HELLO is re-sent after quiet
' spells (the socket may not be fully open when the first one goes out);
' each retry restarts the transfer server-side. ~20s overall deadline.
' Result in fn_ok.
' ---------------------------------------------------------------------------
bs_run: PROCEDURE
    bs_done = 0
    welcome_seen = 0
    bs_mask = 0
    #bs_tick = 0
    bf_len = 0
    bs_tries = 1
    GOSUB bs_hello
    #bs_quiet = FRAME
    #bs_start = FRAME
    WHILE bs_done = 0
        WAIT
        GOSUB net_status
        ' Read on available bytes even when the status error byte is not
        ' SUCCESS -- buffered data (e.g. behind an EOF) is still readable,
        ' and #net_avail is 0 whenever the transaction itself failed.
        IF #net_avail > 0 THEN
            #net_readlen = RX_CHUNK
            IF #net_avail < RX_CHUNK THEN #net_readlen = #net_avail
            GOSUB net_read
            IF #net_gotlen > 0 THEN
                #bs_quiet = FRAME
                #rx_n = #net_gotlen - 1
                FOR #rx_i = 0 TO #rx_n
                    bf_b = PEEK(FN_RX + #rx_i) AND 255
                    GOSUB bf_feed
                NEXT #rx_i
            END IF
        END IF
        IF (FRAME - #bs_quiet) >= HELLO_RETRY_FRAMES THEN
            IF bs_tries >= 10 THEN
                fn_ok = 0
                RETURN
            END IF
            bs_tries = bs_tries + 1
            GOSUB bs_hello
            #bs_quiet = FRAME
        END IF
        IF (FRAME - #bs_start) >= 1200 THEN
            fn_ok = 0
            RETURN
        END IF
    WEND
    fn_ok = 1
END
