' cache.bas -- the 32x24 sliding terrain window and its sync protocol.
'
' The active window lives at TERR as a RING: instead of physically shifting
' 700+ bytes when a TERRAIN_EDGE arrives (4-5 frames of CP-1610 time), we
' bump a column offset / row base and write only the incoming 24- or 32-tile
' strip. Logical cell (cx,cy) [0..31, 0..23] maps to:
'
'   taddr(cx,cy) = TERR + row_tab(row_base + cy) + ((cx + col_off) AND 31)
'
' row_tab bakes ((i) MOD 24)*32 for i 0..47 so there is no runtime MOD.
' All protocol logic uses logical origins (org_x/org_y); the ring offsets are
' pure storage. Everyone -- renderer, prediction, live tile updates, edge
' apply -- goes through taddr so the bookkeeping cannot drift.
'
' Fill/commit/resync semantics are a port of lynx-client/src/bootstrap.c;
' see docs/PROTOCOL.md sections on TERRAIN_EDGE / WINDOW_ROW / WINDOW_COMMIT.

    DEF FN taddr(cx, cy) = (TERR + row_tab(row_base + (cy)) + (((cx) + col_off) AND 31))

row_tab:
    DATA 0,32,64,96,128,160,192,224,256,288,320,352
    DATA 384,416,448,480,512,544,576,608,640,672,704,736
    DATA 0,32,64,96,128,160,192,224,256,288,320,352
    DATA 384,416,448,480,512,544,576,608,640,672,704,736

bit_tab:
    DATA 1,2,4,8,16,32,64,128

' Window state

' ---------------------------------------------------------------------------
' ce_edge: TERRAIN_EDGE (type 3) in RTWS. Duplicate revision -> re-ack
' without shifting; expected revision (or trusted baseline) + geometrically
' adjacent strip -> ring-apply + ack; anything else -> resync request.
' ---------------------------------------------------------------------------
ce_edge: PROCEDURE
    #e_rev = (PEEK(RTWS + 10) AND 255) + (PEEK(RTWS + 11) AND 255) * 256
    IF #e_rev = #revision THEN
        GOSUB snd_ack
        RETURN
    END IF
    IF trust_next = 0 THEN
        ' expected = revision + 1, wrapping $FFFF -> 1 (never 0)
        #t0 = #revision + 1
        IF #t0 = 0 THEN #t0 = 1
        IF #e_rev <> #t0 THEN
            GOSUB ce_resync
            RETURN
        END IF
    END IF
    eo_x = PEEK(RTWS + 6) AND 255
    eo_y = PEEK(RTWS + 7) AND 255
    e_w = PEEK(RTWS + 8) AND 255

    IF e_w = 1 THEN
        ' 1x24 column strip; perpendicular origin must match exactly
        IF eo_y <> org_y THEN
            GOSUB ce_resync
            RETURN
        END IF
        IF eo_x = org_x - 1 THEN
            ' window moves left: new logical col 0
            col_off = (col_off + 31) AND 31
            org_x = org_x - 1
            cam_x = cam_x + 1
            e_c = 0
        ELSEIF eo_x = org_x + 32 THEN
            ' window moves right: new logical col 31
            col_off = (col_off + 1) AND 31
            org_x = org_x + 1
            cam_x = cam_x - 1
            e_c = 31
        ELSE
            GOSUB ce_resync
            RETURN
        END IF
        FOR e_i = 0 TO 23
            #t0 = PEEK(RTWS + 12 + e_i) AND 255
            POKE taddr(e_c, e_i), #t0
        NEXT e_i
    ELSE
        ' 32x1 row strip
        IF eo_x <> org_x THEN
            GOSUB ce_resync
            RETURN
        END IF
        IF eo_y = org_y - 1 THEN
            row_base = row_base + 23
            IF row_base >= 24 THEN row_base = row_base - 24
            org_y = org_y - 1
            cam_y = cam_y + 1
            e_c = 0
        ELSEIF eo_y = org_y + 24 THEN
            row_base = row_base + 1
            IF row_base >= 24 THEN row_base = row_base - 24
            org_y = org_y + 1
            cam_y = cam_y - 1
            e_c = 23
        ELSE
            GOSUB ce_resync
            RETURN
        END IF
        FOR e_i = 0 TO 31
            #t0 = PEEK(RTWS + 12 + e_i) AND 255
            POKE taddr(e_i, e_c), #t0
        NEXT e_i
    END IF

    #revision = #e_rev
    trust_next = 0
    resync_pending = 0
    ' The camera counter-shift above keeps the same world cells on screen, so
    ' no repaint is needed -- unless the shift pushed cam out of range, in
    ' which case cm_track clamps and triggers the repaint.
    IF cam_x > CAM_MAX_X THEN cam_x = CAM_MAX_X : repaint_full = 1
    IF cam_x = 255 THEN cam_x = 0 : repaint_full = 1
    IF cam_y > CAM_MAX_Y THEN cam_y = CAM_MAX_Y : repaint_full = 1
    IF cam_y = 255 THEN cam_y = 0 : repaint_full = 1
    GOSUB snd_ack
