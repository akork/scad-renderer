from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from scadvariants.progress import ProgressWriter


class ProgressWriterTests(unittest.TestCase):
    def test_writes_and_advances_then_removes(self) -> None:
        root = Path(__file__).resolve().parents[1] / ".tmp-progress-tests"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        try:
            writer = ProgressWriter(
                source=root / "model.scad",
                out_dir=root / "model_renders",
                total=3,
                rel="model.scad",
                progress_dir=root,
            )
            payload = json.loads(writer.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["total"], 3)
            self.assertEqual(payload["done"], 0)
            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["pid"], __import__("os").getpid())

            writer.advance('part = "body"')
            payload = json.loads(writer.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["done"], 1)
            self.assertEqual(payload["current"], "")

            writer.start_variant('part = "frame"', 12.5)
            payload = json.loads(writer.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["current"], 'part = "frame"')
            self.assertEqual(payload["current_estimate_s"], 12.5)
            self.assertTrue(payload["current_started"])

            writer.finish()
            self.assertFalse(writer.path.exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
