' render.bas -- BACKTAB renderer: 20x10 tile viewport + 2 HUD rows.
'
' Everything is card stamping, no MOBs: movement is tile-locked and the 8
' sprite slots could never cover player + 6 entities + 3 remotes + 4 items.
' Terrain cells come from the ring window through taddr; objects are stamped
' over terrain each frame with a shadow list of covered cells, restored by
' recomputing the terrain word (nothing is saved, so restore cannot go
' stale).
'
' A full 200-cell repaint costs ~2 frames and happens only when the camera
' moves, the window origin shifts uncompensated, or a visible terrain cell
' changes -- the Lynx trigger discipline. Object stamping is ~14 pokes.


' row * 20 for BACKTAB cell math without runtime multiply
mul20:
    DATA 0,20,40,60,80,100,120,140,160,180,200,220

' ---------------------------------------------------------------------------
' rn_full: repaint all 200 viewport cells from the terrain window.
' ---------------------------------------------------------------------------
rn_full: PROCEDURE
    rf_dst = 0
    FOR rf_r = 0 TO 9
        #t1 = TERR + row_tab(row_base + cam_y + rf_r)
        rf_c0 = cam_x + col_off
        FOR rf_c = 0 TO 19
            #BACKTAB(rf_dst) = tile_word(PEEK(#t1 + ((rf_c0 + rf_c) AND 31)) AND 255)
            rf_dst = rf_dst + 1
        NEXT rf_c
    NEXT rf_r
    shd_n = 0
END

' ---------------------------------------------------------------------------
' rn_restore: repaint just the cells objects covered last frame.
' ---------------------------------------------------------------------------
rn_restore: PROCEDURE
    IF shd_n = 0 THEN RETURN
    FOR sp_i = 0 TO shd_n - 1
        #t1 = TERR + row_tab(row_base + cam_y + shd_row(sp_i))
        #t0 = PEEK(#t1 + ((cam_x + shd_col(sp_i) + col_off) AND 31)) AND 255
        #BACKTAB(mul20(shd_row(sp_i)) + shd_col(sp_i)) = tile_word(#t0)
    NEXT sp_i
    shd_n = 0
END

' ---------------------------------------------------------------------------
' rn_put: stamp word #sp_w at world tile (sp_x, sp_y) if visible; records
' the covered cell in the shadow list. (8-bit unsigned wrap makes the
' "below origin+camera" case fail the < compare, so one check suffices.)
' ---------------------------------------------------------------------------
rn_put: PROCEDURE
    sp_x = sp_x - org_x - cam_x
    IF sp_x >= VIEW_COLS THEN RETURN
    sp_y = sp_y - org_y - cam_y
    IF sp_y >= VIEW_ROWS THEN RETURN
    #BACKTAB(mul20(sp_y) + sp_x) = #sp_w
    IF shd_n < 15 THEN
        shd_col(shd_n) = sp_x
        shd_row(shd_n) = sp_y
        shd_n = shd_n + 1
    END IF
END

' ---------------------------------------------------------------------------
' rn_stamp_all: draw items (bottom), entities, remote players, local player
' (top). Bat/slime alternate their two art tiles on the FRAME clock; an
' entity hit-pulse blinks the card white for a few frames.
' ---------------------------------------------------------------------------
rn_stamp_all: PROCEDURE
    anim = (FRAME AND 16) / 16

    IF itm_n > 0 THEN
        FOR sp_i = 0 TO itm_n - 1
            #t0 = PEEK(ITMBUF + sp_i * 4 + 2) AND 7
            #sp_w = item_word(#t0)
            sp_x = PEEK(ITMBUF + sp_i * 4) AND 255
            sp_y = PEEK(ITMBUF + sp_i * 4 + 1) AND 255
            GOSUB rn_put
        NEXT sp_i
    END IF

    IF ent_n > 0 THEN
        FOR sp_i = 0 TO ent_n - 1
            #t0 = PEEK(ENTBUF + sp_i * 4 + 3) AND 255
            IF #t0 > 8 THEN #t0 = 5
            #t0 = kind_tile(#t0)
            IF #t0 = 44 THEN #t0 = #t0 + anim
            IF #t0 = 46 THEN #t0 = #t0 + anim
            #sp_w = tile_word(#t0)
            IF ent_hit(sp_i) > 0 THEN
                ent_hit(sp_i) = ent_hit(sp_i) - 1
                #sp_w = (#sp_w AND $0FF8) + 7
            END IF
            sp_x = PEEK(ENTBUF + sp_i * 4) AND 255
            sp_y = PEEK(ENTBUF + sp_i * 4 + 1) AND 255
            GOSUB rn_put
        NEXT sp_i
    END IF

    IF rem_n > 0 THEN
        FOR sp_i = 0 TO rem_n - 1
            ' state bit0 = alive
            IF (PEEK(REMBUF + sp_i * 4 + 3) AND 1) <> 0 THEN
                #t0 = PEEK(REMBUF + sp_i * 4 + 2) AND 7
                #sp_w = rem_word(#t0)
                sp_x = PEEK(REMBUF + sp_i * 4) AND 255
                sp_y = PEEK(REMBUF + sp_i * 4 + 1) AND 255
                GOSUB rn_put
            END IF
        NEXT sp_i
    END IF

    #sp_w = ply_word(facing)
    sp_x = px
    sp_y = py
    GOSUB rn_put
