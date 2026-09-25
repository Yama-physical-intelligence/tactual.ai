# Gesture guide

Tactual's control model is simple: **your hand is a pointer, and a pinch is the action.** The cursor sits
where your thumb and index fingertips meet (the *pinch point*), so you aim with the same spot you "touch" with.
The on-screen hand imprint and its aim ring show exactly where that is.

## Setup first

Run the setup once (it starts automatically on first launch, or use `./run.sh --setup`):

1. **Gesture setup** (about 15 s): open hand, point, pinch thumb+index, pinch thumb+middle, fist. Hold each pose
   until the progress bar fills. A step only starts once it actually sees the pose.
2. **Screen setup** (5 s): sweep your hand over the area you want to use and reach every edge. That area
   becomes the full screen. A smaller area means less arm movement but a more sensitive cursor.

Redo either step at any time: `g` redoes gesture setup, `c` redoes screen setup (with the preview window focused).

## One hand

### Point: move the cursor
Hover with your hand relaxed and thumb and index slightly apart. The cursor follows the point between those
two fingertips. Movement is filtered adaptively: steady when you're still, and responsive when you move fast.

### Tap: click
Touch your thumb and index finger together briefly (under 0.35 s) and let go.
- The cursor **freezes** while your fingers are together, so the click can't slide off target.
- **Click rewind:** closing your fingers drags the pinch point slightly. Tactual puts the click where you were
  aiming *just before* your fingers started closing.

### Double tap: double-click
Two taps in quick succession (within 0.45 s). This sends a real double-click, which opens files and selects words.

### Pinch and move: scroll
Pinch and keep your fingers together, then move your hand. The content follows your hand, like dragging paper:
move down to see what's above, move up to see what's below. It works vertically and horizontally.
- **Flick:** release while still moving fast and the content keeps gliding (momentum).
- **Scroll anywhere:** if you pinched over something that can't scroll (a title bar, toolbar, or gap), the
  scroll goes to the window's main scrollable area.
- The movement has to pass about 20 px before scrolling starts, so a tap never scrolls by accident.

### Pinch and twist: dial scroll
Pinch, then rotate your hand around the pinch point, like turning a volume knob. Clockwise scrolls down and
anticlockwise scrolls up. Your pinch point stays still, so this is the most precise way to scroll a long page.
Twisting past about 14° switches into dial mode.

### Tap, then pinch and move: drag and drop
Tap once, then pinch again right away (within 0.45 s) and move. This grabs whatever is under the cursor
(a file, a window, a slider) and carries it; open your fingers to drop it. This matches "tap-drag" on a
MacBook trackpad.

### Pinch thumb + middle: right click
Touch your thumb to your **middle** finger. The context menu opens at the aim ring.

### Pinch and hold still: nothing
A pinch held in place does nothing, by design. You can rest in a pinch without anything happening.

### Open palm swipe: desktops
Open your whole hand (all four fingers up) and sweep it quickly:
- **left / right**: switch to the next or previous desktop (Space). This follows the trackpad convention: move
  your hand left to go to the desktop on the right.
- **up**: Mission Control. **down**: the current app's windows.

The cursor is frozen while your palm is open, so swiping never drags the cursor.

### Fist: pause / resume
Hold a fist for 1 second. A ring fills around your hand in the preview window, then control toggles. Use this to get your mouse back,
or to talk with your hands freely. Open your hand before toggling again.

## Two hands

### Both hands pinch, spread or close: zoom
Pinch with **both** hands, then move them apart to zoom in or together to zoom out. It steps every 15% change in
distance and sends ⌘+ / ⌘−. Tactual switches to two-hand tracking automatically when a second hand shows up;
both hand imprints appear on screen.

## Tips for reliability

- **Light your hand.** In dim light the camera drops to about 15 fps and tracking lags. Check the fps in the preview.
- **Keep your palm roughly facing the camera** for pinches, so the tracker can see the gap between your fingers.
- **Rest your elbow** on the desk and use a small screen-setup area, which is much less tiring.
- **If pinches misfire**, redo the gesture setup (`g`) with clear, deliberate poses.
- **If the cursor can't reach the edges**, redo the screen setup (`c`) and sweep a little further.
- **`--dry-run`** logs every recognized gesture without touching the mouse, which is useful for practice.

## Customizing

Every threshold is a setting in [`fingering/config.py`](../fingering/config.py). Override any of them with a JSON
file:

```json
{
  "natural_scroll": false,
  "dial_gain": 20,
  "tap_max_s": 0.3,
  "primary_hand": "Left"
}
```

```sh
./run.sh --config my_settings.json
```
