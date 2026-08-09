"""Persisted player-state schema version.

Lives in its own module so ``login_server`` (deliberately light: stdlib only,
no ``game`` import) and ``game`` can both reference it without a cycle.

``serialize_player_state`` stamps every save with this number. A record whose
``player_state`` carries a different number -- or none at all, which is every
record written before this module existed -- is from an older generation of the
game and is not worth migrating: ``tools/reset_old_sessions.py`` wipes it back
to a clean level-1 new game while keeping the token and username.

Bump this to force another such wipe of all pre-existing saves.
"""

from __future__ import annotations

PLAYER_SCHEMA_VERSION = 1
