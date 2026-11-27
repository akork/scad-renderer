from __future__ import annotations

import fnmatch
import os
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

PROJECT_DIR = Path(__file__).resolve().parents[1]
TEMP_BASE = PROJECT_DIR / ".tmp-tests"
TEMP_BASE.mkdir(exist_ok=True)
sys.path.insert(0, str(PROJECT_DIR))


@contextmanager
def temp_dir():
    path = TEMP_BASE / f"t{uuid.uuid4().hex[:10]}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

from scad_drop import (  # noqa: E402
    StabilityTracker,
    StateStore,
    _ChoiceDialog,
    _glob_exact,
    _is_candidate,
    _process_image_name,
    copy_into_scad,
    discover,
    find_openscad,
    gallery_dir,
    renderer_running,
)


class HelperTests(unittest.TestCase):
    def test_glob_exact_matches_literal_special_characters(self):
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

    def test_candidate_filter(self):
        self.assertTrue(_is_candidate("part.scad", (".scad",)))
        self.assertTrue(_is_candidate("PART.SCAD", (".scad",)))
        self.assertFalse(_is_candidate("part.stl", (".scad",)))
        self.assertFalse(_is_candidate("~$part.scad", (".scad",)))
        self.assertFalse(_is_candidate("part.scad.crdownload", (".scad",)))
        self.assertFalse(_is_candidate("part.part.scad", (".scad",)))
        self.assertFalse(_is_candidate("part.tmp.scad", (".scad",)))

    def test_renderer_lock_probe(self):
        import msvcrt

        with temp_dir() as tmp:
            lock = Path(tmp) / ".watch.lock"
            lock.write_text("12345", encoding="ascii")
            self.assertFalse(renderer_running(lock))

            handle = lock.open("r+b")
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                self.assertTrue(renderer_running(lock))
            finally:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                handle.close()
            self.assertFalse(renderer_running(lock))

    def test_empty_lock_is_not_running(self):
        with temp_dir() as tmp:
            lock = Path(tmp) / ".watch.lock"
            lock.write_text("", encoding="ascii")
            self.assertFalse(renderer_running(lock))

    def test_find_openscad_explicit_path(self):
        with temp_dir() as tmp:
            fake = Path(tmp) / "openscad.exe"
            fake.write_bytes(b"MZ")
            self.assertEqual(find_openscad(str(fake)), fake)
            self.assertIsNone(find_openscad(str(Path(tmp) / "missing.exe")))

    def test_process_image_name_for_current_process(self):
        image = _process_image_name(os.getpid())
        self.assertIsNotNone(image)
        self.assertTrue(Path(image).name.lower().endswith(".exe"))


class StateTests(unittest.TestCase):
    def test_round_trip(self):
        with temp_dir() as tmp:
            path = Path(tmp) / "seen.json"
            store = StateStore(path)
            store.put("C:\\x\\a.scad", {"size": 1, "mtime_ns": 2, "status": "accepted"})
            again = StateStore(path)
            self.assertEqual(again.get("C:\\x\\a.scad")["status"], "accepted")

    def test_missing_or_broken_state_is_empty(self):
        with temp_dir() as tmp:
            path = Path(tmp) / "seen.json"
            path.write_text("{broken", encoding="utf-8")
            store = StateStore(path)
            self.assertEqual(store.files, {})


class StabilityTests(unittest.TestCase):
    def test_requires_unchanged_interval(self):
        now = [0.0]
        tracker = StabilityTracker(2.0, clock=lambda: now[0])
        stat = SimpleNamespace(st_size=10, st_mtime_ns=100)
        self.assertFalse(tracker.ready("a", stat))
        now[0] = 1.0
        self.assertFalse(tracker.ready("a", stat))
        now[0] = 2.5
        self.assertTrue(tracker.ready("a", stat))

    def test_change_resets_timer(self):
        now = [0.0]
        tracker = StabilityTracker(2.0, clock=lambda: now[0])
        first = SimpleNamespace(st_size=10, st_mtime_ns=100)
        changed = SimpleNamespace(st_size=11, st_mtime_ns=200)
        self.assertFalse(tracker.ready("a", first))
        now[0] = 1.0
        self.assertFalse(tracker.ready("a", changed))
        now[0] = 3.1
        self.assertTrue(tracker.ready("a", changed))

    def test_zero_seconds_is_immediate(self):
        tracker = StabilityTracker(0.0)
        self.assertTrue(
            tracker.ready("a", SimpleNamespace(st_size=1, st_mtime_ns=1))
        )


class CopyTests(unittest.TestCase):
    def test_identical_reused_and_different_gets_suffix(self):
        with temp_dir() as tmp:
            base = Path(tmp)
            downloads = base / "Downloads"
            scad = base / "SCAD"
            downloads.mkdir()
            source = downloads / "part.scad"
            source.write_text("cube(1);\n", encoding="utf-8")

            target, copied = copy_into_scad(source, scad)
            self.assertTrue(copied)
            self.assertEqual(target, scad / "part.scad")
            self.assertEqual(target.read_text(encoding="utf-8"), "cube(1);\n")

            same, copied = copy_into_scad(source, scad)
            self.assertFalse(copied)
            self.assertEqual(same, target)

            source.write_text("sphere(2);\n", encoding="utf-8")
            second, copied = copy_into_scad(source, scad)
            self.assertTrue(copied)
            self.assertEqual(second, scad / "part__2.scad")
            self.assertEqual(target.read_text(encoding="utf-8"), "cube(1);\n")
            self.assertEqual(second.read_text(encoding="utf-8"), "sphere(2);\n")

    def test_gallery_dir(self):
        self.assertEqual(
            gallery_dir(Path("SCAD") / "part.scad"),
            Path("SCAD") / "part_renders",
        )


class ChoiceDialogTests(unittest.TestCase):
    def _dialog(self):
        dialog = _ChoiceDialog(Path("x.scad"), 1234, True, None)
        dialog.root.withdraw()

        def cleanup():
            try:
                dialog.root.destroy()
            except Exception:
                pass

        self.addCleanup(cleanup)
        return dialog

    def test_checkbox_defaults_off(self):
        dialog = self._dialog()
        self.assertFalse(dialog.render_var.get())
        dialog._choose(False)
        self.assertEqual(dialog.result, (False, False))

    def test_render_without_open(self):
        dialog = self._dialog()
        dialog.render_var.set(True)
        dialog._choose(False)
        self.assertEqual(dialog.result, (False, True))

    def test_open_without_render(self):
        dialog = self._dialog()
        dialog._choose(True)
        self.assertEqual(dialog.result, (True, False))


class DiscoveryTests(unittest.TestCase):
    def test_top_level_and_recursive(self):
        with temp_dir() as tmp:
            downloads = Path(tmp)
            (downloads / "a.scad").write_text("a", encoding="utf-8")
            (downloads / "b.SCAD").write_text("b", encoding="utf-8")
            (downloads / "c.stl").write_text("c", encoding="utf-8")
            (downloads / "~$a.scad").write_text("x", encoding="utf-8")
            (downloads / "a.scad.crdownload").write_text("x", encoding="utf-8")
            sub = downloads / "sub"
            sub.mkdir()
            (sub / "d.scad").write_text("d", encoding="utf-8")

            top = {path.name for path, _ in discover(downloads, (".scad",))}
            self.assertEqual(top, {"a.scad", "b.SCAD"})

            deep = {
                path.name
                for path, _ in discover(downloads, (".scad",), recursive=True)
            }
            self.assertEqual(deep, {"a.scad", "b.SCAD", "d.scad"})


if __name__ == "__main__":
    unittest.main()