END

' ---------------------------------------------------------------------------
' ce_resync: ask the server for a fresh window (or the missing rows of an
' in-progress fill). Sets trust_next so the first edge after recovery is
' accepted as a new baseline -- without this, recovery loops forever
' (the server's revision counter is never rewound; lynx README:144).
' ---------------------------------------------------------------------------
ce_resync: PROCEDURE
    trust_next = 1
    resync_pending = 1
    #retry_frame = FRAME
    GOSUB snd_resync
END

' ---------------------------------------------------------------------------
' ce_fill_row: WINDOW_ROW (type 16) in RTWS -> staging buffer. A row whose
' fill_id or derived origin differs from the fill in progress supersedes it.
' On all 24 rows: activate.
' ---------------------------------------------------------------------------
ce_fill_row: PROCEDURE
    eo_x = PEEK(RTWS + 6) AND 255       ' fill origin x
    eo_y = PEEK(RTWS + 7) AND 255       ' ABSOLUTE row y
    e_c = PEEK(RTWS + 8) AND 255        ' row_index 0-23
    IF e_c > 23 THEN RETURN
    eo_y = eo_y - e_c                   ' window origin y of this fill
    e_w = PEEK(RTWS + 9) AND 255        ' fill id
    IF fill_active = 0 THEN
        GOSUB cf_start
    ELSEIF e_w <> fill_id THEN
        GOSUB cf_start
    ELSEIF eo_x <> fill_ox THEN
        GOSUB cf_start
    ELSEIF eo_y <> fill_oy THEN
        GOSUB cf_start
    END IF
    ' duplicate row?
    e_i = bit_tab(e_c AND 7)
    IF e_c < 8 THEN
        IF (rows0 AND e_i) <> 0 THEN RETURN
        rows0 = rows0 + e_i
    ELSEIF e_c < 16 THEN
        IF (rows1 AND e_i) <> 0 THEN RETURN
        rows1 = rows1 + e_i
    ELSE
        IF (rows2 AND e_i) <> 0 THEN RETURN
        rows2 = rows2 + e_i
    END IF
    #t1 = STAGE + row_tab(e_c)          ' row_tab(0..23) = row*32, reused as mul32
    FOR e_i = 0 TO 31
        #t0 = PEEK(RTWS + 10 + e_i) AND 255
        POKE #t1 + e_i, #t0
    NEXT e_i
    IF rows0 = 255 THEN
        IF rows1 = 255 THEN
            IF rows2 = 255 THEN GOSUB ce_activate
        END IF
    END IF
END

cf_start: PROCEDURE
    fill_active = 1
    fill_id = e_w
    fill_ox = eo_x
    fill_oy = eo_y
    rows0 = 0
    rows1 = 0
    rows2 = 0
END

' ---------------------------------------------------------------------------
' ce_activate: staging -> active (768-byte copy, a one-time ~4 frame hitch
' during a load/resync freeze), adopt the fill origin, reset ring offsets,
' trust the next edge, start the WINDOW_COMMIT retry loop.
' ---------------------------------------------------------------------------
ce_activate: PROCEDURE
    FOR #t1 = 0 TO 767
        #t0 = PEEK(STAGE + #t1) AND 255
        POKE TERR + #t1, #t0
    NEXT #t1
    col_off = 0
    row_base = 0
    org_x = fill_ox
    org_y = fill_oy
    fill_active = 0
    trust_next = 1
    resync_pending = 0
    commit_pending = 1
    commit_fill = fill_id
    map_sync = 0
    repaint_full = 1
    #retry_frame = FRAME
    GOSUB snd_commit
END

' ---------------------------------------------------------------------------
' ce_retries: FRAME-based re-send of unacknowledged WINDOW_COMMIT / RESYNC.
' ---------------------------------------------------------------------------
ce_retries: PROCEDURE
    IF commit_pending = 0 THEN
        IF resync_pending = 0 THEN RETURN
    END IF
    IF (FRAME - #retry_frame) < RETRY_FRAMES THEN RETURN
    #retry_frame = FRAME
    IF commit_pending THEN GOSUB snd_commit
    IF resync_pending THEN GOSUB snd_resync
END

' st_commitack: WINDOW_COMMIT_ACK (type 22): [6]=fill_id [7]=ox [8]=oy
st_commitack: PROCEDURE
    IF commit_pending = 0 THEN RETURN
    IF (PEEK(RTWS + 6) AND 255) <> commit_fill THEN RETURN
    commit_pending = 0
END
