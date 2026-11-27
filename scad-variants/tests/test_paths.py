from __future__ import annotations

import unittest

from scadvariants.paths import app_root
from scadvariants.slots import SLOTS_ROOT


class PathTests(unittest.TestCase):
    def test_slots_root_is_project_local(self) -> None:
        self.assertEqual(SLOTS_ROOT, app_root() / "orca-slots")


if __name__ == "__main__":
    unittest.main()
