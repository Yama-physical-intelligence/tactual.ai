"""macOS actuator: posts native Quartz events (sub-millisecond, real click state, drag events)."""

import logging
import time

import Quartz as Q

from .actions import Action, Click, MouseButton, MoveCursor, Notice, Scroll, Shortcut

log = logging.getLogger(__name__)

_CTRL = Q.kCGEventFlagMaskControl
_CMD = Q.kCGEventFlagMaskCommand
# Arrow keys need the Fn + NumericPad flags for Mission Control / Spaces shortcuts to fire.
_ARROW = Q.kCGEventFlagMaskSecondaryFn | Q.kCGEventFlagMaskNumericPad

# name -> (virtual keycode, modifier flags)
SHORTCUTS = {
    "space_left": (123, _CTRL | _ARROW),
    "space_right": (124, _CTRL | _ARROW),
    "app_windows": (125, _CTRL | _ARROW),
    "mission_control": (126, _CTRL | _ARROW),
    "zoom_in": (24, _CMD),  # cmd + '='
    "zoom_out": (27, _CMD),  # cmd + '-'
}

_BUTTONS = {
    "left": (Q.kCGMouseButtonLeft, Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp),
    "right": (Q.kCGMouseButtonRight, Q.kCGEventRightMouseDown, Q.kCGEventRightMouseUp),
}


def accessibility_trusted(prompt: bool = True) -> bool:
    """True if this process may post input events; optionally shows the macOS permission prompt."""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
    except ImportError:
        return True
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))


class MacController:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        bounds = Q.CGDisplayBounds(Q.CGMainDisplayID())
        self.screen_size = (int(bounds.size.width), int(bounds.size.height))
        loc = Q.CGEventGetLocation(Q.CGEventCreate(None))
        self._pos = (loc.x, loc.y)
        self._left_down = False
        self.smart_scroll = True
        self._scroll_at: tuple[float, float] | None = None
        self._last_scroll_t = 0.0

    def execute(self, action: Action) -> None:
        if isinstance(action, Notice):
            log.info(action.text)
            return
        if self.dry_run:
            if not isinstance(action, MoveCursor):
                log.info("[dry-run] %s", action)
            return
        if isinstance(action, MoveCursor):
            self._pos = (action.x, action.y)
            kind = Q.kCGEventLeftMouseDragged if self._left_down else Q.kCGEventMouseMoved
            self._mouse(kind, Q.kCGMouseButtonLeft)
        elif isinstance(action, Click):
            button, down, up = _BUTTONS[action.button]
            self._mouse(down, button, action.count)
            self._mouse(up, button, action.count)
        elif isinstance(action, MouseButton):
            button, down, up = _BUTTONS[action.button]
            self._mouse(down if action.down else up, button)
            if action.button == "left":
                self._left_down = action.down
        elif isinstance(action, Scroll):
            ev = Q.CGEventCreateScrollWheelEvent(None, Q.kCGScrollEventUnitPixel, 2, action.dy, action.dx)
            Q.CGEventSetLocation(ev, self._scroll_location())
            Q.CGEventPost(Q.kCGHIDEventTap, ev)
        elif isinstance(action, Shortcut):
            self._key(*SHORTCUTS[action.name])

    def _scroll_location(self) -> tuple[float, float]:
        """Resolve once per scroll gesture: the pinch point, or the nearest scrollable area if the
        pinch point isn't over one (so scrolling works anywhere in a window)."""
        now = time.monotonic()
        if self._scroll_at is None or now - self._last_scroll_t > 0.4:
            self._scroll_at = self._pos
            if self.smart_scroll:
                from .ax import scroll_target
                self._scroll_at = scroll_target(*self._pos)
        self._last_scroll_t = now
        return self._scroll_at

    def _mouse(self, kind, button, click_state: int = 1) -> None:
        ev = Q.CGEventCreateMouseEvent(None, kind, self._pos, button)
        Q.CGEventSetIntegerValueField(ev, Q.kCGMouseEventClickState, click_state)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)

    @staticmethod
    def _key(keycode: int, flags: int) -> None:
        for down in (True, False):
            ev = Q.CGEventCreateKeyboardEvent(None, keycode, down)
            Q.CGEventSetFlags(ev, flags)
            Q.CGEventPost(Q.kCGHIDEventTap, ev)
