<?php
declare(strict_types=1);

const SESSIONS_PATH = __DIR__ . '/sessions.json';
const MAP_DATA_PATH = __DIR__ . '/map_data.json';
// Written by hybrid_server.py --positions-file. Optional: without it the map
// falls back to the positions saved in sessions.json, which are only as fresh
// as the last thing that marked a player dirty (level, gold, quest, logout).
const POSITIONS_PATH = __DIR__ . '/positions.json';
// A snapshot older than this is treated as "the server is not writing it any
// more" rather than shown as current.
const POSITIONS_MAX_AGE = 120;

function clamp_int($value, int $min, int $max): int
{
    if (is_bool($value)) {
        $value = (int) $value;
    } elseif (!is_int($value) && !is_float($value)) {
        $value = 0;
    }
    return max($min, min($max, (int) $value));
}

function load_players(string $path): array
{
    if (!is_readable($path)) {
        return [];
    }
    $raw = file_get_contents($path);
    if ($raw === false || trim($raw) === '') {
        return [];
    }
    $data = json_decode($raw, true);
    if (!is_array($data) || !isset($data['sessions']) || !is_array($data['sessions'])) {
        return [];
    }
    $players = [];
    foreach ($data['sessions'] as $record) {
        if (!is_array($record)) {
            continue;
        }
        $username = trim((string) ($record['username'] ?? ''));
        $state = $record['player_state'] ?? null;
        if ($username === '' || !is_array($state)) {
            continue;
        }
        $players[] = [
            'username' => $username,
            'online' => (bool) ($record['online'] ?? false),
            'level' => clamp_int($state['level'] ?? 1, 1, 99),
            'gold' => clamp_int($state['gold'] ?? 0, 0, 9999),
            'kills' => clamp_int($state['pvp_kills'] ?? 0, 0, 9999),
        ];
    }
    usort($players, static function (array $a, array $b): int {
        return ($b['kills'] <=> $a['kills'])
            ?: ($b['level'] <=> $a['level'])
            ?: strcasecmp($a['username'], $b['username']);
    });
    return $players;
}

function load_map_data(string $path): ?array
{
    if (!is_readable($path)) {
        return null;
    }
    $data = json_decode((string) file_get_contents($path), true);
    if (!is_array($data) || !isset($data['maps']) || !is_array($data['maps'])) {
        return null;
    }
    return $data;
}

/**
 * Where every online player is right now.
 *
 * Prefers the live snapshot the server writes with --positions-file. Falls
 * back to sessions.json, whose x/y is only written when something marks the
 * player dirty -- so those coordinates can be arbitrarily old, and the page
 * says so rather than pretending otherwise.
 *
 * @return array{players: array, live: bool, age: ?int}
 */
