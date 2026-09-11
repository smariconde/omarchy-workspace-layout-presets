"""Pure expansion of a Dwindle split sequence back into leaf rectangles.

This is the exact inverse of :mod:`infer_dwindle`: that module turns measured
rectangles into a split tree, and this one replays a stored tree to recover the
rectangle each window occupies. Both the restore verifier and the panel sketch
read from here, so the ratio convention lives in a single place.

A ratio is the fraction taken by the *new* side of a split; the focused node
keeps ``1 - ratio``. Coordinates are normalized to the workspace rectangle, so
every value lies in ``[0, 1]`` and the leaves tile it without gaps or overlap.

The functions are total: malformed input yields an empty result rather than an
exception, because callers render or compare whatever they get and must never
fail on a profile that validation already accepted.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence


_VALID_DIRECTIONS = frozenset({"left", "right", "up", "down"})

Rect = tuple[float, float, float, float]


def expand_layout(anchor: Any, splits: Any) -> dict[str, Rect]:
    """Return one normalized ``(x, y, width, height)`` per tiled node id.

    ``anchor`` seeds the whole workspace. Each split subdivides the rectangle
    currently held by its ``focus`` node, handing ``ratio`` of it to the ``new``
    node on the named side. An empty layout, or any split that does not
    reference a known focus, produces ``{}``.
    """
    if not isinstance(anchor, str) or not anchor:
        return {}
    if not isinstance(splits, Sequence) or isinstance(splits, (str, bytes)):
        return {}

    rectangles: dict[str, Rect] = {anchor: (0.0, 0.0, 1.0, 1.0)}
    for split in splits:
        if not isinstance(split, Mapping):
            return {}
        focus, new = split.get("focus"), split.get("new")
        direction, ratio = split.get("direction"), split.get("ratio")
        if (
            not isinstance(focus, str)
            or not isinstance(new, str)
            or direction not in _VALID_DIRECTIONS
            or isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or focus not in rectangles
        ):
            return {}
        fraction = float(ratio)
        if not math.isfinite(fraction) or not 0 < fraction < 1:
            return {}
        x, y, width, height = rectangles[focus]
        if direction == "right":
            rectangles[focus] = (x, y, width * (1 - fraction), height)
            rectangles[new] = (x + width * (1 - fraction), y, width * fraction, height)
        elif direction == "left":
            rectangles[focus] = (x + width * fraction, y, width * (1 - fraction), height)
            rectangles[new] = (x, y, width * fraction, height)
        elif direction == "down":
            rectangles[focus] = (x, y, width, height * (1 - fraction))
            rectangles[new] = (x, y + height * (1 - fraction), width, height * fraction)
        else:
            rectangles[focus] = (x, y + height * fraction, width, height * (1 - fraction))
            rectangles[new] = (x, y, width, height * fraction)
    return rectangles


def profile_layout(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Build the wordless ``layout`` sketch that ``profile show`` returns.

    The result describes proportions only: an id, whether the window was tiled
    or floating, and a normalized rectangle. It carries no application name,
    window class, path or launch argument, so the sketch cannot become a side
    channel for anything the profile schema deliberately excludes.
    """
    tiled = profile.get("tiled") or {}
    nodes = tiled.get("nodes") or []
    identifiers = [node["id"] for node in nodes if isinstance(node, Mapping) and isinstance(node.get("id"), str)]
    approximate = profile.get("layoutConfidence") != "exact"
    rectangles = (
        even_grid(identifiers) if approximate else expand_layout(tiled.get("anchor"), tiled.get("splits") or [])
    )
    if identifiers and not rectangles:
        # A stored tree that will not expand is no better than an unknown one.
        approximate = True
        rectangles = even_grid(identifiers)

    windows = [
        {"id": identifier, "placement": "tiled", **_rectangle_fields(rectangles[identifier])}
        for identifier in identifiers
        if identifier in rectangles
    ]
    for node in profile.get("floating") or []:
        geometry = _floating_rectangle(node)
        if geometry is not None:
            windows.append({"id": node["id"], "placement": "floating", **geometry})
    monitor = (profile.get("source") or {}).get("monitor") or {}
    return {
        "mode": "approximate" if approximate else "exact",
        "aspect": {
            "width": monitor.get("usableWidth") or 16,
            "height": monitor.get("usableHeight") or 9,
        },
        "windows": windows,
    }


def _rectangle_fields(rectangle: Rect) -> dict[str, float]:
    x, y, width, height = rectangle
    return {"x": x, "y": y, "width": width, "height": height}


def _floating_rectangle(node: Any) -> dict[str, float] | None:
    if not isinstance(node, Mapping) or not isinstance(node.get("id"), str):
        return None
    geometry = node.get("geometry")
    if not isinstance(geometry, Mapping):
        return None
    fields: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        value = geometry.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        fields[key] = float(value)
    return fields


def even_grid(identifiers: Iterable[Any]) -> dict[str, Rect]:
    """Return equally sized cells for a layout whose geometry is unknown.

    A ``fallback`` profile stores a synthetic chain of half splits that was
    never measured. Expanding it would draw confident, invented proportions, so
    callers ask for this neutral grid instead and label it as approximate.
    """
    windows = [identifier for identifier in identifiers if isinstance(identifier, str) and identifier]
    if not windows:
        return {}
    columns = math.ceil(math.sqrt(len(windows)))
    rows = math.ceil(len(windows) / columns)
    cell_height = 1.0 / rows
    rectangles: dict[str, Rect] = {}
    for index, identifier in enumerate(windows):
        column, row = index % columns, index // columns
        # The final row may be short; stretch it so the grid fills the frame.
        width = 1.0 / min(columns, len(windows) - row * columns)
        rectangles[identifier] = (column * width, row * cell_height, width, cell_height)
    return rectangles
