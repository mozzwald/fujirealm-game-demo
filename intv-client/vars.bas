' vars.bas -- every cross-module variable, declared before any code mentions
' one. IntyBASIC auto-registers a name at its first MENTION, and a later DIM
' of a registered name is an error -- so shared declarations must all come
' first (the fujitzee "declare shared globals early" lesson).
' fujinet.bas keeps its own DIMs; it is included before any file that touches
' its variables.

' --- shared temps (masked-PEEK staging; see the rules in frconst.bas)
    DIM #t0, #t1

' --- window / cache (cache.bas)
    DIM org_x, org_y            ' logical window origin (world tiles)
    DIM col_off, row_base       ' ring offsets
    DIM trust_next              ' accept next adjacent edge as a new baseline
    DIM commit_pending, commit_fill
    DIM resync_pending
    DIM fill_active, fill_id, fill_ox, fill_oy
    DIM rows0, rows1, rows2     ' 24-bit received-rows bitmap
    DIM map_id
    DIM eo_x, eo_y, e_w, e_i, e_c
    DIM #e_rev, #revision, #retry_frame

' --- player / world (state.bas)
    DIM px, py                  ' predicted player position (world tiles)
    DIM hp
    DIM world_tick, world_seen
    DIM ent_n, ent_hit(6)
    DIM rem_n, itm_n
    DIM #echo_seq, #last_server_seq
    DIM pq_n, pq_x(8), pq_y(8)
    DIM #pq_seq(8)
    DIM pr_ok, pr_i, pr_j
    DIM hud_hp, hud_max, hud_lvl, hud_pvp
    DIM #hud_gold
    DIM msg_len, msg_off, msg_wait
    DIM q_len
    DIM msg_dirty
    DIM dlg_active, dlg_id, dlg_page, dlg_flags, dlg_len
    DIM dlg_next, dlg_speaker, dlg_dirty, dlg_ack_id, dlg_ack_page
    DIM map_sync
    DIM sw_i, sw_x, sw_y
    DIM dc_idx

' --- renderer (render.bas)
    DIM cam_x, cam_y
    DIM repaint_full, hud_dirty
    DIM shd_col(15), shd_row(15), shd_n
    DIM rf_r, rf_c, rf_c0, rf_dst
    DIM sp_x, sp_y, sp_i
    DIM #sp_w
    DIM facing
    DIM anim
    DIM dbg_on
    DIM cm_t
    DIM rm_i, rm_ch, rm_n2
    DIM #dg_last, dg_delta
    DIM rd_row

' --- input (input.bas)
    DIM ig_dir                  ' 0-7 wire facing, 255 = none
    DIM aim
    DIM mv_nx, mv_ny
    DIM move_last_world
    DIM fire_latch, pickup_latch
    DIM fire_ctr, pickup_ctr, pvp_ctr
    DIM btn_bits
    DIM ps_dirty
    DIM key_prev

' --- realtime codec (rt.bas)
    DIM acc_len                 ' bytes accumulated in RXACC (81 = overflow)
    DIM rx_drops                ' rejected frames (reported in PLAYER_STATE)
    DIM w_type, w_status
    DIM raw_len
    DIM crc_h, crc_l, crc_x
    DIM tx_pay, tx_type, tx_status
    DIM #client_seq
    DIM #rx_i, #rx_n
    DIM rf_i, rf_rd, rf_wr, rf_code
    DIM tf_i, tf_code_pos, tf_code

' --- bootstrap (bootstrap.bas)
    DIM bf_len, bf_want, bf_b
    DIM bs_mask, bs_done, welcome_seen
    DIM #bs_tick, #bs_sum
    DIM bs_i, bs_row, bs_tries
    DIM #bs_quiet, #bs_start
    DIM lg_status, lg_seen

' --- login / identity (login.bas)
    DIM id_ok
    DIM tok0, tok1, tok2, tok3
    DIM il_i, il_j, il_c
    DIM ne_buf(8), ne_cur, ne_len, inp_lock
    DIM lg_tries

' --- sound (sound.bas)
    DIM sfx_id, sfx_t

' --- main loop (fujirealm.bas)
    DIM online
    DIM map_banner
    DIM #hb_frame, #ow_frame