END

' ---------------------------------------------------------------------------
' cm_track: keep the player inside the camera's comfort band (margins), clamp
' to the window, repaint on any actual camera move.
' ---------------------------------------------------------------------------
cm_track: PROCEDURE
    cm_t = px - org_x           ' player window-relative 0..31
    IF cm_t < cam_x + 6 THEN
        cam_x = cm_t - 6
        IF cam_x > CAM_MAX_X THEN cam_x = 0        ' unsigned wrap = below 0
        repaint_full = 1
    ELSEIF cm_t > cam_x + 13 THEN
        cam_x = cm_t - 13
        IF cam_x > CAM_MAX_X THEN cam_x = CAM_MAX_X
        repaint_full = 1
    END IF
    cm_t = py - org_y           ' 0..23
    IF cm_t < cam_y + 3 THEN
        cam_y = cm_t - 3
        IF cam_y > CAM_MAX_Y THEN cam_y = 0
        repaint_full = 1
    ELSEIF cm_t > cam_y + 6 THEN
        cam_y = cm_t - 6
        IF cam_y > CAM_MAX_Y THEN cam_y = CAM_MAX_Y
        repaint_full = 1
    END IF
END

' ---------------------------------------------------------------------------
' rn_hud: row 10 -- hearts, level, gold, PvP flag. Redrawn only on change.
' ---------------------------------------------------------------------------
rn_hud: PROCEDURE
    IF hud_dirty = 0 THEN RETURN
    hud_dirty = 0
    FOR rf_c = 0 TO 19
        #BACKTAB(200 + rf_c) = 0
    NEXT rf_c
    #BACKTAB(200) = hud_word(0)
    PRINT AT 201 COLOR COL_TEXT, <.2>hud_hp
    #BACKTAB(203) = (15 * 8) + COL_DIM              ' '/'
    PRINT AT 204 COLOR COL_DIM, <.2>hud_max
    PRINT AT 207 COLOR COL_TEXT, "L"
    PRINT AT 208 COLOR COL_TEXT, <.2>hud_lvl
    PRINT AT 211 COLOR COL_HILITE, "G"
    PRINT AT 212 COLOR COL_HILITE, <.5>#hud_gold
    IF hud_pvp THEN
        PRINT AT 219 COLOR COL_ERROR, "P"
    END IF
END

' ---------------------------------------------------------------------------
' rn_msg: row 11 -- server MESSAGE marquee (scrolls text wider than 20
' cells), falling back to the quest line when the message has run out.
' ---------------------------------------------------------------------------
rn_msg: PROCEDURE
    IF dbg_on THEN
        GOSUB rn_diag
        RETURN
    END IF
    IF msg_len > 0 THEN
        IF msg_len <= 20 THEN
            ' static display, then expire to the quest line after ~4s
            IF msg_dirty THEN
                GOSUB rm_draw_msg
                msg_wait = 0
            END IF
            msg_wait = msg_wait + 1
            IF msg_wait > 240 THEN
                msg_len = 0
                msg_dirty = 1
            END IF
            RETURN
        END IF
        ' marquee: advance one column every 8 frames, hold at each end
        IF msg_dirty THEN
            msg_off = 0
            msg_wait = 0
            GOSUB rm_draw_msg
        END IF
        msg_wait = msg_wait + 1
        IF msg_off = 0 THEN
            IF msg_wait < 60 THEN RETURN
        END IF
        IF msg_wait < 8 THEN RETURN
        msg_wait = 0
        msg_off = msg_off + 1
        IF msg_off > msg_len - 20 THEN
            msg_len = 0
            msg_dirty = 1
            RETURN
        END IF
        GOSUB rm_draw_msg
        RETURN
    END IF
    IF msg_dirty THEN
        msg_dirty = 0
        GOSUB rm_draw_quest
    END IF
