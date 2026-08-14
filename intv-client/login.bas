' login.bas -- identity: FujiNet appkey record, login-server round trip,
' name entry.
'
' The appkey record is the ASCII string "<username>,<token>,<host>" (<= 64
' bytes), creator $3022 (FujiRealm, same as the Lynx client) app 2, fixed
' key 1. The host is stored inside the record and compared byte-for-byte
' with the build-time host: a token is only meaningful to the server that
' issued it, so a host mismatch forces a fresh login. (The Lynx hashes the
' endpoint into the key so servers get separate slots; with a fixed key a
' host switch simply overwrites the old record.)
'
' The token stays ASCII (TOKASC) until tok_parse converts it once into the
' 4 little-endian bytes tok0..tok3 that HELLO and AUTH carry.


' ---------------------------------------------------------------------------
' id_load: read + parse + validate the appkey record. id_ok = 1 on success
' (NAMEBUF and TOKASC populated).
' ---------------------------------------------------------------------------
id_load: PROCEDURE
    id_ok = 0
    ' one retry: the very first transaction can time out on a cold link
    FOR il_i = 0 TO 1
        ak_creator_lo = $22
        ak_creator_hi = $30
        ak_app = 2
        ak_key = 1
        ak_mode = 0
        GOSUB appkey_open
        IF fn_ok THEN EXIT FOR
    NEXT il_i
    IF fn_ok = 0 THEN RETURN
    #fn_src = IDBUF
    ls_max = 64
    GOSUB appkey_read
    GOSUB appkey_close
    IF fn_len = 0 THEN RETURN

    ' username up to the first comma (1-10 chars)
    il_i = 0
    il_j = 0
    WHILE il_i < 11
        il_c = PEEK(IDBUF + il_i) AND 255
        IF il_c = 44 THEN EXIT WHILE
        IF il_c < 33 THEN RETURN
        IF il_c > 126 THEN RETURN
        POKE NAMEBUF + il_i, il_c
        il_i = il_i + 1
    WEND
    IF il_i = 0 THEN RETURN
    IF il_i > 10 THEN RETURN
    POKE NAMEBUF + il_i, 0
    il_i = il_i + 1                             ' skip comma

    ' token digits up to the second comma (1-10 digits)
    WHILE il_j < 11
        il_c = PEEK(IDBUF + il_i) AND 255
        IF il_c = 44 THEN EXIT WHILE
        IF il_c < 48 THEN RETURN
        IF il_c > 57 THEN RETURN
        POKE TOKASC + il_j, il_c
        il_i = il_i + 1
        il_j = il_j + 1
    WEND
    IF il_j = 0 THEN RETURN
    IF il_j > 10 THEN RETURN
    POKE TOKASC + il_j, 0
    il_i = il_i + 1

    ' host must match the build-time endpoint exactly, then end of record --
    ' accepting a trailing CR/LF so hand-made key files (echo, editors that
    ' add a final newline) validate too
    FOR il_j = 0 TO HOST_LEN - 1
        IF (PEEK(IDBUF + il_i + il_j) AND 255) <> host_str(il_j) THEN RETURN
    NEXT il_j
    il_c = PEEK(IDBUF + il_i + HOST_LEN) AND 255
    IF il_c <> 0 THEN
        IF il_c <> 10 THEN
            IF il_c <> 13 THEN RETURN
        END IF
    END IF
    id_ok = 1
END

' ---------------------------------------------------------------------------
' tok_parse: TOKASC decimal digits -> tok0..tok3 (u32 LE) via byte-serial
' x10 + digit with ripple carry.
' ---------------------------------------------------------------------------
tok_parse: PROCEDURE
    tok0 = 0
    tok1 = 0
    tok2 = 0
    tok3 = 0
    il_i = 0
    WHILE il_i < 10
        il_c = PEEK(TOKASC + il_i) AND 255
        IF il_c < 48 THEN EXIT WHILE
        IF il_c > 57 THEN EXIT WHILE
        #t0 = tok0 * 10 + (il_c - 48)
        tok0 = #t0
        #t0 = tok1 * 10 + (#t0 / 256)
        tok1 = #t0
        #t0 = tok2 * 10 + (#t0 / 256)
        tok2 = #t0
        #t0 = tok3 * 10 + (#t0 / 256)
        tok3 = #t0
        il_i = il_i + 1
    WEND