function load_positions(string $live_path, string $sessions_path): array
{
    if (is_readable($live_path)) {
        $data = json_decode((string) file_get_contents($live_path), true);
        if (is_array($data) && isset($data['players']) && is_array($data['players'])) {
            $age = time() - (int) ($data['generated_at'] ?? 0);
            if ($age <= POSITIONS_MAX_AGE) {
                $players = [];
                foreach ($data['players'] as $record) {
                    if (!is_array($record)) {
                        continue;
                    }
                    $username = trim((string) ($record['username'] ?? ''));
                    if ($username === '') {
                        continue;
                    }
                    $players[] = [
                        'username' => $username,
                        'map_id' => clamp_int($record['map_id'] ?? 0, 0, 255),
                        'x' => clamp_int($record['x'] ?? 0, 0, 255),
                        'y' => clamp_int($record['y'] ?? 0, 0, 255),
                        'level' => clamp_int($record['level'] ?? 1, 1, 99),
                        'health' => clamp_int($record['health'] ?? 0, 0, 999),
                        'max_health' => clamp_int($record['max_health'] ?? 0, 0, 999),
                        'gold' => clamp_int($record['gold'] ?? 0, 0, 9999),
                        'kills' => clamp_int($record['pvp_kills'] ?? 0, 0, 9999),
                        'pvp' => (bool) ($record['pvp_enabled'] ?? false),
                    ];
                }
                return ['players' => $players, 'live' => true, 'age' => max(0, $age)];
            }
        }
    }

    // Fallback: last saved position of whoever sessions.json thinks is online.
    $players = [];
    if (is_readable($sessions_path)) {
        $data = json_decode((string) file_get_contents($sessions_path), true);
        foreach (($data['sessions'] ?? []) as $record) {
            if (!is_array($record) || !($record['online'] ?? false)) {
                continue;
            }
            $state = $record['player_state'] ?? null;
            $username = trim((string) ($record['username'] ?? ''));
            if ($username === '' || !is_array($state)) {
                continue;
            }
            $players[] = [
                'username' => $username,
                'map_id' => clamp_int($state['map_id'] ?? 0, 0, 255),
                'x' => clamp_int($state['x'] ?? 0, 0, 255),
                'y' => clamp_int($state['y'] ?? 0, 0, 255),
                'level' => clamp_int($state['level'] ?? 1, 1, 99),
                'health' => clamp_int($state['health'] ?? 0, 0, 999),
                'max_health' => clamp_int($state['max_health'] ?? 0, 0, 999),
                'gold' => clamp_int($state['gold'] ?? 0, 0, 9999),
                'kills' => clamp_int($state['pvp_kills'] ?? 0, 0, 9999),
                'pvp' => (bool) ($state['pvp_enabled'] ?? false),
            ];
        }
    }
    return ['players' => $players, 'live' => false, 'age' => null];
}

