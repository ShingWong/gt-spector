"""Tutorial-aware navigation wrapper (PROPOSAL — untracked, for review).

Wiring point (see Navigator.goto in navigator.py): identify() returns KNOWN
screen names even mid-tutorial (hero_details + banner), so the tutorial check
must run on every goto() entry AND after every hop landing — not just on None.
Placement when merged:
  1. goto(): after `current = identify()`, before the None-recover.
  2. goto(): after each `_resolve_hop` landing (covers tutorials triggered
     mid-route by conditions, e.g. first-time panel opens).
  3. _recover_esc(): if still None after MAX_ESC, run tutorial check before
     giving up (a tutorial overlay can mask all templates).

Detection order per check (cheapest first):
  L1 fixed-banner template patches (ms, CPU) -> L2 contour+EG2 crop naming
  for unknown overlays -> L3 Qwen verdict (seconds, rare).
Finish: follow script (path 1) or single SKIP-out (path 2 BLOCKED), then
re-identify and resume the original route from the new screen.
"""

from __future__ import annotations


def tutorial_check(session, gw):
    """Returns 'clear' | 'tutorial' | 'unknown-overlay'.

    L1 here is a stub: caller passes banner-hit test results. Full version
    imports tutorial_guard.check() once merged (same package).
    """
    try:
        from gt_spector import tutorial_guard  # merged name (no _PROPOSAL)
    except ImportError:
        return "clear", None
    frame = session.frame
    res = tutorial_guard.check(frame)
    if res["fixed"] or res["banners"]:
        return "tutorial", res
    if res["dialogs"]:
        return "unknown-overlay", res
    return "clear", res


def goto_with_tutorial(nav, target, follow_fn=None):
    """Drop-in around Navigator.goto: clears tutorials then delegates.

    follow_fn(session, gw) -> post-tutorial screen or None. If None and the
    tutorial persists, returns the stuck screen (never loops).
    """
    state, _ = tutorial_check(nav._session, nav._gw)
    if state != "clear":
        if follow_fn is None:
            return nav._gw.identify(nav._session)
        cleared = follow_fn(nav._session, nav._gw)
        if cleared is None:
            return nav._gw.identify(nav._session)
    return nav.goto(target)
