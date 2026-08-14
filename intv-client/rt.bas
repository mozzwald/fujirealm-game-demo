' rt.bas -- realtime v3 codec: COBS deframing + CRC-16/CCITT-FALSE + frame
' builders. Port of lynx-client/src/rt_state.c.
'
' Receive: rt_rx_pump feeds bytes from FN_RX into a persistent accumulator
' (FN_RX is overwritten by every mailbox transaction, so partial frames MUST
' survive in RXACC between reads). A 0x00 delimiter completes a frame:
' COBS-decode into RTWS, validate, ZERO THE TAIL (senders strip trailing
' zero payload bytes -- every handler reads fixed offsets from a 64-byte
' zero-padded workspace; this is the single most important protocol detail),
' CRC-check, dispatch.
'
' Send: builders fill TXRAW, tx_frame strips trailing zeros, CRCs inline
' (keeps GOSUB depth down), COBS-encodes appending to FN_TX. All frames of
' one loop pass batch into a single net_write (tx_flush) -- fn_transact
' blocks >= 1 frame each, and COBS frames concatenate freely on TCP.


' ---------------------------------------------------------------------------
' rt_rx_pump: consume the #net_gotlen bytes sitting in FN_RX.
' ---------------------------------------------------------------------------
rt_rx_pump: PROCEDURE
    IF #net_gotlen = 0 THEN RETURN
    #rx_n = #net_gotlen - 1
    FOR #rx_i = 0 TO #rx_n
        #t0 = PEEK(FN_RX + #rx_i) AND 255
        IF #t0 = 0 THEN
            IF acc_len > 0 THEN
                IF acc_len <= 80 THEN GOSUB rt_frame
            END IF
            acc_len = 0
        ELSE
            IF acc_len < 80 THEN
                POKE RXACC + acc_len, #t0
                acc_len = acc_len + 1
            ELSE
                acc_len = 81            ' oversize: discard to next delimiter
            END IF
        END IF
    NEXT #rx_i
END

' ---------------------------------------------------------------------------
' rt_frame: COBS-decode RXACC[0..acc_len) -> RTWS, validate, dispatch.
' A reject costs exactly the bytes to the delimiter; never reset the pump.
' ---------------------------------------------------------------------------
rt_frame: PROCEDURE
    rf_rd = 0
    rf_wr = 0
    WHILE rf_rd < acc_len
        rf_code = PEEK(RXACC + rf_rd) AND 255
        rf_rd = rf_rd + 1
        IF rf_code > 1 THEN
            FOR rf_i = 2 TO rf_code
                IF rf_rd >= acc_len THEN GOTO rf_bad
                IF rf_wr >= 64 THEN GOTO rf_bad
                #t0 = PEEK(RXACC + rf_rd) AND 255
                POKE RTWS + rf_wr, #t0
                rf_rd = rf_rd + 1
                rf_wr = rf_wr + 1
            NEXT rf_i
        END IF
        IF rf_rd < acc_len THEN
            ' not at frame end: the group boundary encodes a zero
            IF rf_wr >= 64 THEN GOTO rf_bad
            POKE RTWS + rf_wr, 0
            rf_wr = rf_wr + 1
        END IF
    WEND
    raw_len = rf_wr
    IF raw_len < 8 THEN GOTO rf_bad
    IF raw_len > 62 THEN GOTO rf_bad
    IF (PEEK(RTWS + 1) AND 255) <> RT_VER THEN GOTO rf_bad
    IF (PEEK(RTWS + 0) AND 255) + 8 <> raw_len THEN GOTO rf_bad
    ' CRC over bytes 0..raw_len-3, compared against LE bytes at the end
    crc_h = 255
    crc_l = 255
    FOR rf_i = 0 TO raw_len - 3
        crc_x = crc_h XOR (PEEK(RTWS + rf_i) AND 255)
        crc_h = crc_l XOR crc_hi_tab(crc_x)
        crc_l = crc_lo_tab(crc_x)
    NEXT rf_i
    IF (PEEK(RTWS + raw_len - 2) AND 255) <> crc_l THEN GOTO rf_bad
    IF (PEEK(RTWS + raw_len - 1) AND 255) <> crc_h THEN GOTO rf_bad
    ' zero the tail (including the CRC bytes) so fixed-offset reads see the
    ' stripped zeros
    FOR rf_i = raw_len - 2 TO 63
        POKE RTWS + rf_i, 0
    NEXT rf_i
    w_type = PEEK(RTWS + 2) AND 255
    w_status = PEEK(RTWS + 3) AND 255
    #last_server_seq = (PEEK(RTWS + 4) AND 255) + (PEEK(RTWS + 5) AND 255) * 256
    ON w_type GOSUB , , st_world, ce_edge, , st_mapchg, , st_hud, st_msg, st_quest, , st_respawn, , , st_remotes, , ce_fill_row, st_items, , , , , st_commitack, , st_dlg
    RETURN

rf_bad:
    rx_drops = rx_drops + 1
END

