from __future__ import annotations

import fnmatch
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from scad_drop import _build_parser, _glob_exact, _record_recent, gallery_dir  # noqa: E402


class HelperTests(unittest.TestCase):
    def test_glob_exact_matches_literal_special_characters(self) -> None:
        for name in (
            "part.scad",
            "liebherr v49(1).scad",
            "a[b]*.scad",
            "what?.scad",
        ):
            pattern = _glob_exact(name)
            self.assertTrue(
                fnmatch.fnmatch(name, pattern),
                f"{name!r} did not match {pattern!r}",
            )

    def test_gallery_dir_is_next_to_source(self) -> None:
        source = Path("C:/models/part.scad")
        self.assertEqual(gallery_dir(source), Path("C:/models/part_renders"))

    def test_parser_requires_render_file(self) -> None:
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])
        args = parser.parse_args(["--render-file", "C:/models/part.scad"])
        self.assertEqual(args.render_file, "C:/models/part.scad")

    def test_recent_registry_records_external_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "part_renders" / "index.html"
            index.parent.mkdir()
            index.write_text("gallery", encoding="utf-8")
            state = root / "state"
            _record_recent(index, root / "part.scad", state)
            payload = json.loads((state / "recent.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["items"][0]["index"], str(index))
            self.assertEqual(payload["items"][0]["name"], "part")


if __name__ == "__main__":
    unittest.main()
