from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_version_and_readme_freeze_the_scientific_boundary(self):
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "1.3.2")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "SOP assumes the input 128³ RAW has already completed all scientific geometry preprocessing.",
            readme,
        )
        self.assertIn(
            "SOP validates the rock geometry but does not modify pore/solid topology.",
            readme,
        )
        self.assertIn("STATIC/LOCAL TEST PASS", readme)

    def test_shell_files_use_lf_and_bash_fail_fast(self):
        for path in sorted((ROOT / "bin").glob("*.sh")):
            data = path.read_bytes()
            self.assertNotIn(b"\r", data, path.name)
            self.assertTrue(data.startswith(b"#!/usr/bin/env bash\n"), path.name)
            self.assertIn(b"set -Eeuo pipefail", data, path.name)

    def test_sha256sums_exactly_covers_controlled_tree(self):
        checksum_path = ROOT / "SHA256SUMS"
        entries: dict[str, str] = {}
        for line in checksum_path.read_text(encoding="utf-8").splitlines():
            digest, relative = line.split("  ", 1)
            entries[relative.removeprefix("./")] = digest
        controlled = {
            path.relative_to(ROOT).as_posix(): path
            for path in ROOT.rglob("*")
            if path.is_file()
            and path != checksum_path
            and "__pycache__" not in path.parts
            and not path.name.endswith(".pyc")
        }
        self.assertEqual(set(entries), set(controlled))
        for relative, path in controlled.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entries[relative], relative)


if __name__ == "__main__":
    unittest.main()