END

' Draw MSGBUF[msg_off..] into row 11 (chars are server-sanitized 32-95).
rm_draw_msg: PROCEDURE
    msg_dirty = 0
    FOR rm_i = 0 TO 19
        rm_ch = 32
        IF msg_off + rm_i < msg_len THEN
            #t0 = PEEK(MSGBUF + msg_off + rm_i) AND 255
            rm_ch = #t0
            IF rm_ch < 32 THEN rm_ch = 32
            IF rm_ch > 95 THEN rm_ch = 32
        END IF
        #BACKTAB(220 + rm_i) = (rm_ch - 32) * 8 + COL_HILITE
    NEXT rm_i
END

rm_draw_quest: PROCEDURE
    FOR rm_i = 0 TO 19
        rm_ch = 32
        IF rm_i < q_len THEN
            #t0 = PEEK(QSTBUF + rm_i) AND 255
            rm_ch = #t0
            IF rm_ch < 32 THEN rm_ch = 32
            IF rm_ch > 95 THEN rm_ch = 32
        END IF
        #BACKTAB(220 + rm_i) = (rm_ch - 32) * 8 + COL_DIM
    NEXT rm_i
END

' ---------------------------------------------------------------------------
' rn_diag: keypad-9 diagnostic line -- frames per loop pass, rx bytes
' available, bad frame count.
' ---------------------------------------------------------------------------
rn_diag: PROCEDURE
    dg_delta = FRAME - #dg_last
    #dg_last = FRAME
    PRINT AT 220 COLOR COL_TEXT, "F"
    PRINT AT 221 COLOR COL_TEXT, <.2>dg_delta
    PRINT AT 224 COLOR COL_TEXT, "A"
    PRINT AT 225 COLOR COL_TEXT, <.4>#net_avail
    PRINT AT 230 COLOR COL_TEXT, "B"
    PRINT AT 231 COLOR COL_TEXT, <.3>rx_drops
    PRINT AT 235 COLOR COL_TEXT, "Q"
    PRINT AT 236 COLOR COL_TEXT, <.2>pq_n
END

' ---------------------------------------------------------------------------
' rn_dlg: dialogue overlay -- speaker line + up to 7 rows of 20 over the
' top of the viewport. Repainted only when the page changes; the viewport
' repaints fully when the modal closes.
' ---------------------------------------------------------------------------
spk_tab:
    ' speaker_id 0-7 -> first char (space,?,?,N,D,W,L,G)
    DATA 32,63,63,78,68,87,76,71
rn_dlg: PROCEDURE
    IF dlg_dirty = 0 THEN RETURN
    dlg_dirty = 0
    ' clear rows 1..9
    FOR rm_i = 20 TO 199
        #BACKTAB(rm_i) = 0
    NEXT rm_i
    ' speaker initial + separator
    rm_ch = 63
    IF dlg_speaker < 8 THEN rm_ch = spk_tab(dlg_speaker)
    #BACKTAB(20) = (rm_ch - 32) * 8 + COL_HILITE
    #BACKTAB(21) = (26 * 8) + COL_HILITE            ' ':'
    ' text rows 2..8
    FOR rd_row = 0 TO 6
        FOR rm_i = 0 TO 19
            rm_ch = 32
            rm_n2 = rd_row * 20 + rm_i
            IF rm_n2 < dlg_len THEN
                #t0 = PEEK(DLGBUF + rm_n2) AND 255
                rm_ch = #t0
                IF rm_ch >= 97 THEN
                    IF rm_ch <= 122 THEN rm_ch = rm_ch - 32
                END IF
                IF rm_ch < 32 THEN rm_ch = 32
                IF rm_ch > 95 THEN rm_ch = 32
            END IF
            #BACKTAB(40 + rd_row * 20 + rm_i) = (rm_ch - 32) * 8 + COL_TEXT
        NEXT rm_i
    NEXT rd_row
    ' prompt row 9
    IF (dlg_flags AND DLG_QUEST_OFFER) <> 0 THEN
        PRINT AT 180 COLOR COL_HILITE, "BTN=YES   CLEAR=NO"
    ELSE
        PRINT AT 180 COLOR COL_HILITE, "BTN=CONTINUE"
    END IF
END
