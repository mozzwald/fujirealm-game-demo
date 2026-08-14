' FujiRealm -- Intellivision FujiNet client.
'
' A client for the FujiRealm server-authoritative multiplayer RPG
' (../server), speaking the same wire protocol as the Atari 8-bit and Lynx
' clients: $BF-framed login/bootstrap, then realtime v3 (COBS + CRC-16)
' over a plain N-device TCP connection through the FujiNet mailbox --
' no netstream, just polled NETCMD_STATUS/READ/WRITE.
'
' 20x10 tile viewport (the house standard) + 2 HUD rows, color stack mode,
' everything rendered as BACKTAB cards. Movement is client-predicted at one
' step per server tick. Without a FujiNet mailbox the client boots into an
' offline demo on a canned overworld slice.
'
' Build: make            (see README.md; SERVER_HOST is baked at build time)
' Run:   ./run.sh        (jzIntv --fujinet against a fujinet-pc RS232 build)

    GOTO boot_start

' Constants and declarations first (vars.bas holds every cross-module DIM;
' a name mentioned before its DIM would auto-register and break the DIM),
' then the modules -- execution jumps over all of it.
    INCLUDE "frconst.bas"
    INCLUDE "server_cfg.bas"
    INCLUDE "vars.bas"
    INCLUDE "fujinet.bas"
    INCLUDE "cache.bas"
    INCLUDE "state.bas"
    INCLUDE "render.bas"
    INCLUDE "input.bas"
    INCLUDE "rt.bas"
    INCLUDE "sound.bas"

boot_start:
    MODE 0,0,0,0,0
    WAIT
    GOSUB gfx_init
    CLS
    dlg_ack_id = 255
    facing = 1
    PRINT AT screenpos(3,2) COLOR COL_HILITE, "* FUJIREALM *"
    PRINT AT screenpos(1,6) COLOR COL_DIM, "CONNECTING FUJINET"
    GOSUB fn_wait_mailbox
    IF fn_ok = 0 THEN GOTO offline_start

    ' --- identity: cached appkey record, else name entry + login server
    PRINT AT screenpos(1,7) COLOR COL_DIM, "READING IDENTITY"
    GOSUB id_load
    IF id_ok = 0 THEN
        lg_tries = 0
retry_login:
        GOSUB name_entry
        CLS
        PRINT AT screenpos(3,5) COLOR COL_TEXT, "LOGGING IN..."
        GOSUB lg_login
        IF fn_ok = 0 THEN GOTO err_login
        IF lg_status <> 0 THEN
            lg_tries = lg_tries + 1
            IF lg_tries < 3 THEN
                CLS
                PRINT AT screenpos(3,5) COLOR COL_ERROR, "NAME TAKEN"
                FOR il_i = 0 TO 90
                    WAIT
                NEXT il_i
                GOTO retry_login
            END IF
            GOTO err_login
        END IF
        GOSUB id_store
    END IF
    GOSUB tok_parse

    ' --- game socket + bootstrap window transfer
    CLS
    PRINT AT screenpos(2,5) COLOR COL_TEXT, "CONNECTING WORLD"
    #fn_txlen = 0
    #fn_src = VARPTR game_url(0)
    fn_len = GAME_URL_LEN
    GOSUB fn_putstr
    GOSUB net_open
    IF fn_ok = 0 THEN GOTO err_net
    PRINT AT screenpos(2,6) COLOR COL_DIM, "LOADING REALM..."
    GOSUB bs_run
    IF fn_ok = 0 THEN GOTO err_net

    ' --- enter realtime: RT3\n + AUTH(seq 0) + first PLAYER_STATE(seq 1)
    ' batched into one write. The server sends no WORLD_STATE until it has
    ' seen a PLAYER_STATE; position is a guess the first WORLD_STATE fixes.
    px = org_x + 16
    py = org_y + 12
    #client_seq = 0
    POKE FN_TX + 0, 82          ' 'R'
    POKE FN_TX + 1, 84          ' 'T'
    POKE FN_TX + 2, 51          ' '3'
    POKE FN_TX + 3, 10          ' \n
    #fn_txlen = 4
    GOSUB snd_auth
    GOSUB snd_player_state
    GOSUB tx_flush
    online = 1
    GOTO game_setup

