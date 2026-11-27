from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from scadvariants.gallery import write_source_page


class GalleryDedupTests(unittest.TestCase):
    def test_alias_images_render_once(self) -> None:
        root = Path(__file__).resolve().parents[1] / ".tmp-gallery-tests"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        try:
            for name in ("body.png", "rail-left.png", "rail-right.png"):
                (root / name).write_bytes(b"not-a-real-png")
            for name in ("body.stl", "rail-left.stl", "rail-right.stl"):
                (root / name).write_bytes(b"not-a-real-stl")

            manifest = {
                "source": {"abs": str(root / "model.scad"), "rel": "model.scad"},
                "switches": [],
                "status": "ok",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "variants": [
                    {
                        "id": "body-left",
                        "label": 'part = "body"',
                        "values": {"part": "body", "side": "left"},
                        "effective_values": {"part": "body"},
                        "image": "body.png",
                        "stl": "body.stl",
                        "aliases": ["body-right"],
                        "status": "ok",
                    },
                    {
                        "id": "body-right",
                        "label": 'part = "body" · side = "right"',
                        "values": {"part": "body", "side": "right"},
                        "effective_values": {"part": "body"},
                        "image": "body.png",
                        "stl": "body.stl",
                        "status": "ok",
                    },
                    {
                        "id": "rail-left",
                        "label": 'part = "rail" · side = "left"',
                        "values": {"part": "rail", "side": "left"},
                        "effective_values": {"part": "rail", "side": "left"},
                        "image": "rail-left.png",
                        "stl": "rail-left.stl",
                        "status": "ok",
                    },
                    {
                        "id": "rail-right",
                        "label": 'part = "rail" · side = "right"',
                        "values": {"part": "rail", "side": "right"},
                        "effective_values": {"part": "rail", "side": "right"},
                        "image": "rail-right.png",
                        "stl": "rail-right.stl",
                        "status": "ok",
                    },
                ],
            }

            write_source_page(root, manifest)
            html = (root / "index.html").read_text(encoding="utf-8")

            self.assertEqual(html.count("<img src="), 3)
            self.assertEqual(html.count('class="thumb viewer-link"'), 3)
            self.assertEqual(html.count('class="thumb-expand"'), 3)
            self.assertIn("return open3D", html)
            self.assertIn("return openImageClick", html)
            self.assertEqual(html.count('class="copy-path"'), 6)
            self.assertNotIn('id="preview-overlay"', html)
            self.assertIn("вариантов: 3", html)
            self.assertIn("комбинаций: 4", html)
            self.assertIn("ещё 1 комбинация с той же геометрией", html)
            self.assertIn("part = &quot;body&quot;", html)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