END

' ---------------------------------------------------------------------------
' id_store: NAMEBUF + TOKASC + host -> "user,token,host" -> appkey key 1.
' A failed write is reported but not fatal (you just log in again next boot).
' ---------------------------------------------------------------------------
id_store: PROCEDURE
    il_j = 0
    il_i = 0
    WHILE (PEEK(NAMEBUF + il_i) AND 255) <> 0
        il_c = PEEK(NAMEBUF + il_i) AND 255
        POKE IDBUF + il_j, il_c
        il_i = il_i + 1
        il_j = il_j + 1
    WEND
    POKE IDBUF + il_j, 44
    il_j = il_j + 1
    il_i = 0
    WHILE (PEEK(TOKASC + il_i) AND 255) <> 0
        il_c = PEEK(TOKASC + il_i) AND 255
        POKE IDBUF + il_j, il_c
        il_i = il_i + 1
        il_j = il_j + 1
    WEND
    POKE IDBUF + il_j, 44
    il_j = il_j + 1
    FOR il_i = 0 TO HOST_LEN - 1
        POKE IDBUF + il_j, host_str(il_i)
        il_j = il_j + 1
    NEXT il_i
    POKE IDBUF + il_j, 0

    ak_creator_lo = $22
    ak_creator_hi = $30
    ak_app = 2
    ak_key = 1
    ak_mode = 1
    GOSUB appkey_open
    IF fn_ok = 0 THEN RETURN
    #fn_src = IDBUF
    fn_len = il_j
    GOSUB appkey_write
    GOSUB appkey_close
END

