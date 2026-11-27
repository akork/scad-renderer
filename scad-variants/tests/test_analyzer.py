from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from scadvariants.analyzer import (
    analyze_scad,
    build_variants,
    canonical_tokens,
)


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / ".tmp-tests"
        base.mkdir(exist_ok=True)
        self.root = base / self._testMethodName
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_textual_switch_and_numeric_ignored(self):
        path = self.write(
            "a.scad",
            """
            mode = "a"; // [a, b]
            count = 3;  // [2, 3]
            sizes = ["10", "20"];
            if (mode == "a") cube(10);
            if (mode == "b") sphere(5);
            """,
        )
        scad = analyze_scad(path)
        self.assertEqual([s.name for s in scad.switches], ["mode"])
        self.assertEqual(scad.switches[0].options, ["a", "b"])
        variants = build_variants(scad.switches)
        self.assertEqual([v.variant_id for v in variants], ["mode-a", "mode-b"])

    def test_options_from_comparisons(self):
        path = self.write(
            "b.scad",
            """
            d = "h";
            module holder() {
                if (d == "h") cube(10);
                if (d == "s") sphere(5);
            }
            holder();
            """,
        )
        scad = analyze_scad(path)
        self.assertEqual(scad.switches[0].default, "h")
        self.assertEqual(scad.switches[0].options, ["h", "s"])

    def test_unused_module_does_not_invalidate_variant(self):
        path = self.write(
            "c.scad",
            """
            mode = "a"; // [a, b]
            size_a = 10;
            module a_part() { cube([size_a, 20, 12]); }
            module b_part() { cylinder(h = 18, r = 7, $fn = 48); }
            if (mode == "a") a_part();
            if (mode == "b") b_part();
            """,
        )
        scad = analyze_scad(path)
        a_before = canonical_tokens(scad, {"mode": "a"})
        b_before = canonical_tokens(scad, {"mode": "b"})

        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "cube([size_a, 20, 12]);", "cube([size_a, 20, 16]);"
            ),
            encoding="utf-8",
        )
        changed = analyze_scad(path)
        self.assertNotEqual(a_before, canonical_tokens(changed, {"mode": "a"}))
        self.assertEqual(b_before, canonical_tokens(changed, {"mode": "b"}))

    def test_unused_parameter_does_not_invalidate_variant(self):
        path = self.write(
            "d.scad",
            """
            mode = "a"; // [a, b]
            size_a = 10;
            module a_part() { cube([size_a, 20, 12]); }
            module b_part() { cylinder(h = 18, r = 7, $fn = 48); }
            if (mode == "a") a_part();
            if (mode == "b") b_part();
            """,
        )
        scad = analyze_scad(path)
        a_before = canonical_tokens(scad, {"mode": "a"})
        b_before = canonical_tokens(scad, {"mode": "b"})
        path.write_text(
            path.read_text(encoding="utf-8").replace("size_a = 10;", "size_a = 13;"),
            encoding="utf-8",
        )
        changed = analyze_scad(path)
        self.assertNotEqual(a_before, canonical_tokens(changed, {"mode": "a"}))
        self.assertEqual(b_before, canonical_tokens(changed, {"mode": "b"}))

    def test_nested_if_else_is_pruned(self):
        path = self.write(
            "e.scad",
            """
            d = "h"; // [h, s]
            module hpart() { cube([10, 10, 4]); }
            module spart() { cylinder(h = 8, r = 5, $fn = 32); }
            module holder() {
                difference() {
                    cube([12, 12, 10]);
                    if (d == "h") hpart(); else spart();
                }
            }
            holder();
            """,
        )
        scad = analyze_scad(path)
        h_before = canonical_tokens(scad, {"d": "h"})
        s_before = canonical_tokens(scad, {"d": "s"})
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "cube([10, 10, 4]);", "cube([10, 10, 6]);"
            ),
            encoding="utf-8",
        )
        changed = analyze_scad(path)
        self.assertNotEqual(h_before, canonical_tokens(changed, {"d": "h"}))
        self.assertEqual(s_before, canonical_tokens(changed, {"d": "s"}))

    def test_comments_do_not_invalidate(self):
        path = self.write(
            "f.scad",
            """
            mode = "a"; // [a, b]
            // old comment
            if (mode == "a") cube(10);
            if (mode == "b") sphere(5);
            """,
        )
        before = canonical_tokens(analyze_scad(path), {"mode": "a"})
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "// old comment", "// a completely different comment"
            ),
            encoding="utf-8",
        )
        after = canonical_tokens(analyze_scad(path), {"mode": "a"})
        self.assertEqual(before, after)

    def test_default_is_first_but_other_order_preserved(self):
        path = self.write(
            "g.scad",
            """
            p = "h";
            if (p == "a") cube(1);
            if (p == "h") cube(2);
            if (p == "c") cube(3);
            """,
        )
        scad = analyze_scad(path)
        self.assertEqual(scad.switches[0].options, ["h", "a", "c"])

    def test_dependencies(self):
        dep = self.write("lib.scad", "module thing() { cube(1); }")
        path = self.write(
            "main.scad",
            """
            use <lib.scad>
            thing();
            """,
        )
        scad = analyze_scad(path)
        self.assertEqual(scad.dependencies, [dep.resolve()])

    def test_no_switches_gives_default_variant(self):
        path = self.write("h.scad", "cube(10);")
        scad = analyze_scad(path)
        variants = build_variants(scad.switches)
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].variant_id, "default")

    def test_module_parameter_shadows_switch(self):
        path = self.write(
            "i.scad",
            """
            mode = "a"; // [a, b]
            module local(mode) {
                if (mode == "x") cube(1); else sphere(2);
            }
            if (mode == "a") local("x");
            if (mode == "b") local("y");
            """,
        )
        scad = analyze_scad(path)
        # The module's if must not be pruned using the global mode="a".
        # Changing the local else-branch therefore changes both variants.
        a_before = canonical_tokens(scad, {"mode": "a"})
        b_before = canonical_tokens(scad, {"mode": "b"})
        path.write_text(
            path.read_text(encoding="utf-8").replace("sphere(2);", "sphere(3);"),
            encoding="utf-8",
        )
        changed = analyze_scad(path)
        self.assertNotEqual(a_before, canonical_tokens(changed, {"mode": "a"}))
        self.assertNotEqual(b_before, canonical_tokens(changed, {"mode": "b"}))


if __name__ == "__main__":
    unittest.main()
