from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "bin" / "state_reports.py"
SOFTWARE_REPORT = ROOT / "bin" / "write_software_report.py"


def run_state(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(STATE), *args], text=True, capture_output=True
    )


class AcceptanceStateTests(unittest.TestCase):
    def test_stale_postinstall_pass_is_invalidated_before_failed_child(self):
        with tempfile.TemporaryDirectory() as td:
            validation = Path(td)
            marker = validation / "POSTINSTALL_PASS.txt"
            report = validation / "acceptance_report.json"
            marker.write_text("old pass")
            report.write_text('{"status":"PASS"}')
            started = run_state("acceptance-start", "--validation-dir", str(validation))
            self.assertEqual(started.returncode, 0, started.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse(report.exists())
            # Simulated child failure: no publication call occurs.
            self.assertFalse(marker.exists())

    def test_acceptance_pass_writes_consistent_json_and_atomic_text_marker(self):
        with tempfile.TemporaryDirectory() as td:
            validation = Path(td)
            software = validation / "software-verification.json"
            software.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "PASS",
                        "checks": {
                            "lbpm_identity": "PASS",
                            "patch": "PASS",
                            "dynamic_linking": "PASS",
                            "gpu": "PASS",
                            "cuda": "PASS",
                            "mpi": "PASS",
                        },
                        "provenance": {"lbpm_commit": "abc"},
                    }
                )
            )
            testset = validation / "TestSetDevice.PASS.json"
            piston = validation / "piston_result.json"
            testset.write_text(json.dumps({"schema_version": 1, "status": "PASS"}))
            piston.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "PASS",
                        "numerical_sanity": "PASS",
                    }
                )
            )
            completed = run_state(
                "acceptance-pass",
                "--validation-dir",
                str(validation),
                "--software-report",
                str(software),
                "--testsetdevice-report",
                str(testset),
                "--piston-report",
                str(piston),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads((validation / "acceptance_report.json").read_text())
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["checks"]["testsetdevice"], "PASS")
            self.assertEqual(report["checks"]["piston"], "PASS")
            self.assertTrue((validation / "POSTINSTALL_PASS.txt").is_file())
            self.assertFalse(list(validation.glob("*.tmp")))


class SoftwareReportTests(unittest.TestCase):
    def test_runtime_provenance_and_executable_hashes_are_machine_readable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "LBPM_BUILD_MANIFEST.txt"
            source = root / "ColorModel.cpp"
            executable = root / "lbpm_color_simulator"
            output = root / "software-verification.json"
            manifest.write_text(
                "LBPM_COMMIT=abc123\nPATCHSET_ID=patch-v1\nPATCH_SHA256=patchsha\n"
                "INSTALLER_VERSION=2.0.5-offline\nCUDA_ARCH=sm_86\n"
            )
            source.write_text("fixed source")
            executable.write_bytes(b"binary")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SOFTWARE_REPORT),
                    "--output",
                    str(output),
                    "--manifest",
                    str(manifest),
                    "--source",
                    str(source),
                    "--gpu-name",
                    "GPU X",
                    "--driver-version",
                    "999.1",
                    "--compute-capability",
                    "8.6",
                    "--cuda-version",
                    "12.4",
                    "--mpi-implementation",
                    "Open MPI",
                    "--mpi-version",
                    "4.1.8",
                    "--cuda-aware-mpi-status",
                    "SUPPORTED",
                    "--patch-status",
                    "APPLIED",
                    "--executable",
                    f"lbpm_color_simulator={executable}",
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["provenance"]["gpu"]["name"], ["GPU X"])
            self.assertEqual(payload["provenance"]["lbpm_commit"], "abc123")
            self.assertIn("sha256", payload["provenance"]["executables"]["lbpm_color_simulator"])


