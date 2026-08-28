from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SourcePublicationContractTests(unittest.TestCase):
    def test_version_marks_behavior_changing_source_as_development(self) -> None:
        self.assertEqual(
            (ROOT / "VERSION").read_text(encoding="utf-8").strip(), "1.0.4-dev"
        )

    def test_source_tree_excludes_release_and_upstream_archives(self) -> None:
        forbidden = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            lowered = path.name.lower()
            if lowered.endswith((".zip", ".tar.gz", ".tgz")):
                forbidden.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(forbidden, [])

    def test_validated_artifact_identity_and_release_status_are_documented(self) -> None:
        validation = (ROOT / "docs/validation/v1.0.3.md").read_text(encoding="utf-8")
        self.assertIn(
            "f1bf6e5649769aba5d246535d3f74f1cbc4032ebab78ee9bb54fa7a439360507",
            validation,
        )
        self.assertIn("ARTIFACT_IDENTITY=PASS", validation)
        self.assertIn("V1_0_3_VALIDATION=PASS", validation)
        self.assertIn("PUBLIC_RELEASE_ARTIFACT=PASS", validation)
        self.assertIn(
            "CORRECTION_REASON=EVIDENCE_LAYER_MISINTERPRETATION", validation
        )

    def test_linux_scripts_and_python_helpers_use_lf(self) -> None:
        candidates = list(ROOT.rglob("*.sh")) + list(ROOT.rglob("*.py"))
        self.assertGreater(len(candidates), 10)
        for path in candidates:
            if "__pycache__" not in path.parts:
                self.assertNotIn(b"\r\n", path.read_bytes(), str(path.relative_to(ROOT)))


if __name__ == "__main__":
    unittest.main()
