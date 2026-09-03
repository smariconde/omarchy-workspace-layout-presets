from __future__ import annotations

import unittest

from backend.infer_dwindle import GeometryError, Rectangle, infer_dwindle


def rectangle(x: float, y: float, width: float, height: float) -> Rectangle:
    return Rectangle(x, y, width, height)


class InferDwindleTests(unittest.TestCase):
    def test_infers_vertical_split_with_ratio_measured_at_the_gap_centre(self) -> None:
        layout = infer_dwindle(
            {
                "editor": rectangle(0, 0, 958, 1000),
                "terminal": rectangle(962, 0, 958, 1000),
            }
        )

        self.assertIsNotNone(layout)
        assert layout is not None
        self.assertEqual(layout.anchor, "editor")
        self.assertEqual(
            layout.splits,
            [{"focus": "editor", "direction": "right", "new": "terminal", "ratio": 0.5}],
        )

    def test_infers_nested_slicing_tree_in_deterministic_order(self) -> None:
        layout = infer_dwindle(
            {
                "editor": rectangle(0, 0, 598, 1000),
                "shell": rectangle(602, 0, 598, 498),
                "logs": rectangle(602, 502, 598, 498),
            }
        )

        self.assertIsNotNone(layout)
        assert layout is not None
        self.assertEqual(layout.anchor, "editor")
        self.assertEqual(
            layout.splits,
            [
                {"focus": "editor", "direction": "right", "new": "shell", "ratio": 0.5},
                {"focus": "shell", "direction": "down", "new": "logs", "ratio": 0.5},
            ],
        )

    def test_returns_fallback_signal_for_staggered_non_slicing_rectangles(self) -> None:
        layout = infer_dwindle(
            {
                "top-left": rectangle(0, 0, 400, 400),
                "bottom-right": rectangle(500, 500, 400, 400),
            }
        )

        self.assertIsNone(layout)

    def test_rejects_invalid_and_oversized_inputs(self) -> None:
        with self.assertRaises(GeometryError):
            rectangle(0, 0, 0, 10)
        with self.assertRaises(GeometryError):
            infer_dwindle({str(index): rectangle(index * 10, 0, 10, 10) for index in range(11)})
