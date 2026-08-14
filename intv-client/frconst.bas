' frconst.bas -- FujiRealm client constants: screen layout, cart RAM map,
' protocol numbers, timing. Included first so every other file can use these.
'
' CODING RULES (IntyBASIC v1.4.2 landmines -- apply in every file):
'  - PEEK returns 16 bits; cart RAM upper bytes are garbage on real hardware.
'    Mask inside a larger expression is safe: (PEEK(a) AND 255) = n.
'    A BARE load into an 8-bit var silently drops the mask -- go through a
'    16-bit temp:  #t0 = PEEK(a) AND 255 : v = #t0
'  - Parenthesize (PEEK(x) AND 255) fully; '=' binds tighter than AND.
'  - Nest IFs instead of AND-chaining comparisons that contain DEF FNs.
'  - PRINT numbers with <.n>, never <n>.
'  - SOUND channel argument must be a literal constant.
'  - Wait for CONT1.KEY = 12 before accepting a new keypad press.
'  - Keep GOSUB nesting <= 8 (24-word stack shared with the ISR).

' ---------------------------------------------------------------------------
' Colors (color stack mode foreground values; pastels 8-15 need +$1000 in the
' BACKTAB word, which the generated gfx tables already bake in).
' ---------------------------------------------------------------------------
    CONST CS_BLACK      = 0
    CONST CS_BLUE       = 1
    CONST CS_RED        = 2
    CONST CS_TAN        = 3
    CONST CS_DARKGREEN  = 4
    CONST CS_GREEN      = 5
    CONST CS_YELLOW     = 6
    CONST CS_WHITE      = 7

    CONST COL_TEXT    = CS_WHITE
    CONST COL_DIM     = CS_TAN
    CONST COL_HILITE  = CS_YELLOW
    CONST COL_ERROR   = CS_RED

' Decoded keypad values (CONT.KEY)
    CONST KEYPAD_CLEAR  = 10
    CONST KEYPAD_ENTER  = 11
    CONST KEYPAD_NONE   = 12

' ---------------------------------------------------------------------------
' Screen layout: 20x12 cards. Rows 0-9 = 20x10 tile viewport (the house
' standard shared with the Atari and Lynx clients), row 10 = HUD stats,
' row 11 = message/quest marquee.
' ---------------------------------------------------------------------------
    CONST SCREEN_COLS = 20
    DEF FN screenpos(aColumn, aRow) = (((aRow)*SCREEN_COLS)+(aColumn))

    CONST VIEW_COLS = 20
    CONST VIEW_ROWS = 10
    CONST HUD_ROW   = 10
    CONST MSG_ROW   = 11

' Terrain window (matches the server's per-client 32x24 sliding window)
    CONST WIN_W = 32
    CONST WIN_H = 24
    CONST CAM_MAX_X = 12        ' WIN_W - VIEW_COLS
    CONST CAM_MAX_Y = 14        ' WIN_H - VIEW_ROWS

    CONST WORLD_W = 128
    CONST WORLD_H = 96

' ---------------------------------------------------------------------------
' Cart RAM map ($8000-$9BFF is 8-bit cartridge RAM; $9100-$917F is
' fujinet.bas scratch; $9C00+ is the FujiNet mailbox). Nothing below $8100:
' the console's STIC alias sits at $8000-$803F and jzIntv's layered bus can
' let it answer ahead of cart RAM -- the example clients never touch that
' corner and neither do we.
' ---------------------------------------------------------------------------
    CONST TERR    = $8100       ' active terrain window, 768B, ring-addressed
    CONST STAGE   = $8400       ' window-fill staging, 768B, linear
    CONST RTWS    = $8700       ' decoded realtime frame workspace, 64B
    CONST RXACC   = $8740       ' encoded COBS frame accumulator, 80B
    CONST TXRAW   = $8790       ' raw outgoing frame build area, 32B
    CONST BFACC   = $87B0       ' $BF bootstrap frame accumulator, 120B
    CONST ENTBUF  = $8830       ' entities, 6 x {x,y,hp,kind}, 24B
    CONST REMBUF  = $8850       ' remote players, 4 x {x,y,facing,state}, 16B
    CONST ITMBUF  = $8860       ' item drops, 4 x {x,y,id,qty}, 16B
    CONST MSGBUF  = $8870       ' server MESSAGE text, 40B
    CONST QSTBUF  = $88A0       ' quest line text, 40B
    CONST DLGBUF  = $88D0       ' dialogue page reassembly, 144B
    CONST IDBUF   = $8960       ' identity record "user,token,host", 64B
    CONST TOKASC  = $89A0       ' token ASCII digits, 16B
    CONST NAMEBUF = $89B0       ' player name, 16B
    CONST TRCBUF  = $89C0       ' shot tracer {x0,y0,dir,len}, 4B
    CONST SHDBUF  = $89D0       ' stamp shadow list, 21 x {col,row}, 42B

' ---------------------------------------------------------------------------
' Realtime v3 protocol (COBS-framed, CRC-16/CCITT-FALSE; see docs/PROTOCOL.md
' and lynx-client/src/rt_state.h)
' ---------------------------------------------------------------------------
    CONST RT_VER            = 3
    CONST RTS_PLAYER_STATE  = 1
    CONST RTS_WORLD_STATE   = 2
    CONST RTS_TERRAIN_EDGE  = 3
    CONST RTS_BYE           = 4
    CONST RTS_MAP_CHANGE    = 5
    CONST RTS_HUD           = 7
    CONST RTS_MESSAGE       = 8
    CONST RTS_QUEST         = 9
    CONST RTS_INVENTORY     = 10
    CONST RTS_RESPAWN       = 11
    CONST RTS_AUTH          = 13
    CONST RTS_REMOTE        = 14
    CONST RTS_RESYNC        = 15
    CONST RTS_WINDOW_ROW    = 16
    CONST RTS_ITEMS         = 17
    CONST RTS_MAP_READY     = 19
    CONST RTS_COMMIT        = 20
    CONST RTS_STEP_ACK      = 21
    CONST RTS_COMMIT_ACK    = 22
    CONST RTS_DIALOGUE      = 24

' Dialogue page flags
    CONST DLG_QUEST_OFFER = 1
    CONST DLG_ACK_ONLY    = 2
    CONST DLG_LAST_PAGE   = 4
    CONST DLG_CHUNK_END   = 8

' $BF bootstrap/login framing
    CONST PKT_MAGIC      = $BF
    CONST PKT_VER        = 1
    CONST PT_HELLO       = $01
    CONST PT_WINDOW      = $80
    CONST PT_WELCOME     = $81
    CONST PT_LOGIN_REQ   = $A0
    CONST PT_LOGIN_RESP  = $A1

' ---------------------------------------------------------------------------
' Timing (frames, on the free-running 16-bit FRAME counter)
' ---------------------------------------------------------------------------
    CONST HEARTBEAT_FRAMES   = 15   ' bare PLAYER_STATE cadence (~250ms), Lynx-equal
    CONST RETRY_FRAMES       = 45   ' window-commit / resync re-send interval
    CONST HELLO_RETRY_FRAMES = 120  ' quiet time before re-sending HELLO
    CONST RX_CHUNK           = 192  ' net_read cap per loop iteration
