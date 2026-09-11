from __future__ import annotations

from typing import Any
import unittest

from backend.infer_dwindle import Rectangle, infer_dwindle
from backend.layout_preview import even_grid, expand_layout, profile_layout


def split(focus: str, direction: str, new: str, ratio: float) -> dict[str, Any]:
    return {"focus": focus, "direction": direction, "new": new, "ratio": ratio}


def profile(
    nodes: list[str],
    anchor: str | None,
    splits: list[dict[str, Any]],
    *,
    confidence: str = "exact",
    floating: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "name": "Work",
        "createdAt": "2026-01-01T00:00:00Z",
        "source": {
            "hyprlandLayout": "dwindle",
            "workspace": {"name": "4"},
            "monitor": {"connector": "DP-1", "usableWidth": 2560, "usableHeight": 1392},
        },
        "layoutConfidence": confidence,
        "tiled": {
            "anchor": anchor,
            "nodes": [
                {
                    "id": node,
                    "app": {"desktopId": "app.desktop", "wmClass": "app", "ordinal": 1},
                    "launch": {"kind": "desktop", "desktopId": "app.desktop"},
                }
                for node in nodes
            ],
            "splits": splits,
        },
        "floating": floating or [],
        "warnings": [],
    }


class ExpandLayoutTests(unittest.TestCase):
    def test_a_lone_anchor_occupies_the_whole_workspace(self) -> None:
        self.assertEqual(expand_layout("editor", []), {"editor": (0.0, 0.0, 1.0, 1.0)})

    def test_each_direction_gives_the_ratio_to_the_new_side(self) -> None:
        cases = {
            "right": {"editor": (0.0, 0.0, 0.7, 1.0), "terminal": (0.7, 0.0, 0.3, 1.0)},
            "left": {"editor": (0.3, 0.0, 0.7, 1.0), "terminal": (0.0, 0.0, 0.3, 1.0)},
            "down": {"editor": (0.0, 0.0, 1.0, 0.7), "terminal": (0.0, 0.7, 1.0, 0.3)},
            "up": {"editor": (0.0, 0.3, 1.0, 0.7), "terminal": (0.0, 0.0, 1.0, 0.3)},
        }
        for direction, expected in cases.items():
            with self.subTest(direction=direction):
                rectangles = expand_layout("editor", [split("editor", direction, "terminal", 0.3)])
                self.assertEqual(len(rectangles), 2)
                for identifier, rectangle in expected.items():
                    for value, wanted in zip(rectangles[identifier], rectangle):
                        self.assertAlmostEqual(value, wanted)

    def test_nested_splits_tile_the_workspace_without_gaps_or_overlap(self) -> None:
        rectangles = expand_layout(
            "editor",
            [
                split("editor", "right", "browser", 0.5),
                split("browser", "down", "chat", 0.25),
            ],
        )

        self.assertEqual(
            {identifier: tuple(round(value, 6) for value in rectangle) for identifier, rectangle in rectangles.items()},
            {
                "editor": (0.0, 0.0, 0.5, 1.0),
                "browser": (0.5, 0.0, 0.5, 0.75),
                "chat": (0.5, 0.75, 0.5, 0.25),
            },
        )
        self.assertAlmostEqual(sum(width * height for _, _, width, height in rectangles.values()), 1.0)

    def test_expansion_reproduces_the_geometry_that_inference_measured(self) -> None:
        measured = {
            "editor": Rectangle(0, 0, 1280, 1392),
            "browser": Rectangle(1280, 0, 1280, 696),
            "chat": Rectangle(1280, 696, 1280, 696),
        }
        inferred = infer_dwindle(measured)
        assert inferred is not None

        rectangles = expand_layout(inferred.anchor, inferred.splits)

        for identifier, original in measured.items():
            x, y, width, height = rectangles[identifier]
            self.assertAlmostEqual(x * 2560, original.x, places=3)
            self.assertAlmostEqual(y * 1392, original.y, places=3)
            self.assertAlmostEqual(width * 2560, original.width, places=3)
            self.assertAlmostEqual(height * 1392, original.height, places=3)

    def test_a_ten_window_chain_stays_within_the_workspace(self) -> None:
        identifiers = [f"window-{index}" for index in range(1, 11)]
        splits = [split(identifiers[index - 1], "right", identifiers[index], 0.5) for index in range(1, 10)]

        rectangles = expand_layout(identifiers[0], splits)

        self.assertEqual(len(rectangles), 10)
        for x, y, width, height in rectangles.values():
            self.assertGreaterEqual(x, 0.0)
            self.assertGreater(width, 0.0)
            self.assertLessEqual(round(x + width, 9), 1.0)
            self.assertEqual((y, height), (0.0, 1.0))
        self.assertAlmostEqual(sum(width for _, _, width, _ in rectangles.values()), 1.0)

    def test_malformed_input_yields_an_empty_result_instead_of_raising(self) -> None:
        cases = {
            "no anchor": (None, []),
            "unknown focus": ("editor", [split("ghost", "right", "terminal", 0.5)]),
            "bad direction": ("editor", [split("editor", "sideways", "terminal", 0.5)]),
            "ratio out of range": ("editor", [split("editor", "right", "terminal", 1.0)]),
            "boolean ratio": ("editor", [split("editor", "right", "terminal", True)]),
            "split is not an object": ("editor", ["right"]),
            "splits are not a sequence": ("editor", 3),
        }
        for label, (anchor, splits) in cases.items():
            with self.subTest(label=label):
                self.assertEqual(expand_layout(anchor, splits), {})


