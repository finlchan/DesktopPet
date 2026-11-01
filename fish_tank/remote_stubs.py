"""Phase 2 online hooks — local no-ops / TODO stubs only.

Do **not** ship a public fish-tank server in Phase 1.
Locked sync model (plan):
- Care / local deltas → flush on server 30 min settlement.
- Catch / trade / gift / drop-to-public-sea → immediate APIs.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Settlement (every 30 minutes on public server — Phase 2)
# ---------------------------------------------------------------------------

SETTLEMENT_INTERVAL_SEC = 30 * 60  # 30 minutes — server-side in Phase 2


def flush_care_deltas_for_settlement(local_deltas: Dict[str, Any]) -> None:
    """TODO(Phase 2): POST care/local deltas to public settlement endpoint.

    Phase 1: no-op. Local simulation already applied feed/decor/name locally.
    """
    _ = local_deltas
    return None


def on_settlement_tick_stub() -> Optional[Dict[str, Any]]:
    """TODO(Phase 2): pull settlement result (visitors assigned to active tanks).

    Phase 1: returns None (no visitors from public sea).
    """
    return None


# ---------------------------------------------------------------------------
# Immediate APIs (catch / trade / gift / drop) — Phase 2
# ---------------------------------------------------------------------------

def upload_catch_immediate(fish_payload: Dict[str, Any]) -> Dict[str, Any]:
    """TODO(Phase 2): immediate server upload on catch (same class as trade).

    Phase 1: local ownership stub — echo payload with ``ok: True``, ``local: True``.
    """
    return {"ok": True, "local": True, "fish": fish_payload}


def trade_immediate(_offer: Dict[str, Any]) -> Dict[str, Any]:
    """TODO(Phase 2): immediate trade (blocked offline). Phase 1: stub reject."""
    return {"ok": False, "error": "phase1_stub_no_public_server"}


def gift_immediate(_gift: Dict[str, Any]) -> Dict[str, Any]:
    """TODO(Phase 2): immediate gift / ownership transfer. Phase 1: stub reject."""
    return {"ok": False, "error": "phase1_stub_no_public_server"}


def drop_to_public_sea_immediate(_fish_id: str) -> Dict[str, Any]:
    """TODO(Phase 2): player release → unowned public sea. Phase 1: stub reject."""
    return {"ok": False, "error": "phase1_stub_no_public_server"}


def fetch_public_sea_visitors_stub() -> list:
    """TODO(Phase 2): wild visitors from public sea. Phase 1: empty list."""
    return []
