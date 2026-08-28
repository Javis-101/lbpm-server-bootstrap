from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "bin" / "write_summary.py"
EVIDENCE = ROOT / "bin" / "collect_evidence.py"


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(script), *args], text=True, capture_output=True)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.run_root = Path(self.temp.name) / "20260827T231500Z-test01"
        (self.run_root / "state").mkdir(parents=True)
        write_json(
            self.run_root / "state" / "package-identity.json",
            {
                "status": "PASS",
                "installer_version": "2.0.7-offline",
                "sop_version": "1.3.2",
                "lbpm_commit": "abc123",
                "patchset_id": "patch-v1",
                "patch_sha256": "f" * 64,
            },
        )
        write_json(
            self.run_root / "state" / "raw-check.json",
            {"status": "PASS", "filename": "41_001.raw", "sha256_before": "a" * 64},
        )
        write_json(
            self.run_root / "state" / "acceptance-check.json",
            {
                "status": "PASS",
                "required_checks": {"testsetdevice": "PASS", "piston": "PASS"},
                "provenance": {"gpu_name": "fixture GPU", "cuda": "fixture CUDA"},
            },
        )
        write_json(
            self.run_root / "state" / "ready-check.json",
            {
                "status": "PASS",
                "source_immutable": True,
                "simulation_roi_preserved": True,
                "z_connectivity": "PASS",
                "smoke_test": "PASS",
            },
        )
        write_json(
            self.run_root / "host" / "prerequisites.json",
            {
                "schema_version": 1,
                "gfortran": {
                    "path": "/usr/bin/gfortran",
                    "version": "GNU Fortran fixture 13.3.0",
                    "link_test": "PASS",
                },
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_pass_summary_is_valid_and_scientifically_bounded(self):
        state = self.run_root / "bootstrap-state.json"
        for stage in (
            "package_integrity",
            "host_preflight",
            "source_verification",
            "installer",
            "environment_identity",
            "sop_deployment",
            "sop_acceptance",
            "raw_and_first_rock",
            "evidence",
        ):
            completed = run(
                SUMMARY,
                "record",
                "--state",
                str(state),
                "--run-id",
                self.run_root.name,
                "--stage",
                stage,
                "--status",
                "PASS",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
        completed = run(
            SUMMARY,
            "render",
            "--state",
            str(state),
            "--run-root",
            str(self.run_root),
            "--status",
            "PASS",
            "--install-action",
            "SKIPPED",
            "--archive",
            "/data/evidence.tar.gz",
            "--archive-sha256",
            "b" * 64,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads((self.run_root / "summary.json").read_text())
        self.assertEqual(payload["status"], "PASS")
        self.assertFalse(payload["production_physical_validation"])
        self.assertFalse(payload["production_parameters_decided"])
        self.assertEqual(payload["install_action"], "SKIPPED")
        self.assertEqual(payload["host_prerequisites"]["gfortran"]["link_test"], "PASS")
        summary = (self.run_root / "summary.txt").read_text()
        self.assertIn("OVERALL RESULT", summary)
        self.assertIn("GFortran                 GNU Fortran fixture 13.3.0", summary)
        self.assertIn("libgfortran link          PASS", summary)
        self.assertIn("PRODUCTION PHYSICAL VALIDATION: NOT PERFORMED", summary)
        self.assertIn("RUNNER: NOT DEVELOPED", summary)

    def test_fail_summary_keeps_failed_stage_and_reason(self):
        state = self.run_root / "bootstrap-state.json"
        run(
            SUMMARY,
            "record",
            "--state",
            str(state),
            "--run-id",
            self.run_root.name,
            "--stage",
            "host_preflight",
            "--status",
            "FAIL",
            "--detail",
            "nvcc missing",
        )
        completed = run(
            SUMMARY,
            "render",
            "--state",
            str(state),
            "--run-root",
            str(self.run_root),
            "--status",
            "FAIL",
            "--failed-stage",
            "host_preflight",
            "--fail-reason",
            "nvcc missing",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads((self.run_root / "summary.json").read_text())
        self.assertEqual(payload["status"], "FAIL")
        self.assertEqual(payload["failed_stage"], "host_preflight")
        self.assertEqual(payload["fail_reason"], "nvcc missing")


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.run_root = Path(self.temp.name) / "run-001"
        for directory in ("logs", "host", "validation", "simulations/case/engineering-smoke-2000"):
            (self.run_root / directory).mkdir(parents=True, exist_ok=True)
        (self.run_root / "summary.json").write_text('{"status":"PASS"}\n')
        (self.run_root / "summary.txt").write_text("PASS\n")
        (self.run_root / "summary.md").write_text("# PASS\n")
        (self.run_root / "logs" / "bootstrap.log").write_text("bounded\n")
        (self.run_root / "host" / "host-info.txt").write_text("fixture\n")
        write_json(
            self.run_root / "host" / "prerequisites.json",
            {
                "schema_version": 1,
                "gfortran": {
                    "path": "/usr/bin/gfortran",
                    "version": "GNU Fortran fixture 13.3.0",
                    "link_test": "PASS",
                },
            },
        )
        (self.run_root / "validation" / "acceptance_report.json").write_text("{}\n")
        write_json(
            self.run_root / "state" / "raw-check.json",
            {"filename": "41_001.raw", "sha256_before": "a" * 64, "status": "PASS"},
        )
        case = self.run_root / "simulations" / "case"
        (case / "READY_FOR_PARAMETERIZATION.json").write_text("{}\n")
        (case / "case_manifest.json").write_text("{}\n")
        (case / "connectivity_report.json").write_text("{}\n")
        (case / "engineering-smoke-2000" / "PASS.json").write_text(
            json.dumps({"final_raw": {"file": "id_t2000.raw", "sha256": "c" * 64}})
        )
        (case / "engineering-smoke-2000" / "id_t2000.raw").write_bytes(b"large-not-copied")
        (case / "Restart.00000").write_bytes(b"not-copied")
        (case / "result.h5").write_bytes(b"not-copied")
        self.installer = Path(self.temp.name) / "installer"
        (self.installer / "sources").mkdir(parents=True)
        (self.installer / "sources" / "BUNDLE_MANIFEST.txt").write_text("BUNDLE_FORMAT=2\n")
        self.stack_manifest = Path(self.temp.name) / "LBPM_BUILD_MANIFEST.txt"
        self.stack_manifest.write_text("INSTALLER_VERSION=2.0.7-offline\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_evidence_archive_is_bounded_and_hash_verified(self):
        completed = run(
            EVIDENCE,
            "--run-root",
            str(self.run_root),
            "--installer-root",
            str(self.installer),
            "--stack-manifest",
            str(self.stack_manifest),
            "--case-dir",
            str(self.run_root / "simulations" / "case"),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        archive = Path(result["archive"])
        sidecar = Path(result["sidecar"])
        self.assertTrue(archive.is_file())
        expected_hash = sidecar.read_text().split()[0]
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), expected_hash)
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
        self.assertTrue(any(name.endswith("summary.json") for name in names))
        self.assertTrue(any(name.endswith("host/prerequisites.json") for name in names))
        self.assertFalse(any(name.endswith(".raw") for name in names))
        self.assertFalse(any("Restart." in name or name.endswith(".h5") for name in names))
        metadata = json.loads(
            (self.run_root / "evidence" / "first-rock" / "final-raw-metadata.json").read_text()
        )
        self.assertEqual(metadata["filename"], "id_t2000.raw")
        self.assertEqual(
            (self.run_root / "evidence" / "first-rock" / "raw.sha256").read_text(),
            f"{'a' * 64}  41_001.raw\n",
        )
        ledger_lines = (self.run_root / "evidence" / "EVIDENCE_SHA256SUMS").read_text().splitlines()
        self.assertGreaterEqual(len(ledger_lines), 5)

    def test_fail_run_still_gets_evidence_archive(self):
        (self.run_root / "summary.json").write_text('{"status":"FAIL"}\n')
        completed = run(EVIDENCE, "--run-root", str(self.run_root))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "PASS")
        inventory = json.loads(
            (self.run_root / "evidence" / "evidence_inventory.json").read_text()
        )
        self.assertIn("NOT_PRODUCED", inventory["statuses"].values())


if __name__ == "__main__":
    unittest.main()
