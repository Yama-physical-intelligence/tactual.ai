"""Actions are plain data emitted by the gesture engine and executed by an OS controller."""

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class MoveCursor:
    x: float
    y: float


@dataclass(frozen=True)
class MouseButton:
    button: str  # "left" | "right"
    down: bool


@dataclass(frozen=True)
class Click:
    button: str = "left"
    count: int = 1


@dataclass(frozen=True)
class Scroll:
    dy: int
    dx: int = 0


@dataclass(frozen=True)
class Shortcut:
    name: str  # see controller.SHORTCUTS


@dataclass(frozen=True)
class Notice:
    text: str  # HUD/log only, no OS effect


Action = Union[MoveCursor, MouseButton, Click, Scroll, Shortcut, Notice]