' ---------------------------------------------------------------------------
' tx_frame: TXRAW holds type/status/payload (payload at TXRAW+6, nominal
' length tx_pay); strip trailing zeros, stamp header + seq, CRC inline,
' COBS-encode appended to FN_TX at #fn_txlen, add the 0x00 delimiter.
' Each frame consumes one #client_seq.
' ---------------------------------------------------------------------------
tx_frame: PROCEDURE
    WHILE tx_pay > 0
        IF (PEEK(TXRAW + 5 + tx_pay) AND 255) <> 0 THEN EXIT WHILE
        tx_pay = tx_pay - 1
    WEND
    POKE TXRAW + 0, tx_pay
    POKE TXRAW + 1, RT_VER
    POKE TXRAW + 2, tx_type
    POKE TXRAW + 3, tx_status
    POKE TXRAW + 4, #client_seq AND 255
    POKE TXRAW + 5, #client_seq / 256
    #client_seq = #client_seq + 1
    raw_len = 6 + tx_pay
    crc_h = 255
    crc_l = 255
    FOR tf_i = 0 TO raw_len - 1
        crc_x = crc_h XOR (PEEK(TXRAW + tf_i) AND 255)
        crc_h = crc_l XOR crc_hi_tab(crc_x)
        crc_l = crc_lo_tab(crc_x)
    NEXT tf_i
    POKE TXRAW + raw_len, crc_l
    POKE TXRAW + raw_len + 1, crc_h
    raw_len = raw_len + 2
    ' COBS encode (raw_len <= 64 < 254, so no 0xFF group case)
    tf_code_pos = #fn_txlen
    #fn_txlen = #fn_txlen + 1
    tf_code = 1
    FOR tf_i = 0 TO raw_len - 1
        #t0 = PEEK(TXRAW + tf_i) AND 255
        IF #t0 = 0 THEN
            POKE FN_TX + tf_code_pos, tf_code
            tf_code_pos = #fn_txlen
            #fn_txlen = #fn_txlen + 1
            tf_code = 1
        ELSE
            POKE FN_TX + #fn_txlen, #t0
            #fn_txlen = #fn_txlen + 1
            tf_code = tf_code + 1
        END IF
    NEXT tf_i
    POKE FN_TX + tf_code_pos, tf_code
    POKE FN_TX + #fn_txlen, 0
    #fn_txlen = #fn_txlen + 1
END

' tx_flush: one net_write per loop pass carrying every queued frame.
tx_flush: PROCEDURE
    IF #fn_txlen = 0 THEN RETURN
    fn_len = #fn_txlen
    GOSUB net_write
    #fn_txlen = 0
END

' ---------------------------------------------------------------------------
' Frame builders. Payload bytes beyond what each POKEs are guaranteed zero:
' tx_frame's trailing-zero strip makes stale TXRAW bytes beyond tx_pay
' irrelevant only if they ARE zero -- so builders must POKE every field of
' their nominal payload, including zeros.
' ---------------------------------------------------------------------------

' PLAYER_STATE (type 1): desired position, aim, buttons, event counters.
snd_player_state: PROCEDURE
    POKE TXRAW + 6, px
    POKE TXRAW + 7, py
    POKE TXRAW + 8, aim
    POKE TXRAW + 9, btn_bits
    POKE TXRAW + 10, fire_ctr
    POKE TXRAW + 11, pickup_ctr
    POKE TXRAW + 12, #last_server_seq AND 255
    POKE TXRAW + 13, #last_server_seq / 256
    POKE TXRAW + 14, rx_drops
    POKE TXRAW + 15, pvp_ctr
    tx_pay = 10
    tx_type = RTS_PLAYER_STATE
    tx_status = 0
    GOSUB tx_frame
    btn_bits = 0
END

' AUTH (type 13): the 4 token bytes, LE. Doubles as the keepalive.
snd_auth: PROCEDURE
    POKE TXRAW + 6, tok0
    POKE TXRAW + 7, tok1
    POKE TXRAW + 8, tok2
    POKE TXRAW + 9, tok3
    tx_pay = 4
    tx_type = RTS_AUTH
    tx_status = 0
    GOSUB tx_frame
END

' CACHE_STEP_ACK (type 21): revision + committed origin.
snd_ack: PROCEDURE
    POKE TXRAW + 6, #revision AND 255
    POKE TXRAW + 7, #revision / 256
    POKE TXRAW + 8, org_x
    POKE TXRAW + 9, org_y
    tx_pay = 4
    tx_type = RTS_STEP_ACK
    tx_status = 0
    GOSUB tx_frame
END

' RESYNC_REQUEST (type 15): current origin + in-progress fill state.
snd_resync: PROCEDURE
    POKE TXRAW + 6, org_x
    POKE TXRAW + 7, org_y
    IF fill_active THEN
        POKE TXRAW + 8, fill_ox
        POKE TXRAW + 9, fill_oy
        POKE TXRAW + 10, rows0
        POKE TXRAW + 11, rows1
        POKE TXRAW + 12, rows2
        POKE TXRAW + 13, fill_id
    ELSE
        POKE TXRAW + 8, 0
        POKE TXRAW + 9, 0
        POKE TXRAW + 10, 0
        POKE TXRAW + 11, 0
        POKE TXRAW + 12, 0
        POKE TXRAW + 13, 0
    END IF
    POKE TXRAW + 14, 0
    tx_pay = 9
    tx_type = RTS_RESYNC
    tx_status = 0
    GOSUB tx_frame
END

' WINDOW_COMMIT (type 20): adopt-this-window handshake after a full fill.
snd_commit: PROCEDURE
    POKE TXRAW + 6, commit_fill
    POKE TXRAW + 7, org_x
    POKE TXRAW + 8, org_y
    POKE TXRAW + 9, map_id
    POKE TXRAW + 10, 1
    tx_pay = 5
    tx_type = RTS_COMMIT
    tx_status = 0
    GOSUB tx_frame
END

' MAP_READY (type 19): acknowledges a MAP_CHANGE.
snd_map_ready: PROCEDURE
    POKE TXRAW + 6, map_id
    POKE TXRAW + 7, org_x
    POKE TXRAW + 8, org_y
    tx_pay = 3
    tx_type = RTS_MAP_READY
    tx_status = 0
    GOSUB tx_frame
END
