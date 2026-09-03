"""Pure inference of a Dwindle split tree from tiled window rectangles.

Hyprland reports final window rectangles, not the history that produced them.
This module accepts only *slicing* (guillotine) floorplans: every recursive
partition must split the current bounding rectangle completely from one side
to the other. That is the subset that can be reconstructed with Dwindle
preselection without guessing at overlapping or staggered geometry.

When several equivalent slicing trees exist, the deterministic preference is
vertical before horizontal, then the first coordinate-ordered partition. The
choice is an implementation detail; each accepted tree reproduces the same
rectangular partition. A reported ratio is the fraction occupied by the new
right or bottom side, measured at the centre of the inter-window gap.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


_MAX_TILED_WINDOWS = 10


class GeometryError(ValueError):
    """Raised when an alleged tiled rectangle has invalid numeric geometry."""


@dataclass(frozen=True)
class Rectangle:
    """A finite, positive rectangle in Hyprland's workspace coordinates."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(math.isfinite(value) for value in values):
            raise GeometryError("tiled geometry must contain finite numbers")
        if self.width <= 0 or self.height <= 0:
            raise GeometryError("tiled geometry width and height must be positive")

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class InferredLayout:
    """Schema-ready anchor and ordered Dwindle split operations."""

    anchor: str
    splits: list[dict[str, float | str]]


@dataclass(frozen=True)
class _Bounds:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True)
class _Tree:
    identifiers: tuple[str, ...]
    first: _Tree | None = None
    second: _Tree | None = None
    direction: str | None = None
    ratio: float | None = None

    @property
    def is_leaf(self) -> bool:
        return self.first is None


def _bounds(identifiers: Sequence[str], rectangles: Mapping[str, Rectangle]) -> _Bounds:
    items = [rectangles[identifier] for identifier in identifiers]
    return _Bounds(
        left=min(item.x for item in items),
        top=min(item.y for item in items),
        right=max(item.right for item in items),
        bottom=max(item.bottom for item in items),
    )


def _close(first: float, second: float, extent: float) -> bool:
    """Tolerate decoding noise, but never a visible rectangular mismatch."""
    return math.isclose(first, second, abs_tol=max(1e-6, abs(extent) * 1e-6), rel_tol=0.0)


def _partitions(
    identifiers: tuple[str, ...], rectangles: Mapping[str, Rectangle]
) -> list[tuple[tuple[str, ...], tuple[str, ...], str, float]]:
    """Return safe first/second partitions in deterministic preference order."""
    parent = _bounds(identifiers, rectangles)
    candidates: list[tuple[tuple[str, ...], tuple[str, ...], str, float]] = []
    for vertical in (True, False):
        ordered = tuple(
            sorted(
                identifiers,
                key=lambda identifier: (
                    rectangles[identifier].x if vertical else rectangles[identifier].y,
                    rectangles[identifier].y if vertical else rectangles[identifier].x,
                    identifier,
                ),
            )
        )
        for index in range(1, len(ordered)):
            first, second = ordered[:index], ordered[index:]
            first_bounds = _bounds(first, rectangles)
            second_bounds = _bounds(second, rectangles)
            if vertical:
                if first_bounds.right > second_bounds.left and not _close(
                    first_bounds.right, second_bounds.left, parent.width
                ):
                    continue
                if not (
                    _close(first_bounds.top, parent.top, parent.height)
                    and _close(first_bounds.bottom, parent.bottom, parent.height)
                    and _close(second_bounds.top, parent.top, parent.height)
                    and _close(second_bounds.bottom, parent.bottom, parent.height)
                ):
                    continue
                cut = (first_bounds.right + second_bounds.left) / 2
                ratio = (parent.right - cut) / parent.width
                direction = "right"
            else:
                if first_bounds.bottom > second_bounds.top and not _close(
                    first_bounds.bottom, second_bounds.top, parent.height
                ):
                    continue
                if not (
                    _close(first_bounds.left, parent.left, parent.width)
                    and _close(first_bounds.right, parent.right, parent.width)
                    and _close(second_bounds.left, parent.left, parent.width)
                    and _close(second_bounds.right, parent.right, parent.width)
                ):
                    continue
                cut = (first_bounds.bottom + second_bounds.top) / 2
                ratio = (parent.bottom - cut) / parent.height
                direction = "down"
            if 0 < ratio < 1 and math.isfinite(ratio):
                candidates.append((first, second, direction, ratio))
    return candidates


def infer_dwindle(rectangles: Mapping[str, Rectangle]) -> InferredLayout | None:
    """Infer a replayable Dwindle tree, or ``None`` for non-slicing layouts.

    Empty layouts have no tiled-tree representation and return ``None``; the
    caller can represent that state exactly with a null anchor. Invalid input
    raises :class:`GeometryError` rather than silently falling back.
    """
    if len(rectangles) > _MAX_TILED_WINDOWS:
        raise GeometryError(f"at most {_MAX_TILED_WINDOWS} tiled windows can be inferred")
    if not rectangles:
        return None
    identifiers = tuple(rectangles)
    if any(not isinstance(identifier, str) or not identifier for identifier in identifiers):
        raise GeometryError("tiled window identifiers must be non-empty strings")
    if any(not isinstance(rectangle, Rectangle) for rectangle in rectangles.values()):
        raise GeometryError("tiled geometry must use Rectangle values")

    cache: dict[tuple[str, ...], _Tree | None] = {}

    def build(current: tuple[str, ...]) -> _Tree | None:
        key = tuple(sorted(current))
        if key in cache:
            return cache[key]
        if len(current) == 1:
            result: _Tree | None = _Tree(current)
        else:
            result = None
            for first, second, direction, ratio in _partitions(current, rectangles):
                first_tree = build(first)
                second_tree = build(second)
                if first_tree is not None and second_tree is not None:
                    result = _Tree(current, first_tree, second_tree, direction, ratio)
                    break
        cache[key] = result
        return result

    tree = build(identifiers)
    if tree is None:
        return None

    splits: list[dict[str, float | str]] = []

    def first_leaf(current: _Tree) -> str:
        while not current.is_leaf:
            assert current.first is not None
            current = current.first
        return current.identifiers[0]

    def emit(current: _Tree) -> None:
        if current.is_leaf:
            return
        assert current.first is not None and current.second is not None
        assert current.direction is not None and current.ratio is not None
        splits.append(
            {
                "focus": first_leaf(current.first),
                "direction": current.direction,
                "new": first_leaf(current.second),
                "ratio": current.ratio,
            }
        )
        emit(current.first)
        emit(current.second)

    anchor = first_leaf(tree)
    emit(tree)
    return InferredLayout(anchor=anchor, splits=splits)
