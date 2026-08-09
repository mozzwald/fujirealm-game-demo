# FujiRealm MORPG Demo Protocol

This document summarizes the current FujiRealm Demo client/server protocol.  
The game uses TCP through FujiNet Netstream.

There are two protocol phases:

1. Login/resume and bootstrap use variable-length `$BF` packets.
2. Realtime gameplay uses realtime v3: COBS-framed, CRC-16-protected,
  zero-delimited compact frames (the fixed-size `$AD` v2 stream is  
   retired).

## `$BF` Packets

Bootstrap packets have this shape:

```text
magic, version, packet_type, payload_len, payload..., checksum
```

- `magic`: `$BF`
- `version`: `1`
- `payload_len`: 0-255 bytes
- `checksum`: sum of all previous bytes, low byte

Current important `$BF` packet types:

| Type  | Name              | Direction                 | Payload                          | Purpose                                           |
| ----- | ----------------- | ------------------------- | -------------------------------- | ------------------------------------------------- |
| `$A0` | `LOGIN_REQUEST`   | Client -> login server    | username                         | Ask for a new token.                              |
| `$A1` | `LOGIN_RESPONSE`  | Login server -> client    | status, token                    | Returns token or username-taken status.           |
| `$A2` | `RESUME_REQUEST`  | Client -> login server    | token                            | Resume an existing login token.                   |
| `$A3` | `RESUME_RESPONSE` | Login server -> client    | status, username                 | Confirms token and username.                      |
| `$01` | `HELLO`           | Client -> realtime server | flags, seed, token               | Starts bootstrap on the realtime socket.          |
| `$81` | `WELCOME`         | Server -> client          | player id, seed, limits, version | Confirms bootstrap.                               |
| `$80` | `WINDOW`          | Server -> client          | terrain chunk                    | Sends the initial 32x24 terrain window in chunks. |

After bootstrap, the client switches to realtime `$AD` packets on the same  
Netstream TCP connection.

## `$AD` Realtime Packets

Realtime v3 wire frames are `COBS(raw_frame)` followed by a `$00`  
delimiter. COBS guarantees no zero appears inside an encoded frame, so the  
next delimiter always realigns the parser after any byte loss, insertion,  
or corruption; a CRC failure costs exactly one delimiter-bounded frame.

A realtime connection identifies itself with the raw 4-byte preamble  
`RT3` + newline immediately after opening the stream, before the first  
framed `AUTH`.

Raw frame layout (maximum 62 bytes: 54-byte payload ceiling):

```text
offset 0    payload_length N
offset 1    version = 3
offset 2    realtime_type
offset 3    status/count
offset 4-5  seq (16-bit, little endian)
offset 6..  payload (N bytes)
6+N, 7+N    CRC-16/CCITT-FALSE over bytes 0..5+N, little endian
```

Trailing zero bytes of the payload are stripped on encode and re-padded on  
decode, so frames are sent compact; the per-type field offsets below are  
unchanged from v2. The sizes in the table are the legacy v2 workspace  
classes and now serve only as field-capacity bounds.

## Realtime Packet Summary