$players = load_players(SESSIONS_PATH);
$map_data = load_map_data(MAP_DATA_PATH);
$positions = load_positions(POSITIONS_PATH, SESSIONS_PATH);
$online_now = $positions['players'];
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FujiRealm Demo Stats</title>
<style>
:root {
  color-scheme: dark;
  --bg: #101510;
  --panel: #172217;
  --panel-2: #1e2b1e;
  --text: #e6f1d8;
  --muted: #9db58d;
  --line: #365033;
  --accent: #b4e06b;
  --gold: #f1c35b;
  --online: #72e06b;
  --offline: #d64d4d;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
}
main {
  width: min(920px, calc(100% - 24px));
  margin: 32px auto;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
header {
  padding: 22px 24px 16px;
  border-bottom: 1px solid var(--line);
  background: var(--panel-2);
}
h1 {
  margin: 0;
  font-size: 28px;
  letter-spacing: 0;
}
.subtitle {
  margin-top: 8px;
  color: var(--muted);
  font-size: 14px;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th, td {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(54, 80, 51, 0.75);
}
th {
  color: var(--accent);
  text-align: left;
  font-weight: 700;
  cursor: pointer;
  user-select: none;
}
th.num, td.num { text-align: right; }
th.status, td.status { text-align: center; }
tbody tr:nth-child(odd) { background: rgba(255, 255, 255, 0.025); }
tbody tr:hover { background: rgba(180, 224, 107, 0.08); }
tbody tr.top { background: rgba(241, 195, 91, 0.08); }
td.kills { color: var(--accent); font-weight: 700; }
td.gold { color: var(--gold); }
.status-dot {
  display: inline-block;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.18), 0 0 8px currentColor;
}
.status-dot.online { color: var(--online); background: var(--online); }
.status-dot.offline { color: var(--offline); background: var(--offline); }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.empty {
  padding: 32px 24px;
  color: var(--muted);
}
.map-section { padding: 20px 24px 24px; border-bottom: 1px solid var(--line); }
.map-head {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}
.map-title { color: var(--accent); font-weight: 700; }
.map-note { color: var(--muted); font-size: 13px; }
.map-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.map-tab {
  background: var(--panel-2);
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 5px 10px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.map-tab[aria-selected="true"] { color: var(--bg); background: var(--accent); border-color: var(--accent); font-weight: 700; }
.map-wrap { position: relative; line-height: 0; }
#map {
  width: 100%;
  height: auto;
  display: block;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: #0b0f0b;
  /* One canvas pixel per tile, scaled up: keep the pixels crisp. */
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  cursor: crosshair;
}
.map-pop {
  position: absolute;
  min-width: 150px;
  padding: 8px 10px;
  background: rgba(10, 16, 10, 0.97);
  border: 1px solid var(--accent);
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.5;
  pointer-events: none;
  transform: translate(-50%, calc(-100% - 12px));
  white-space: nowrap;
  z-index: 5;
}
.map-pop .who { color: var(--accent); font-weight: 700; }
.map-pop .row { color: var(--muted); }
.map-pop .row b { color: var(--text); font-weight: 400; }
.map-pop[hidden] { display: none; }
.map-legend { margin-top: 10px; color: var(--muted); font-size: 12px; }
.map-legend .dot {
  display: inline-block; width: 9px; height: 9px; border-radius: 50%;
  background: #fff36b; box-shadow: 0 0 0 1px #000; vertical-align: -1px; margin-right: 4px;
}
.map-legend .dot.pvp { background: #ff6bd6; }
</style>
</head>
<body>
<main>
  <header>
    <h1>FujiRealm Demo Stats</h1>
    <div class="subtitle">Lifetime PvP leaderboard</div>
  </header>
  <?php if ($map_data): ?>
    <section class="map-section">
      <div class="map-head">
        <div>
          <div class="map-title">World map</div>
          <div class="map-note">
            <?php if (!$online_now): ?>
              Nobody is online right now.
            <?php elseif ($positions['live']): ?>
              <?= count($online_now) ?> online, as of <?= (int) $positions['age'] ?>s ago. Reload for a newer snapshot.
            <?php else: ?>
              <?= count($online_now) ?> online, at their last <em>saved</em> position &mdash; positions are only
              written when a player levels, banks gold, advances a quest or logs out.
              Run the server with <code>--positions-file positions.json</code> for live ones.
            <?php endif; ?>
          </div>
        </div>
        <div class="map-tabs" id="map-tabs"></div>
      </div>
      <div class="map-wrap">
        <canvas id="map"></canvas>
        <div class="map-pop" id="map-pop" hidden></div>
      </div>
      <div class="map-legend">
        <span class="dot"></span>player
        <span style="margin-left:14px"><span class="dot pvp"></span>PvP enabled</span>
        <span style="margin-left:14px">Click a marker for details. Enemies and NPCs are not shown.</span>
      </div>
    </section>
    <script id="map-data" type="application/json"><?= json_encode([
        'maps' => $map_data['maps'],
        'players' => $online_now,
    ], JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?></script>
  <?php endif; ?>
  <?php if (!$players): ?>
    <div class="empty">No players yet.</div>
  <?php else: ?>
    <table id="stats">
      <thead>
        <tr>
          <th data-type="text">Username</th>
          <th class="status" data-type="num">Online</th>
          <th class="num" data-type="num">Level</th>
          <th class="num" data-type="num">Gold</th>
          <th class="num" data-type="num" data-dir="desc">PvP Kills ▼</th>
        </tr>
      </thead>
      <tbody>
      <?php foreach ($players as $index => $player): ?>
        <tr<?= $index < 3 ? ' class="top"' : '' ?>>
          <td><?= htmlspecialchars($player['username'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
          <td class="status" data-sort="<?= $player['online'] ? 1 : 0 ?>">
            <span class="status-dot <?= $player['online'] ? 'online' : 'offline' ?>" aria-hidden="true"></span>
            <span class="sr-only"><?= $player['online'] ? 'Online' : 'Offline' ?></span>
          </td>
          <td class="num"><?= $player['level'] ?></td>
          <td class="num gold"><?= $player['gold'] ?></td>
          <td class="num kills"><?= $player['kills'] ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
  <?php endif; ?>
</main>
<script>
// --- world map -------------------------------------------------------------
(() => {
  const source = document.getElementById('map-data');
  const canvas = document.getElementById('map');
  if (!source || !canvas) return;

  const data = JSON.parse(source.textContent);
  const pop = document.getElementById('map-pop');
  const tabs = document.getElementById('map-tabs');
  const ctx = canvas.getContext('2d');

  // Tile colours, matching the Godot client's placeholder palette so the two
  // views read the same. Ids are the shared contract in docs/TILE_ALLOCATION.md.
  const COLORS = {
    0:  '#387033',  // grass
    2:  '#1a4c1f',  // tree
    3:  '#5fbf5f',  // herb
    4:  '#2e5724',  // tree, damaged
    5:  '#6b4f2a',  // stump
    6:  '#ffe64d',  // bullet
    7:  '#1f1f24',  // border
    10: '#c8ccc0',  // road
    11: '#2659a6',  // water
    12: '#8c7359',  // building
    13: '#14141a',  // cave entrance
    14: '#8a8a8a',  // grave
    15: '#2a2a2a',  // cave floor
    16: '#4d474d',  // cave wall
    17: '#d9c77a',  // cave exit
  };

  // Same fallback the client uses for ids it has no colour for: a stable hue
  // per id, so an unexpected tile shows as a pattern rather than vanishing.
  const fallback = (id) => {
    const hue = ((id * 0.137) % 1) * 360;
    return `hsl(${hue.toFixed(1)} 25% 55%)`;
  };
  const colorFor = (id) => COLORS[id] ?? (id > 0 ? fallback(id) : '#387033');

  const decode = (b64) => {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  };

  const mapIds = Object.keys(data.maps).sort((a, b) => Number(a) - Number(b));
  const countOn = (id) => data.players.filter(p => String(p.map_id) === String(id)).length;
  // Open on whichever map has people on it.
  let current = mapIds.reduce((best, id) => (countOn(id) > countOn(best) ? id : best), mapIds[0]);

  let tiles = null;
  let width = 0;
  let height = 0;
  let selected = null;

  const draw = () => {
    const map = data.maps[current];
    width = map.width;
    height = map.height;
    canvas.width = width;
    canvas.height = height;
    tiles = decode(map.tiles);

    const image = ctx.createImageData(width, height);
    const probe = document.createElement('canvas').getContext('2d');
    const cache = new Map();
    for (let i = 0; i < tiles.length; i++) {
      let rgb = cache.get(tiles[i]);
      if (!rgb) {
        // Resolve the colour string to bytes once per distinct tile id.
        probe.fillStyle = colorFor(tiles[i]);
        const hex = probe.fillStyle;
        rgb = hex.startsWith('#')
          ? [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)]
          : [56, 112, 51];
        cache.set(tiles[i], rgb);
      }
      image.data[i * 4] = rgb[0];
      image.data[i * 4 + 1] = rgb[1];
      image.data[i * 4 + 2] = rgb[2];
      image.data[i * 4 + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);

    // Players on top, as 3x3 blips so they survive the downscale to one
    // pixel per tile. Drawn after the terrain so they always win.
    for (const player of playersHere()) {
      ctx.fillStyle = '#000';
      ctx.fillRect(player.x - 1, player.y - 1, 3, 3);
      ctx.fillStyle = player.pvp ? '#ff6bd6' : '#fff36b';
      ctx.fillRect(player.x, player.y, 1, 1);
      ctx.fillRect(player.x - 1, player.y, 1, 1);
      ctx.fillRect(player.x + 1, player.y, 1, 1);
      ctx.fillRect(player.x, player.y - 1, 1, 1);
      ctx.fillRect(player.x, player.y + 1, 1, 1);
    }
  };

  const playersHere = () => data.players.filter(p => String(p.map_id) === String(current));

  const renderTabs = () => {
    tabs.innerHTML = '';
    for (const id of mapIds) {
      const button = document.createElement('button');
      button.className = 'map-tab';
      button.type = 'button';
      const here = countOn(id);
      button.textContent = here ? `${data.maps[id].name} (${here})` : data.maps[id].name;
      button.setAttribute('aria-selected', String(id === current));
      button.addEventListener('click', () => {
        current = id;
        selected = null;
        pop.hidden = true;
        renderTabs();
        draw();
      });
      tabs.appendChild(button);
    }
  };

  // Canvas pixel under the pointer, independent of how far the CSS scaled it.
  const tileAt = (event) => {
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.floor((event.clientX - rect.left) / rect.width * width),
      y: Math.floor((event.clientY - rect.top) / rect.height * height),
    };
  };

  const showPopup = (player) => {
    const rect = canvas.getBoundingClientRect();
    const hp = player.max_health ? `${player.health}/${player.max_health}` : String(player.health);
    pop.innerHTML = '';
    const who = document.createElement('div');
    who.className = 'who';
    who.textContent = player.username;
    pop.appendChild(who);
    for (const [label, value] of [
      ['Level', player.level], ['HP', hp], ['Gold', player.gold],
      ['PvP kills', player.kills], ['At', `${player.x},${player.y}`],
    ]) {
      const row = document.createElement('div');
      row.className = 'row';
      row.append(`${label} `);
      const strong = document.createElement('b');
      strong.textContent = String(value);
      row.appendChild(strong);
      pop.appendChild(row);
    }
    pop.style.left = `${(player.x + 0.5) / width * rect.width}px`;
    pop.style.top = `${(player.y + 0.5) / height * rect.height}px`;
    pop.hidden = false;
  };

  canvas.addEventListener('click', (event) => {
    const at = tileAt(event);
    // Generous hit radius: one tile is a couple of screen pixels at most.
    let best = null;
    let bestDistance = Infinity;
    for (const player of playersHere()) {
      const distance = Math.max(Math.abs(player.x - at.x), Math.abs(player.y - at.y));
      if (distance < bestDistance) {
        bestDistance = distance;
        best = player;
      }
    }
    if (best && bestDistance <= 3) {
      selected = best;
      showPopup(best);
    } else {
      selected = null;
      pop.hidden = true;
    }
  });

  window.addEventListener('resize', () => {
    if (selected) showPopup(selected);
  });

  renderTabs();
  draw();
})();

// --- sortable leaderboard --------------------------------------------------
(() => {
  const table = document.getElementById('stats');
  if (!table) return;
  const headers = [...table.tHead.rows[0].cells];
  const body = table.tBodies[0];
  headers.forEach((header, column) => {
    header.addEventListener('click', () => {
      const type = header.dataset.type || 'text';
      const dir = header.dataset.dir === 'asc' ? 'desc' : 'asc';
      headers.forEach(h => {
        h.dataset.dir = '';
        h.textContent = h.textContent.replace(/[ ▲▼]$/u, '');
      });
      header.dataset.dir = dir;
      header.textContent += dir === 'asc' ? ' ▲' : ' ▼';
      const rows = [...body.rows];
      rows.sort((a, b) => {
        const av = a.cells[column].dataset.sort ?? a.cells[column].textContent.trim();
        const bv = b.cells[column].dataset.sort ?? b.cells[column].textContent.trim();
        const cmp = type === 'num' ? Number(av) - Number(bv) : av.localeCompare(bv, undefined, { sensitivity: 'base' });
        return dir === 'asc' ? cmp : -cmp;
      });
      rows.forEach(row => body.appendChild(row));
    });
  });
})();
</script>
</body>
</html>
