' state.bas -- realtime message handlers (ports of lynx-client rt_state.c
' apply_* / main.c reaction logic) plus movement prediction (predict.c).
'
' Every handler reads fixed offsets out of the zero-padded 64-byte RTWS
' workspace; entity/remote/item snapshots are copied to cart RAM buffers
' (the 8-bit variable pool cannot hold them).

' Player / world

' Prediction queue: absolute predicted positions awaiting server echo.
    CONST PQ_MAX = 8

' HUD / message / quest state

' Dialogue

' Map transition

' blk_tab: 1 = players cannot enter (server world.py PLAYER_BLOCKING plus
' static-NPC tiles; tile 13 cave entrance is WALKABLE -- it is the door).
blk_tab:
    DATA 0,0,1,0,1,0,1,1,1,1,0,1,1,0,0,0
    DATA 1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    DATA 0,0,0,0,1,1,1,0,1,1,1,1,0,0,0,0
    DATA 0,0,0,0

' los_tab: 1 = blocks shots (the server's smaller line-of-sight set:
' tiles 2,4,7,8,11,12,16 -- see lynx predict.c). Used by the tracer so it
' stops where the real shot stops.
los_tab:
    DATA 0,0,1,0,1,0,0,1,1,0,0,1,1,0,0,0
    DATA 1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    DATA 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    DATA 0,0,0,0

' Facing deltas, wire order: 0 up,1 down,2 left,3 right,4 ul,5 ur,6 dl,7 dr.
' (255 = -1 as an 8-bit add.)
dx_tab:
    DATA 0,0,255,1,255,1,255,1
dy_tab:
    DATA 255,1,0,0,255,255,1,1