| Type | Name                | Size | Direction        | Sends                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---- | ------------------- | ---- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `1`  | `PLAYER_STATE`      | 32   | Client -> server | Player x/y, facing, buttons, fire counter, pickup counter, last server seq, client RX drop counter, PvP toggle counter.                                                                                                                                                                                                                                                                                                                                                                                                 |
| `13` | `AUTH`              | 32   | Client -> server | 32-bit token. Also used as a keepalive.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `15` | `RESYNC_REQUEST`    | 32   | Client -> server | Client window origin, fill origin, and row mask for terrain resync.                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `19` | `MAP_READY`         | 32   | Client -> server | Map id and window origin after client finishes a map transition.                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `12` | `PLAYER_COMMAND`    | 32   | Client -> server | Generic command, direction, args, and last server seq. Mostly future-facing.                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `2`  | `WORLD_STATE`       | 64   | Server -> client | Authoritative player x/y/health, correction flag, echoed client seq, one tile update, and up to 6 enemy snapshots.                                                                                                                                                                                                                                                                                                                                                                                                      |
| `3`  | `TERRAIN_EDGE`      | 64   | Server -> client | One acknowledged cache step: a relative row/column strip plus a 16-bit revision (bytes 10-11). Up to 3 chained steps are pipelined (go-back-N); ACKs are cumulative and the window origin advances server-side only on ACKs. A client receiving a non-adjacent follower re-ACKs its applied state, and the server fast-retransmits the pipeline on that duplicate ACK; otherwise unacknowledged steps retransmit byte-identically oldest-first on a 0.5 s timer, escalating to a full window fill after 4 timer rounds. |
| `16` | `WINDOW_ROW`        | 64   | Server -> client | One absolute 32-tile terrain row for full-window resync or map transition.                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `5`  | `MAP_CHANGE`        | 32   | Server -> client | New map id, spawn x/y, tileset id, palette id, flags.                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `7`  | `HUD_UPDATE`        | 32   | Server -> client | HP, max HP, level, XP, next XP, gold, flags, PvP kills.                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `8`  | `MESSAGE`           | 64   | Server -> client | Message id and up to 39 uppercase display characters.                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `9`  | `QUEST_UPDATE`      | 64   | Server -> client | Quest id, state, and up to 39 uppercase display characters.                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `10` | `INVENTORY_UPDATE`  | 32   | Server -> client | Gold plus up to 8 item slots.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `11` | `RESPAWN_EVENT`     | 32   | Server -> client | Map id, x/y, HP, max HP, message id, flags.                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `14` | `REMOTE_PLAYERS`    | 64   | Server -> client | Up to 12 remote player records: x, y, facing, state.                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `17` | `ITEM_DROPS`        | 32   | Server -> client | Up to 4 visible item drops: x, y, item id, quantity.                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `18` | `MAP_SUMMARY`       | 64   | Server -> client | Compact map-summary cells for the map modal.                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `4`  | `BYE`               | 32   | Either           | Disconnect marker.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `6`  | `ENTITY_DELTA`      | 64   | Server -> client | Generic entity delta records. Mostly legacy/future-facing.                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `20` | `WINDOW_COMMIT`     | 32   | Client -> server | Fill id, committed origin, map id: the client owns the streamed window.                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `21` | `CACHE_STEP_ACK`    | 32   | Client -> server | Applied cache-step revision plus committed window origin.                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `22` | `WINDOW_COMMIT_ACK` | 32   | Server -> client | Confirms a WINDOW_COMMIT; stops the client's commit retry.                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `23` | `NET_STATS`         | 32   | Client -> server | Link-health telemetry (~every 4 s): frame drops, handler overflow/serial counters, fill/commit state, origin, cache revision.                                                                                                                                                                                                                                                                                                                                                                                           |

### `PLAYER_STATE` / `REMOTE_PLAYERS` facing byte

The unchanged one-byte facing field uses these values:

| Value | Direction  |
| ----- | ---------- |
| `0`   | Up         |
| `1`   | Down       |
| `2`   | Left       |
| `3`   | Right      |
| `4`   | Up-left    |
| `5`   | Up-right   |
| `6`   | Down-left  |
| `7`   | Down-right |

Values `4-7` are joystick-shot facings. Keyboard controls continue to produce only `0-3`; invalid values do not create a server shot. The `PLAYER_STATE` and four-byte `REMOTE_PLAYERS` record layouts are unchanged.

### `REMOTE_PLAYERS` state byte

Each four-byte remote-player record is `x, y, facing, state`. The state byte  
uses:

| Bits  | Meaning                                                |
| ----- | ------------------------------------------------------ |
| `0`   | Player is alive/present.                               |
| `1`   | Player has PvP enabled.                                |
| `2-3` | Low two bits of the server-side accepted-shot counter. |
| `4-7` | Reserved; currently zero.                              |

The server increments the shot counter once when a valid-direction fire is  
accepted. A client that observes bits 2-3 change on an already-occupied remote  
slot spawns a cosmetic tracer from that record's position and facing. A newly  
occupied slot establishes its counter baseline without drawing a tracer.  
Damage and hit resolution remain server-authoritative; tracers never apply  
damage. The packet and record sizes are unchanged, although a state-only  
counter change can trigger another change-driven `REMOTE_PLAYERS` packet.

## Gameplay Notes

- The server is authoritative for movement, collision, health, enemies, item  
pickup, XP, gold, quests, PvP kills, and map transitions.
- The client sends intent/state frequently through `PLAYER_STATE`.
- The server sends `WORLD_STATE` every tick for correction and enemy data.
- Terrain normally scrolls through `TERRAIN_EDGE`.
- If terrain gets out of sync, the client requests a resync and the server  
streams `WINDOW_ROW` packets until the 32x24 window is restored.
- The client reports its local realtime parser drop counter in every  
`PLAYER_STATE`; the server logs deltas as `net_rx_drops`.
