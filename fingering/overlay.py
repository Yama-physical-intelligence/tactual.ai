"""Subtle on-screen hand imprint: a transparent, click-through window above everything.

The ghost hand is drawn in screen space so its index knuckle sits exactly on the cursor.
"""

import AppKit
import objc
from Foundation import NSDate, NSMakeRect, NSPoint

from .hand import CONNECTIONS, INDEX_TIP, THUMB_TIP, MIDDLE_TIP

_TIPS = (4, 8, 12, 16, 20)
_SMOOTH = 0.45  # landmark EMA: lower = smoother, laggier


def _rgba(r, g, b, a):
    return AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)


class _HandView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_HandView, self).initWithFrame_(frame)
        if self is not None:
            self.points = None
            self.state = "idle"
            self.message = None
            self.progress = 0.0
            self.cursor = None
        return self

    def isFlipped(self):  # top-left origin, like CoreGraphics screen coords
        return True

    def drawRect_(self, rect):
        AppKit.NSColor.clearColor().set()
        AppKit.NSRectFill(rect)
        if self.message:
            self._draw_message()
        pts = self.points
        if not pts:
            return
        tint = {
            "paused": (0.6, 0.6, 0.6, 0.18),
            "pinch": (1.0, 0.55, 0.25, 0.45),
            "active": (1.0, 1.0, 1.0, 0.28),
        }[self.state]
        line = _rgba(*tint)
        shadow = _rgba(0, 0, 0, tint[3] * 0.6)

        path = AppKit.NSBezierPath.bezierPath()
        for a, b in CONNECTIONS:
            path.moveToPoint_(NSPoint(*pts[a]))
            path.lineToPoint_(NSPoint(*pts[b]))
        path.setLineCapStyle_(AppKit.NSLineCapStyleRound)
        path.setLineWidth_(4.0)
        shadow.set()
        path.stroke()
        path.setLineWidth_(2.0)
        line.set()
        path.stroke()

        if self.cursor:  # precise aim point: where the click lands
            x, y = self.cursor
            ring = AppKit.NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x - 9, y - 9, 18, 18))
            ring.setLineWidth_(1.5)
            _rgba(*tint[:3], min(tint[3] * 2.5, 0.9)).set()
            ring.stroke()
            AppKit.NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x - 2, y - 2, 4, 4)).fill()
            line.set()

        for i in _TIPS:
            r = 7.0 if i in (THUMB_TIP, INDEX_TIP) else 4.5
            if self.state == "pinch" and i in (THUMB_TIP, INDEX_TIP, MIDDLE_TIP):
                r += 2
            x, y = pts[i]
            AppKit.NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x - r, y - r, 2 * r, 2 * r)).fill()


    def _draw_message(self):
        """Setup instruction pill, bottom-center of the screen."""
        attrs = {
            AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_weight_(20, AppKit.NSFontWeightMedium),
            AppKit.NSForegroundColorAttributeName: _rgba(1, 1, 1, 0.92),
        }
        text = AppKit.NSAttributedString.alloc().initWithString_attributes_(self.message, attrs)
        size = text.size()
        bounds = self.bounds()
        w, h = size.width + 48, size.height + 30
        x, y = (bounds.size.width - w) / 2, bounds.size.height - h - 90
        pill = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(x, y, w, h), h / 2, h / 2)
        _rgba(0.08, 0.08, 0.1, 0.72).set()
        pill.fill()
        if self.progress > 0:
            _rgba(1.0, 0.55, 0.25, 0.9).set()
            AppKit.NSRectFill(NSMakeRect(x + h / 2, y + h - 5, (w - h) * self.progress, 3))
        text.drawAtPoint_(NSPoint(x + 24, y + 12))


class HandOverlay:
    def __init__(self):
        AppKit.NSApplication.sharedApplication()
        frame = AppKit.NSScreen.mainScreen().frame()
        win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
        win.setOpaque_(False)
        win.setBackgroundColor_(AppKit.NSColor.clearColor())
        win.setHasShadow_(False)
        win.setIgnoresMouseEvents_(True)  # fully click-through
        win.setLevel_(AppKit.NSScreenSaverWindowLevel)
        win.setCollectionBehavior_(  # follow across Spaces and over full-screen apps
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorIgnoresCycle)
        self._view = _HandView.alloc().initWithFrame_(NSMakeRect(0, 0, frame.size.width, frame.size.height))
        win.setContentView_(self._view)
        win.orderFrontRegardless()
        self._win = win
        self._smoothed = None

    def update(self, screen_points, state: str, message: str | None = None, progress: float = 0.0,
               cursor=None) -> None:
        """screen_points: 21 (x, y) in screen pixels, or None to hide."""
        if screen_points is None:
            self._smoothed = None
        elif self._smoothed is None:
            self._smoothed = list(screen_points)
        else:
            self._smoothed = [
                (px + _SMOOTH * (x - px), py + _SMOOTH * (y - py))
                for (px, py), (x, y) in zip(self._smoothed, screen_points)
            ]
        self._view.points = self._smoothed
        self._view.state = state
        self._view.message = message
        self._view.progress = progress
        self._view.cursor = cursor if screen_points else None
        self._view.setNeedsDisplay_(True)
        self.pump()

    @staticmethod
    def pump() -> None:
        """Process pending Cocoa events so the overlay redraws even without an OpenCV window."""
        app = AppKit.NSApp()
        while True:
            ev = app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                AppKit.NSEventMaskAny, NSDate.distantPast(), AppKit.NSDefaultRunLoopMode, True)
            if ev is None:
                break
            app.sendEvent_(ev)

    def close(self) -> None:
        self._win.orderOut_(None)
