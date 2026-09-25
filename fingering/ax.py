"""macOS Accessibility helpers: find where a scroll should go.

Scroll events go to whatever is under the event's location. If the user pinches over something that
can't scroll (a toolbar, a sidebar header, a gap), we redirect the scroll to the nearest sensible
scrollable area in the same window, so "pinch and scroll" works anywhere in the window.
"""

import logging
import time
from collections import deque

from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCopyElementAtPosition,
    AXUIElementCreateSystemWide,
    AXUIElementSetMessagingTimeout,
    AXValueGetValue,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)

log = logging.getLogger(__name__)

SCROLLABLE = {"AXScrollArea", "AXWebArea"}
_SEARCH_BUDGET_S = 0.08
_MAX_NODES = 400

_system = AXUIElementCreateSystemWide()
AXUIElementSetMessagingTimeout(_system, 0.1)


def _attr(el, name):
    err, value = AXUIElementCopyAttributeValue(el, name, None)
    return value if err == 0 else None


def _frame(el):
    pos, size = _attr(el, "AXPosition"), _attr(el, "AXSize")
    if pos is None or size is None:
        return None
    ok1, p = AXValueGetValue(pos, kAXValueCGPointType, None)
    ok2, s = AXValueGetValue(size, kAXValueCGSizeType, None)
    if not (ok1 and ok2) or s.width <= 1 or s.height <= 1:
        return None
    return p.x, p.y, s.width, s.height


def _largest_scroll_area(window) -> tuple[float, float] | None:
    """Breadth-first search of the window for its biggest scrollable area (time/node bounded)."""
    deadline = time.perf_counter() + _SEARCH_BUDGET_S
    queue, seen, best, best_area = deque([window]), 0, None, 0.0
    while queue and seen < _MAX_NODES and time.perf_counter() < deadline:
        el = queue.popleft()
        seen += 1
        if _attr(el, "AXRole") in SCROLLABLE:
            f = _frame(el)
            if f and f[2] * f[3] > best_area:
                best, best_area = (f[0] + f[2] / 2, f[1] + f[3] / 2), f[2] * f[3]
            continue  # don't descend into scroll areas: the outer one is the page
        queue.extend(_attr(el, "AXChildren") or ())
    return best


def scroll_target(x: float, y: float) -> tuple[float, float]:
    """Where to post a scroll the user started at (x, y)."""
    try:
        err, el = AXUIElementCopyElementAtPosition(_system, x, y, None)
        window = None
        for _ in range(30):
            if err or el is None:
                break
            role = _attr(el, "AXRole")
            if role in SCROLLABLE:
                return x, y  # already over something scrollable
            if role == "AXWindow":
                window = el
                break
            el = _attr(el, "AXParent")
            err = 0 if el is not None else 1
        if window is not None:
            best = _largest_scroll_area(window)
            if best:
                log.debug("scroll redirected from (%.0f, %.0f) to (%.0f, %.0f)", x, y, *best)
                return best
    except Exception as e:  # accessibility is best-effort; never break scrolling
        log.debug("scroll_target failed: %s", e)
    return x, y