class EvenGridTests(unittest.TestCase):
    def test_an_empty_layout_has_no_cells(self) -> None:
        self.assertEqual(even_grid([]), {})

    def test_cells_fill_the_frame_even_when_the_last_row_is_short(self) -> None:
        for count in range(1, 11):
            with self.subTest(count=count):
                rectangles = even_grid([f"window-{index}" for index in range(count)])

                self.assertEqual(len(rectangles), count)
                self.assertAlmostEqual(sum(width * height for _, _, width, height in rectangles.values()), 1.0)
                for x, y, width, height in rectangles.values():
                    self.assertLessEqual(round(x + width, 9), 1.0)
                    self.assertLessEqual(round(y + height, 9), 1.0)


class ProfileLayoutTests(unittest.TestCase):
    def test_an_exact_profile_reports_measured_proportions(self) -> None:
        layout = profile_layout(
            profile(["editor", "terminal"], "editor", [split("editor", "right", "terminal", 0.4)])
        )

        self.assertEqual(layout["mode"], "exact")
        self.assertEqual(layout["aspect"], {"width": 2560, "height": 1392})
        self.assertEqual(
            layout["windows"],
            [
                {"id": "editor", "placement": "tiled", "x": 0.0, "y": 0.0, "width": 0.6, "height": 1.0},
                {"id": "terminal", "placement": "tiled", "x": 0.6, "y": 0.0, "width": 0.4, "height": 1.0},
            ],
        )

    def test_a_fallback_profile_never_presents_its_synthetic_splits_as_measured(self) -> None:
        stored = profile(
            ["editor", "terminal"],
            "editor",
            [split("editor", "right", "terminal", 0.5)],
            confidence="fallback",
        )

        layout = profile_layout(stored)

        self.assertEqual(layout["mode"], "approximate")
        self.assertEqual(
            [window["width"] for window in layout["windows"]],
            [0.5, 0.5],
        )
        self.assertEqual([window["height"] for window in layout["windows"]], [1.0, 1.0])

    def test_floating_windows_keep_their_normalized_geometry_and_come_last(self) -> None:
        stored = profile(
            ["editor"],
            "editor",
            [],
            floating=[
                {
                    "id": "picker",
                    "app": {"desktopId": None, "wmClass": "picker", "ordinal": 1},
                    "launch": {"kind": "unresolved"},
                    "geometry": {"x": 0.25, "y": 0.2, "width": 0.4, "height": 0.5},
                }
            ],
        )

        layout = profile_layout(stored)

        self.assertEqual(
            layout["windows"][-1],
            {"id": "picker", "placement": "floating", "x": 0.25, "y": 0.2, "width": 0.4, "height": 0.5},
        )

    def test_an_empty_profile_produces_no_windows(self) -> None:
        layout = profile_layout(profile([], None, []))

        self.assertEqual(layout["windows"], [])
        self.assertEqual(layout["mode"], "exact")

    def test_the_sketch_carries_proportions_only_and_no_application_identity(self) -> None:
        layout = profile_layout(
            profile(["editor", "terminal"], "editor", [split("editor", "down", "terminal", 0.5)])
        )

        allowed = {"id", "placement", "x", "y", "width", "height"}
        for window in layout["windows"]:
            self.assertEqual(set(window), allowed)
        self.assertNotIn("wmClass", repr(layout))
        self.assertNotIn("desktop", repr(layout))


if __name__ == "__main__":
    unittest.main()
