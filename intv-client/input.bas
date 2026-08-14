' input.bas -- disc/button/keypad input and the movement cadence.
'
' Movement is paced by WORLD_STATE arrivals (world_tick), the Lynx lesson:
' the server applies only the newest PLAYER_STATE per 10 Hz tick, so one
' step per tick is the correct pacing -- faster sending coalesces into
' diagonal deltas that fail the server's corner rule and snap back.
'
' Diagonals are tested first (disc reports both axes), aim follows the disc
' exactly including diagonals, drawn facing collapses to a cardinal via the
' same parity the Lynx uses (its facing_frame table).


' wire facing -> drawn cardinal facing (diagonals borrow the side facings)
face_tab:
    DATA 0,1,2,3,2,3,2,3

' ---------------------------------------------------------------------------
' ig_poll: sample disc + buttons + keypad with edge detection.
' ---------------------------------------------------------------------------
ig_poll: PROCEDURE
    ig_dir = 255
    IF CONT.UP THEN
        IF CONT.LEFT THEN
            ig_dir = 4
        ELSEIF CONT.RIGHT THEN
            ig_dir = 5
        ELSE
            ig_dir = 0
        END IF
    ELSEIF CONT.DOWN THEN
        IF CONT.LEFT THEN
            ig_dir = 6
        ELSEIF CONT.RIGHT THEN
            ig_dir = 7
        ELSE
            ig_dir = 1
        END IF
    ELSEIF CONT.LEFT THEN
        ig_dir = 2
    ELSEIF CONT.RIGHT THEN
        ig_dir = 3
    END IF

    ' Side buttons: top = fire, either bottom = interact/pickup. Latched so
    ' a held button fires once; the counters ride the next PLAYER_STATE.
    IF CONT.B0 THEN
        IF fire_latch = 0 THEN
            fire_latch = 1
            fire_ctr = fire_ctr + 1
            btn_bits = btn_bits + 1
            ps_dirty = 1
            sfx_id = 2
            GOSUB sfx_start
        END IF
    ELSE
        fire_latch = 0
    END IF
    IF CONT.B1 + CONT.B2 THEN
        IF pickup_latch = 0 THEN
            pickup_latch = 1
            pickup_ctr = pickup_ctr + 1
            ps_dirty = 1
            sfx_id = 4
            GOSUB sfx_start
        END IF
    ELSE
        pickup_latch = 0
    END IF

    ' Keypad (edge-detected: act once per press)
    IF CONT.KEY <> key_prev THEN
        key_prev = CONT.KEY
        IF key_prev = 5 THEN
            ' PvP toggle: server edge-detects the counter change
            pvp_ctr = pvp_ctr + 1
            ps_dirty = 1
        ELSEIF key_prev = 9 THEN
            dbg_on = 1 - dbg_on
            msg_dirty = 1
        END IF
    END IF
END

' ---------------------------------------------------------------------------
' ig_move: one predicted step per server tick while the disc is held.
' A step refused by prediction does not consume the cadence slot.
' ---------------------------------------------------------------------------
ig_move: PROCEDURE
    IF ig_dir = 255 THEN RETURN
    aim = ig_dir
    facing = face_tab(ig_dir)
    IF world_tick = move_last_world THEN RETURN
    sw_x = px + dx_tab(ig_dir)
    sw_y = py + dy_tab(ig_dir)
    ' diagonal steps additionally need BOTH orthogonal side cells enterable
    ' (the server refuses corner-cutting)
    IF ig_dir >= 4 THEN
        GOSUB pr_can_step
        IF pr_ok = 0 THEN RETURN
        mv_nx = sw_x
        mv_ny = sw_y
        sw_y = py
        GOSUB pr_can_step
        IF pr_ok = 0 THEN RETURN
        sw_x = px
        sw_y = mv_ny
        GOSUB pr_can_step
        IF pr_ok = 0 THEN RETURN
        sw_x = mv_nx
        sw_y = mv_ny
    ELSE
        GOSUB pr_can_step
        IF pr_ok = 0 THEN RETURN
    END IF
    ' prediction queue full = backpressure: stall, don't clear
    IF pq_n >= PQ_MAX THEN RETURN
    px = sw_x
    py = sw_y
    pq_x(pq_n) = px
    pq_y(pq_n) = py
    #pq_seq(pq_n) = #client_seq
    pq_n = pq_n + 1
    move_last_world = world_tick
    ps_dirty = 1
    sfx_id = 1
    GOSUB sfx_start
END

' ---------------------------------------------------------------------------
' dlg_input: modal input while a dialogue page is open. Button/ENTER =
' advance (ack via pickup counter), CLEAR = decline (buttons bit 1 + ack).
' ---------------------------------------------------------------------------
dlg_input: PROCEDURE
    IF CONT.B0 + CONT.B1 + CONT.B2 THEN
        IF pickup_latch = 0 THEN
            pickup_latch = 1
            GOSUB dlg_ack
        END IF
    ELSE
        pickup_latch = 0
    END IF
    IF CONT.KEY <> key_prev THEN
        key_prev = CONT.KEY
        IF key_prev = KEYPAD_ENTER THEN
            GOSUB dlg_ack
        ELSEIF key_prev = KEYPAD_CLEAR THEN
            btn_bits = btn_bits + 2
            GOSUB dlg_ack
        END IF
    END IF
END

dlg_ack: PROCEDURE
    pickup_ctr = pickup_ctr + 1
    ps_dirty = 1
    dlg_ack_id = dlg_id
    dlg_ack_page = dlg_page
    dlg_active = 0
    repaint_full = 1
    hud_dirty = 1
    msg_dirty = 1
    sfx_id = 4
    GOSUB sfx_start
END