' ---------------------------------------------------------------------------
' Offline demo: no mailbox -> real overworld slice, local prediction only.
' ---------------------------------------------------------------------------
offline_start:
    online = 0
    FOR #t1 = 0 TO 767
        POKE TERR + #t1, testmap(#t1)
    NEXT #t1
    org_x = testmap_meta(0)
    org_y = testmap_meta(1)
    px = testmap_meta(2)
    py = testmap_meta(3)
    hud_hp = 10
    hud_max = 10
    hud_lvl = 1
    world_seen = 1
    msg_len = 12
    FOR il_i = 0 TO 11
        msg_off = offline_msg(il_i)
        POKE MSGBUF + il_i, msg_off
    NEXT il_i
    msg_off = 0

' ---------------------------------------------------------------------------
' Shared setup + main loop
' ---------------------------------------------------------------------------
game_setup:
    cam_x = 0
    cam_y = 0
    GOSUB cm_track
    repaint_full = 1
    hud_dirty = 1
    msg_dirty = 1
    CLS
    #hb_frame = FRAME

game_loop:
    WAIT

    ' --- receive: one status + one capped read per pass; the COBS
    ' accumulator carries partial frames across passes.
    IF online THEN
        GOSUB net_status
        ' Read on available bytes even when the status error byte is not
        ' SUCCESS (EOF still has readable buffered data; #net_avail is 0
        ' when the transaction itself failed).
        IF #net_avail > 0 THEN
            #net_readlen = RX_CHUNK
            IF #net_avail < RX_CHUNK THEN #net_readlen = #net_avail
            GOSUB net_read
            GOSUB rt_rx_pump
        END IF
    ELSE
        ' fake the 10 Hz world clock so the movement cadence works
        IF (FRAME - #ow_frame) >= 6 THEN
            #ow_frame = FRAME
            world_tick = world_tick + 1
        END IF
        pq_n = 0
    END IF

    ' --- input (or the modal that replaces it)
    IF map_sync THEN
        IF map_banner = 0 THEN
            map_banner = 1
            CLS
            PRINT AT screenpos(4,5) COLOR COL_TEXT, "ENTERING..."
        END IF
        GOTO gl_send
    END IF
    map_banner = 0
    IF dlg_active THEN
        GOSUB rn_dlg
        GOSUB dlg_input
        GOTO gl_send
    END IF
    GOSUB ig_poll
    GOSUB ig_move

gl_send:
    IF online THEN
        IF (FRAME - #hb_frame) >= HEARTBEAT_FRAMES THEN ps_dirty = 1
        IF ps_dirty THEN
            GOSUB snd_player_state
            #hb_frame = FRAME
            ps_dirty = 0
        END IF
        GOSUB ce_retries
        GOSUB tx_flush
    END IF

    ' --- render (suppressed while loading or in dialogue)
    IF map_sync THEN GOTO gl_end
    IF dlg_active THEN GOTO gl_end
    GOSUB cm_track
    IF repaint_full THEN
        GOSUB rn_full
        repaint_full = 0
    ELSE
        GOSUB rn_restore
    END IF
    GOSUB rn_stamp_all
    GOSUB rn_hud
    GOSUB rn_msg
gl_end:
    GOSUB sfx_tick
    GOTO game_loop

' ---------------------------------------------------------------------------
' Error stops
' ---------------------------------------------------------------------------
err_login:
    CLS
    PRINT AT screenpos(3,5) COLOR COL_ERROR, "LOGIN FAILED"
    GOTO halt

err_net:
    CLS
    PRINT AT screenpos(1,5) COLOR COL_ERROR, "CONNECTION FAILED"
    PRINT AT screenpos(1,7) COLOR COL_DIM, "CHECK SERVER + WIFI"
    GOTO halt

halt:
    WAIT
    GOTO halt

offline_msg:
    DATA 79,70,70,76,73,78,69,32,68,69,77,79       ' "OFFLINE DEMO"

' Boot-only code and cold data live in the $A000-$BFFF cartridge segment:
' the base 16K at $5000-$6FFF silently overflows into unsafe space otherwise
' (the fujitzee lesson -- its boot hung on real hardware from a 20-word
' spill jzIntv forgave). ROM speed is uniform, so placement is purely about
' fitting segments. VERIFY the generated .cfg maps nothing into $7000 after
' any code growth.
    ASM ORG $A000
    INCLUDE "bootstrap.bas"
    INCLUDE "login.bas"
    INCLUDE "crc_tab.bas"
    INCLUDE "gfx.bas"
    INCLUDE "testmap.bas"