' ---------------------------------------------------------------------------
' st_world: WORLD_STATE (type 2), every server tick. Authoritative position,
' correction flag, echo seq, one live terrain cell, entity snapshot.
' ---------------------------------------------------------------------------
st_world: PROCEDURE
    #echo_seq = (PEEK(RTWS + 10) AND 255) + (PEEK(RTWS + 11) AND 255) * 256

    ' Live single-cell terrain update (chopped tree, taken item). Sent every
    ' tick regardless -- only repaint when the value actually changed.
    sw_x = PEEK(RTWS + 13) AND 255
    sw_y = PEEK(RTWS + 14) AND 255
    sw_x = sw_x - org_x
    sw_y = sw_y - org_y
    IF sw_x < WIN_W THEN
        IF sw_y < WIN_H THEN
            #t1 = taddr(sw_x, sw_y)
            #t0 = PEEK(RTWS + 12) AND 255
            IF (PEEK(#t1) AND 255) <> #t0 THEN
                POKE #t1, #t0
                repaint_full = 1
            END IF
        END IF
    END IF

    ' Entity snapshot -> ENTBUF, kind bit 7 is a one-shot damage pulse.
    ent_n = w_status
    IF ent_n > 6 THEN ent_n = 6
    IF ent_n > 0 THEN
        FOR sw_i = 0 TO ent_n - 1
            #t1 = RTWS + 15 + sw_i * 4
            #t0 = PEEK(#t1) AND 255
            POKE ENTBUF + sw_i * 4, #t0
            #t0 = PEEK(#t1 + 1) AND 255
            POKE ENTBUF + sw_i * 4 + 1, #t0
            #t0 = PEEK(#t1 + 2) AND 255
            POKE ENTBUF + sw_i * 4 + 2, #t0
            #t0 = PEEK(#t1 + 3) AND 255
            IF #t0 >= 128 THEN
                ent_hit(sw_i) = 6
                #t0 = #t0 - 128
            END IF
            POKE ENTBUF + sw_i * 4 + 3, #t0
        NEXT sw_i
    END IF

    hp = PEEK(RTWS + 8) AND 255

    ' Reconcile prediction with the authoritative position.
    IF (PEEK(RTWS + 9) AND 255) <> 0 THEN
        ' correction: the last PLAYER_STATE was rejected -- hard snap
        pq_n = 0
        px = PEEK(RTWS + 6) AND 255
        py = PEEK(RTWS + 7) AND 255
    ELSE
        GOSUB pr_reconcile
    END IF

    world_tick = world_tick + 1
    world_seen = 1
END

' ---------------------------------------------------------------------------
' pr_reconcile: drop queue entries the server has consumed (seq <= echo,
' wrap-safe), then adopt the newest surviving prediction, else the server
' position. (The Lynx additionally re-validates each surviving step against
' the terrain; corrections arrive via correction_flags within a tick, so the
' simplified form converges the same way.)
' ---------------------------------------------------------------------------
pr_reconcile: PROCEDURE
    pr_j = 0
    IF pq_n > 0 THEN
        FOR pr_i = 0 TO pq_n - 1
            #t0 = #pq_seq(pr_i) - #echo_seq
            IF #t0 <> 0 THEN
                IF (#t0 AND $8000) = 0 THEN
                    ' still pending: keep (compact toward the front)
                    #pq_seq(pr_j) = #pq_seq(pr_i)
                    pq_x(pr_j) = pq_x(pr_i)
                    pq_y(pr_j) = pq_y(pr_i)
                    pr_j = pr_j + 1
                END IF
            END IF
        NEXT pr_i
    END IF
    pq_n = pr_j
    IF pq_n > 0 THEN
        px = pq_x(pq_n - 1)
        py = pq_y(pq_n - 1)
    ELSE
        px = PEEK(RTWS + 6) AND 255
        py = PEEK(RTWS + 7) AND 255
    END IF
END

' ---------------------------------------------------------------------------
' pr_can_step: is (sw_x, sw_y) enterable? Checks window bounds, blocking
' tiles, live entities, remote players. Result in pr_ok.
' ---------------------------------------------------------------------------
pr_can_step: PROCEDURE
    pr_ok = 0
    ' world edge (border tiles guard the rim; belt and braces)
    IF sw_x = 0 THEN RETURN
    IF sw_y = 0 THEN RETURN
    IF sw_x >= WORLD_W - 1 THEN RETURN
    IF sw_y >= WORLD_H - 1 THEN RETURN
    ' must be inside the cached window to be verifiable
    pr_i = sw_x - org_x
    pr_j = sw_y - org_y
    IF pr_i >= WIN_W THEN RETURN
    IF pr_j >= WIN_H THEN RETURN
    #t0 = PEEK(taddr(pr_i, pr_j)) AND 255
    IF #t0 > 51 THEN RETURN
    IF blk_tab(#t0) THEN RETURN
    ' live entities occupy their tile
    IF ent_n > 0 THEN
        FOR pr_i = 0 TO ent_n - 1
            IF (PEEK(ENTBUF + pr_i * 4) AND 255) = sw_x THEN
                IF (PEEK(ENTBUF + pr_i * 4 + 1) AND 255) = sw_y THEN RETURN
            END IF
        NEXT pr_i
    END IF
    ' remote players (alive ones) too
    IF rem_n > 0 THEN
        FOR pr_i = 0 TO rem_n - 1
            IF (PEEK(REMBUF + pr_i * 4 + 3) AND 1) <> 0 THEN
                IF (PEEK(REMBUF + pr_i * 4) AND 255) = sw_x THEN
                    IF (PEEK(REMBUF + pr_i * 4 + 1) AND 255) = sw_y THEN RETURN
                END IF
            END IF
        NEXT pr_i
    END IF
    pr_ok = 1
END

' ---------------------------------------------------------------------------
' st_hud: HUD_UPDATE (type 7)
' ---------------------------------------------------------------------------
st_hud: PROCEDURE
    hud_hp = PEEK(RTWS + 6) AND 255
    hud_max = PEEK(RTWS + 7) AND 255
    hud_lvl = PEEK(RTWS + 8) AND 255
    #hud_gold = (PEEK(RTWS + 13) AND 255) + (PEEK(RTWS + 14) AND 255) * 256
    hud_pvp = PEEK(RTWS + 15) AND 1
    hud_dirty = 1
END

' ---------------------------------------------------------------------------
' st_msg: MESSAGE (type 8): [6]=id [7]=len [8..] uppercase ASCII 32-95.
' message_id 0 is a VALID message -- never infer "no message" from the id.
' ---------------------------------------------------------------------------
st_msg: PROCEDURE
    msg_len = PEEK(RTWS + 7) AND 255
    IF msg_len > 39 THEN msg_len = 39
    IF msg_len > 0 THEN
        FOR sw_i = 0 TO msg_len - 1
            #t0 = PEEK(RTWS + 8 + sw_i) AND 255
            POKE MSGBUF + sw_i, #t0
        NEXT sw_i
    END IF
    msg_off = 0
    msg_wait = 0
    msg_dirty = 1
    sfx_id = 5
    GOSUB sfx_start
END

' ---------------------------------------------------------------------------
' st_quest: QUEST_UPDATE (type 9): [6]=quest_id (0 = clear) [7]=state
' [8]=len [9..]=text (prebuilt display string; no client quest knowledge).
' ---------------------------------------------------------------------------
st_quest: PROCEDURE
    IF (PEEK(RTWS + 6) AND 255) = 0 THEN
        q_len = 0
        msg_dirty = 1
        RETURN
    END IF
    q_len = PEEK(RTWS + 8) AND 255
    IF q_len > 39 THEN q_len = 39
    IF q_len > 0 THEN
        FOR sw_i = 0 TO q_len - 1
            #t0 = PEEK(RTWS + 9 + sw_i) AND 255
            POKE QSTBUF + sw_i, #t0
        NEXT sw_i
    END IF
    msg_dirty = 1
END

' ---------------------------------------------------------------------------
' st_remotes: REMOTE_PLAYERS (type 14): count x {x,y,facing,state}
' ---------------------------------------------------------------------------
st_remotes: PROCEDURE
    rem_n = w_status
    IF rem_n > 4 THEN rem_n = 4
    IF rem_n > 0 THEN
        FOR sw_i = 0 TO rem_n * 4 - 1
            #t0 = PEEK(RTWS + 6 + sw_i) AND 255
            POKE REMBUF + sw_i, #t0
        NEXT sw_i
    END IF
END

' ---------------------------------------------------------------------------
' st_items: ITEM_DROPS (type 17): count x {x,y,item_id,quantity}
' ---------------------------------------------------------------------------
st_items: PROCEDURE
    itm_n = w_status
    IF itm_n > 4 THEN itm_n = 4
    IF itm_n > 0 THEN
        FOR sw_i = 0 TO itm_n * 4 - 1
            #t0 = PEEK(RTWS + 6 + sw_i) AND 255
            POKE ITMBUF + sw_i, #t0
        NEXT sw_i
    END IF
END

' ---------------------------------------------------------------------------
' st_mapchg: MAP_CHANGE (type 5): [6]=map [7]=spawn_x [8]=spawn_y. Three
' cases (lynx main.c:1347): new map -> freeze + wait for the full fill;
' same map already loaded -> our MAP_READY was lost, just re-send it;
' duplicate while loading -> re-ack. MAP_READY is idempotent server-side.
' ---------------------------------------------------------------------------
st_mapchg: PROCEDURE
    IF (PEEK(RTWS + 6) AND 255) = map_id THEN
        IF map_sync = 0 THEN
            GOSUB snd_map_ready
            RETURN
        END IF
        GOSUB snd_map_ready
        RETURN
    END IF
    map_id = PEEK(RTWS + 6) AND 255
    px = PEEK(RTWS + 7) AND 255
    py = PEEK(RTWS + 8) AND 255
    pq_n = 0
    ent_n = 0
    rem_n = 0
    itm_n = 0
    map_sync = 1
    msg_dirty = 1
    GOSUB snd_map_ready
END

' ---------------------------------------------------------------------------
' st_respawn: RESPAWN_EVENT (type 11): [6]=map [7]=x [8]=y [9]=hp
' ---------------------------------------------------------------------------
st_respawn: PROCEDURE
    px = PEEK(RTWS + 7) AND 255
    py = PEEK(RTWS + 8) AND 255
    hp = PEEK(RTWS + 9) AND 255
    pq_n = 0
    repaint_full = 1
END

' ---------------------------------------------------------------------------
' st_dlg: DIALOGUE_PAGE (type 24). Pages up to 141 chars arrive as <=47-byte
' chunks, one per tick. The four ordered rules (rt_state.c:242): chunk 0
' resets the buffer; an unexpected index is dropped silently; text appends;
' flags are only committed by the chunk carrying CHUNK_END (taking them from
' earlier chunks froze the Atari client on quest turn-ins). Retransmits
' restart from chunk 0, so reassembly is idempotent.
' ---------------------------------------------------------------------------
st_dlg: PROCEDURE
    dc_idx = PEEK(RTWS + 11) AND 255
    IF dc_idx = 0 THEN
        dlg_len = 0
        dlg_next = 0
        dlg_id = PEEK(RTWS + 6) AND 255
        dlg_speaker = PEEK(RTWS + 7) AND 255
        dlg_page = PEEK(RTWS + 8) AND 255
    END IF
    IF dc_idx <> dlg_next THEN RETURN
    dlg_next = dlg_next + 1
    sw_i = PEEK(RTWS + 12) AND 255
    IF sw_i > 47 THEN sw_i = 47
    IF sw_i > 0 THEN
        FOR sw_x = 0 TO sw_i - 1
            IF dlg_len < 141 THEN
                #t0 = PEEK(RTWS + 13 + sw_x) AND 255
                POKE DLGBUF + dlg_len, #t0
                dlg_len = dlg_len + 1
            END IF
        NEXT sw_x
    END IF
    IF ((PEEK(RTWS + 10) AND 255) AND DLG_CHUNK_END) <> 0 THEN
        dlg_flags = PEEK(RTWS + 10) AND 255
        ' Same (id,page) already acknowledged? Retransmit -- don't reopen.
        IF dlg_id = dlg_ack_id THEN
            IF dlg_page = dlg_ack_page THEN RETURN
        END IF
        dlg_active = 1
        dlg_dirty = 1
    END IF
END
