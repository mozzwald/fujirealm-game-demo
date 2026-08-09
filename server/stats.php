<?php
declare(strict_types=1);

const SESSIONS_PATH = __DIR__ . '/sessions.json';

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

$players = load_players(SESSIONS_PATH);
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
</style>
</head>
<body>
<main>
  <header>
    <h1>FujiRealm Demo Stats</h1>
    <div class="subtitle">Lifetime PvP leaderboard</div>
  </header>
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