' ---------------------------------------------------------------------------
' lg_login: one-shot TCP round trip to the login server (one request per
' connection; the server closes after replying). Result: fn_ok, lg_status
' (0 = ok -> TOKASC holds the new token, 1 = username taken).
' ---------------------------------------------------------------------------
lg_login: PROCEDURE
    lg_seen = 0
    lg_status = 255
    bf_len = 0
    #fn_txlen = 0
    #fn_src = VARPTR login_url(0)
    fn_len = LOGIN_URL_LEN
    GOSUB fn_putstr
    GOSUB net_open
    IF fn_ok = 0 THEN RETURN

    ' LOGIN_REQUEST: BF 01 A0 plen ulen user... sum8
    il_j = 0
    WHILE (PEEK(NAMEBUF + il_j) AND 255) <> 0
        il_j = il_j + 1
    WEND
    POKE FN_TX + 0, PKT_MAGIC
    POKE FN_TX + 1, PKT_VER
    POKE FN_TX + 2, PT_LOGIN_REQ
    POKE FN_TX + 3, il_j + 1
    POKE FN_TX + 4, il_j
    FOR il_i = 0 TO il_j - 1
        il_c = PEEK(NAMEBUF + il_i) AND 255
        POKE FN_TX + 5 + il_i, il_c
    NEXT il_i
    #bs_sum = 0
    FOR il_i = 0 TO il_j + 4
        #bs_sum = #bs_sum + (PEEK(FN_TX + il_i) AND 255)
    NEXT il_i
    POKE FN_TX + 5 + il_j, #bs_sum AND 255
    fn_len = il_j + 6
    GOSUB net_write
    IF fn_ok = 0 THEN
        GOSUB net_close
        RETURN
    END IF

    ' Poll for LOGIN_RESPONSE (~5s). Read whenever bytes are available even
    ' if the status error byte is not SUCCESS: the login server closes right
    ' after replying, so the reply routinely sits behind an EOF (error 136)
    ' status -- and the firmware's interrupt-poll timer may have auto-read
    ' part of it into its buffer already. Gating reads on fn_ok stranded the
    ' reply and failed logins that the server had accepted. (net_status
    ' zeroes #net_avail when the mailbox transaction itself failed.)
    FOR il_j = 0 TO 150
        WAIT
        GOSUB net_status
        IF #net_avail > 0 THEN
            #net_readlen = 64
            GOSUB net_read
            IF #net_gotlen > 0 THEN
                #rx_n = #net_gotlen - 1
                FOR #rx_i = 0 TO #rx_n
                    bf_b = PEEK(FN_RX + #rx_i) AND 255
                    GOSUB bf_feed
                NEXT #rx_i
            END IF
        END IF
        IF lg_seen THEN EXIT FOR
    NEXT il_j
    GOSUB net_close
    IF lg_seen = 0 THEN
        fn_ok = 0
        RETURN
    END IF
    fn_ok = 1
END

' lg_response: LOGIN_RESPONSE payload at BFACC+4: status, len, token digits.
lg_response: PROCEDURE
    lg_status = PEEK(BFACC + 4) AND 255
    il_c = PEEK(BFACC + 5) AND 255
    IF il_c > 10 THEN il_c = 10
    IF il_c > 0 THEN
        FOR il_i = 0 TO il_c - 1
            #t0 = PEEK(BFACC + 6 + il_i) AND 255
            POKE TOKASC + il_i, #t0
        NEXT il_i
    END IF
    POKE TOKASC + il_c, 0
    lg_seen = 1
END

' ---------------------------------------------------------------------------
' name_entry: 8-slot letter picker (up/down cycles A-Z 0-9 _, left/right
' moves, side button accepts with at least one character). -> NAMEBUF.
' ---------------------------------------------------------------------------
name_entry: PROCEDURE
    CLS
    PRINT AT screenpos(2,3) COLOR COL_TEXT, "ENTER YOUR NAME"
    PRINT AT screenpos(1,8) COLOR COL_DIM, "UP/DOWN LETTER"
    PRINT AT screenpos(1,9) COLOR COL_DIM, "BUTTON = DONE"
    FOR il_i = 0 TO 7
        ne_buf(il_i) = 36
    NEXT il_i
    ne_cur = 0
    inp_lock = 0
ne_loop:
    FOR il_i = 0 TO 7
        il_j = COL_DIM
        IF il_i = ne_cur THEN il_j = COL_HILITE
        il_c = ne_buf(il_i)
        IF il_c < 26 THEN
            il_c = 65 + il_c
        ELSEIF il_c < 36 THEN
            il_c = 48 + il_c - 26
        ELSE
            il_c = 95
        END IF
        #BACKTAB(screenpos(6 + il_i, 5)) = (il_c - 32) * 8 + il_j
    NEXT il_i
    WAIT
    IF inp_lock > 0 THEN
        inp_lock = inp_lock - 1
        GOTO ne_loop
    END IF
    IF CONT.RIGHT THEN
        ne_cur = ne_cur + 1
        IF ne_cur > 7 THEN ne_cur = 0
        inp_lock = 8
        GOTO ne_loop
    END IF
    IF CONT.LEFT THEN
        IF ne_cur = 0 THEN ne_cur = 8
        ne_cur = ne_cur - 1
        inp_lock = 8
        GOTO ne_loop
    END IF
    IF CONT.UP THEN
        ne_buf(ne_cur) = ne_buf(ne_cur) + 1
        IF ne_buf(ne_cur) > 36 THEN ne_buf(ne_cur) = 0
        inp_lock = 6
        GOTO ne_loop
    END IF
    IF CONT.DOWN THEN
        IF ne_buf(ne_cur) = 0 THEN ne_buf(ne_cur) = 37
        ne_buf(ne_cur) = ne_buf(ne_cur) - 1
        inp_lock = 6
        GOTO ne_loop
    END IF
    IF CONT.BUTTON = 0 THEN GOTO ne_loop

    ' right-trim blanks; reject an all-blank name
    ne_len = 8
    WHILE ne_len > 0
        IF ne_buf(ne_len - 1) <> 36 THEN EXIT WHILE
        ne_len = ne_len - 1
    WEND
    IF ne_len = 0 THEN GOTO ne_loop
    FOR il_i = 0 TO ne_len - 1
        il_c = ne_buf(il_i)
        IF il_c < 26 THEN
            il_c = 65 + il_c
        ELSEIF il_c < 36 THEN
            il_c = 48 + il_c - 26
        ELSE
            il_c = 95
        END IF
        POKE NAMEBUF + il_i, il_c
    NEXT il_i
    POKE NAMEBUF + ne_len, 0
    ' wait for button release so the game doesn't see this press
ne_release:
    WAIT
    IF CONT.BUTTON THEN GOTO ne_release
END
