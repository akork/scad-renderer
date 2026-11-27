from __future__ import annotations

import unittest
from pathlib import Path

from scadvariants.slots import DEFAULT_SLOTS_ROOT


class PathTests(unittest.TestCase):
    def test_slots_default_is_in_home(self) -> None:
        self.assertEqual(DEFAULT_SLOTS_ROOT, Path.home() / "slicer-slots")


if __name__ == "__main__":
    unittest.main()
