from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.publication_gate import audit_repository
import scripts.publication_gate as publication_gate_module


REQUIRED_FIXTURES = {
    "VERSION": "1.0.4-dev\n",
    "README.md": (
        "# LBPM Server Bootstrap\n\n"
        "LBPM Server Bootstrap is an independent community project. "
        "It is not an official OPM project.\n\n"
        "It does **not** constitute physical validation.\n"
    ),
    "LICENSE": "GNU GENERAL PUBLIC LICENSE Version 3\n",
    "THIRD_PARTY_NOTICES.md": "OPM/LBPM\nOpen MPI\nzlib\nHDF5\n",
    "CITATION.cff": 'cff-version: 1.2.0\nversion: "1.0.4-dev"\n',
    "CHANGELOG.md": "# Changelog\n",
    "SECURITY.md": "# Security Policy\n",
    "CONTRIBUTING.md": "# Contributing\n",
    ".gitignore": "*.raw\n*.zip\nbootstrap.env\n",
    "bootstrap.env.example": "STACK_DIR=/opt/lbpm-stack\n",
    "docs/validation/v1.0.3.md": (
        "ARTIFACT_IDENTITY=PASS\n"
        "V1_0_3_VALIDATION=PASS\n"
        "PUBLIC_RELEASE_ARTIFACT=PASS\n"
        "CORRECTION_REASON=EVIDENCE_LAYER_MISINTERPRETATION\n"
    ),
    "installer/lib/path_safety.sh": "validate_install_root() { return 0; }\n",
}


def make_candidate(root: Path) -> None:
    for relative, content in REQUIRED_FIXTURES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class PublicationGateTests(unittest.TestCase):
    def test_minimal_public_candidate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_candidate(root)
            self.assertEqual(audit_repository(root), [])

    def test_research_raw_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_candidate(root)
            (root / "sample.raw").write_bytes(b"research")
            self.assertIn("FORBIDDEN_TRACKED_FILE: sample.raw", audit_repository(root))

    def test_secret_value_is_rejected_without_flagging_policy_words(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_candidate(root)
            (root / "SECURITY.md").write_text(
                "Discuss tokens and authorization safely.\n"
                "GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456\n",
                encoding="utf-8",
            )
            errors = audit_repository(root)
            self.assertEqual(errors, ["SECRET_PATTERN: SECURITY.md:2:GITHUB_TOKEN"])

    def test_version_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_candidate(root)
            (root / "CITATION.cff").write_text(
                'cff-version: 1.2.0\nversion: "1.0.3"\n', encoding="utf-8"
            )
            self.assertIn(
                "VERSION_MISMATCH: VERSION=1.0.4-dev CITATION.cff=1.0.3",
                audit_repository(root),
            )

    def test_missing_notice_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_candidate(root)
            (root / "THIRD_PARTY_NOTICES.md").unlink()
            self.assertIn(
                "MISSING_REQUIRED_FILE: THIRD_PARTY_NOTICES.md", audit_repository(root)
            )

    def test_build_time_pending_metadata_cannot_regress_release_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_candidate(root)
            (root / "docs/validation/v1.0.3.md").write_text(
                "ARTIFACT_IDENTITY=PASS\n"
                "V1_0_3_GPU_VALIDATION_EVIDENCE=NOT_FOUND\n"
                "PUBLIC_RELEASE_ARTIFACT=BLOCKED\n"
                "OVERALL=NOT_READY\n",
                encoding="utf-8",
            )
            self.assertIn(
                "V1_0_3_VALIDATION_STATUS_INVALID",
                audit_repository(root),
            )

    def test_gate_does_not_report_its_own_detection_literals_as_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_candidate(root)
            scanner = root / "scripts/publication_gate.py"
            scanner.parent.mkdir(parents=True, exist_ok=True)
            scanner.write_text(
                Path(publication_gate_module.__file__).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            self.assertEqual(audit_repository(root), [])


if __name__ == "__main__":
    unittest.main()