class CaseStateTests(unittest.TestCase):
    def test_stale_ready_is_invalidated_before_failed_preparation(self):
        with tempfile.TemporaryDirectory() as td:
            case = Path(td) / "case"
            case.mkdir()
            (case / "READY_FOR_PARAMETERIZATION.txt").write_text("old")
            (case / "READY_FOR_PARAMETERIZATION.json").write_text('{"status":"READY"}')
            started = run_state(
                "case-start", "--case-dir", str(case), "--case-id", "normal_case"
            )
            self.assertEqual(started.returncode, 0, started.stderr)
            self.assertFalse((case / "READY_FOR_PARAMETERIZATION.txt").exists())
            self.assertFalse((case / "READY_FOR_PARAMETERIZATION.json").exists())

    def test_case_id_accepts_safe_basename_and_rejects_path_forms(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            good = run_state(
                "case-start", "--case-dir", str(root / "good"), "--case-id", "normal_case"
            )
            self.assertEqual(good.returncode, 0, good.stderr)
            for index, case_id in enumerate(("../escape", "a/b", r"a\b", "/absolute", r"C:\absolute")):
                bad = run_state(
                    "case-start",
                    "--case-dir",
                    str(root / f"bad-{index}"),
                    "--case-id",
                    case_id,
                )
                self.assertNotEqual(bad.returncode, 0, case_id)
                self.assertIn("CASE_ID_INVALID", bad.stderr + bad.stdout)

    def test_non_empty_case_directory_fails_without_deleting_scientific_output(self):
        with tempfile.TemporaryDirectory() as td:
            case = Path(td) / "case"
            case.mkdir()
            result = case / "result.raw"
            result.write_bytes(b"important")
            completed = run_state(
                "case-start", "--case-dir", str(case), "--case-id", "normal_case"
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("CASE_DIRECTORY_NOT_EMPTY", completed.stderr + completed.stdout)
            self.assertEqual(result.read_bytes(), b"important")

    def make_prepared_case(self, root: Path):
        case = root / "case"
        case.mkdir()
        source = root / "source.raw"
        source.write_bytes(b"immutable-source")
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest = case / "case_manifest.json"
        connectivity = case / "connectivity_report.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "sop_version": "1.3.2",
                    "source_roi": {
                        "source_file": str(source),
                        "sha256": source_sha,
                        "geometry_modified": False,
                    },
                    "simulation": {"roi_preserved": True},
                }
            )
        )
        connectivity.write_text(
            json.dumps({"schema_version": 1, "status": "PASS", "geometry_modified": False})
        )
        acceptance = root / "acceptance_report.json"
        acceptance.write_text(json.dumps({"schema_version": 1, "status": "PASS", "checks": {}}))
        prepared = run_state(
            "case-prepared",
            "--case-dir",
            str(case),
            "--acceptance-report",
            str(acceptance),
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        prepared_state = json.loads((case / "CASE_PREPARED.json").read_text())
        self.assertEqual(prepared_state["source_sha256_before"], source_sha)
        self.assertEqual(prepared_state["source_sha256_after"], source_sha)
        return case, acceptance

    def test_case_prepared_rejects_source_changed_after_geometry_stage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case, acceptance = self.make_prepared_case(root)
            (case / "CASE_PREPARED.json").unlink()
            Path(json.loads((case / "case_manifest.json").read_text())["source_roi"]["source_file"]).write_bytes(b"changed")
            prepared = run_state(
                "case-prepared",
                "--case-dir",
                str(case),
                "--acceptance-report",
                str(acceptance),
            )
            self.assertNotEqual(prepared.returncode, 0)
            self.assertIn("SOURCE_ROCK_IMMUTABILITY_FAILED", prepared.stderr + prepared.stdout)

    def test_ready_distinguishes_smoke_pass_and_not_required(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case, acceptance = self.make_prepared_case(root)
            ready = run_state(
                "case-ready",
                "--case-dir",
                str(case),
                "--acceptance-report",
                str(acceptance),
                "--smoke-status",
                "NOT_REQUIRED",
            )
            self.assertEqual(ready.returncode, 0, ready.stderr)
            state = json.loads((case / "READY_FOR_PARAMETERIZATION.json").read_text())
            self.assertEqual(state["status"], "READY")
            self.assertEqual(state["case_preparation"], "PASS")
            self.assertEqual(state["smoke_test"], "NOT_REQUIRED")

            (case / "READY_FOR_PARAMETERIZATION.json").unlink()
            (case / "READY_FOR_PARAMETERIZATION.txt").unlink()
            smoke = case / "engineering-smoke-2000"
            smoke.mkdir()
            (smoke / "PASS.json").write_text(
                json.dumps({"schema_version": 1, "status": "PASS", "numerical_sanity": "PASS"})
            )
            ready2 = run_state(
                "case-ready",
                "--case-dir",
                str(case),
                "--acceptance-report",
                str(acceptance),
                "--smoke-status",
                "PASS",
            )
            self.assertEqual(ready2.returncode, 0, ready2.stderr)
            state2 = json.loads((case / "READY_FOR_PARAMETERIZATION.json").read_text())
            self.assertEqual(state2["smoke_test"], "PASS")


class ShellContractTests(unittest.TestCase):
    def text(self, name: str) -> str:
        return (ROOT / "bin" / name).read_text(encoding="utf-8")

    def test_every_modified_shell_is_fail_fast(self):
        for name in (
            "common.sh",
            "verify_lbpm_install.sh",
            "post_install_acceptance.sh",
            "prepare_case.sh",
            "run_to_parameterization.sh",
            "piston_acceptance.sh",
            "first_case_smoke_test.sh",
        ):
            self.assertIn("set -Eeuo pipefail", self.text(name), name)

    def test_prepare_case_is_fixed_128_preserve_only_and_rechecks_contract(self):
        text = self.text("prepare_case.sh")
        self.assertNotIn("--nx)", text)
        self.assertNotIn("--ny)", text)
        self.assertNotIn("--nz)", text)
        self.assertIn("--keep percolating", text)
        self.assertIn("Geometry mutation is no longer supported", text)
        self.assertIn("verify_case_contract.py", text)
        self.assertIn("state_reports.py", text)

    def test_ldd_command_failure_is_explicitly_fail_closed(self):
        text = self.text("verify_lbpm_install.sh")
        self.assertRegex(text, r"if\s+!\s+ldd_output=\"\$\(ldd")
        self.assertIn("ldd command failed", text)

    def test_acceptance_and_readiness_are_published_only_after_children(self):
        acceptance = self.text("post_install_acceptance.sh")
        self.assertLess(acceptance.index("acceptance-start"), acceptance.index("verify_lbpm_install.sh"))
        self.assertLess(acceptance.index("piston_acceptance.sh"), acceptance.index("acceptance-pass"))
        wrapper = self.text("run_to_parameterization.sh")
        self.assertLess(wrapper.index("prepare_case.sh"), wrapper.index("case-ready"))
        self.assertIn('SMOKE_STATUS="NOT_REQUIRED"', wrapper)

    def test_no_recursive_delete_remains_in_modified_shell(self):
        for name in (
            "post_install_acceptance.sh",
            "prepare_case.sh",
            "run_to_parameterization.sh",
            "piston_acceptance.sh",
            "first_case_smoke_test.sh",
        ):
            self.assertNotIn("rm -rf", self.text(name), name)

    def test_piston_and_first_case_require_numerical_sanity_artifacts(self):
        piston = self.text("piston_acceptance.sh")
        self.assertIn("save_8bit_raw = true", piston)
        self.assertIn("check_color_sanity.py", piston)
        self.assertIn("--expected-final-timestep 200", piston)
        self.assertIn("piston_result.json", piston)
        smoke = self.text("first_case_smoke_test.sh")
        self.assertIn("check_color_sanity.py", smoke)
        self.assertIn("check_case_output.py", smoke)
        self.assertIn("--expected-final-timestep 2000", smoke)
        self.assertIn("verify_case_contract.py", smoke)


if __name__ == "__main__":
    unittest.main()
