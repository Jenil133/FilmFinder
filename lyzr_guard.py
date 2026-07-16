"""Circuit breaker shared by both Lyzr agent call sites.

Why this exists: the Lyzr account has ~20 monthly credits TOTAL, and a dead or
exhausted Lyzr API doesn't fail fast — it costs the full request timeout
(6s parser + 8s scout) on EVERY search before the silent fallback kicks in.
The breaker converts "Lyzr is down/broke" from a per-search latency tax into
one cheap boolean check.

Behavior: after FAILURE_THRESHOLD consecutive failures, Lyzr calls are skipped
entirely for COOLDOWN_S (callers go straight to their fallbacks). After the
cooldown one probe call is allowed through (half-open); a single failure in
that state re-trips immediately, a success closes the breaker.

State is per-process, which matches Streamlit Community Cloud's single-process
model. Races under Streamlit's script threads are benign (worst case: one
extra probe call).
"""

import time

FAILURE_THRESHOLD = 3
COOLDOWN_S = 600.0  # 10 min: long enough to stop bleeding, short enough to recover mid-demo

_failures = 0
_disabled_until = 0.0
_tripped = False  # half-open memory: one failure after cooldown re-trips


def allowed() -> bool:
    """Cheap pre-check: should a Lyzr call be attempted right now?"""
    return time.monotonic() >= _disabled_until


def record(success: bool) -> None:
    """Report the outcome of an attempted Lyzr call."""
    global _failures, _disabled_until, _tripped
    if success:
        _failures = 0
        _tripped = False
    else:
        _failures += 1
        if _tripped or _failures >= FAILURE_THRESHOLD:
            _disabled_until = time.monotonic() + COOLDOWN_S
            _tripped = True
            _failures = 0


def reset() -> None:
    """Test hook / manual recovery."""
    global _failures, _disabled_until, _tripped
    _failures = 0
    _disabled_until = 0.0
    _tripped = False
