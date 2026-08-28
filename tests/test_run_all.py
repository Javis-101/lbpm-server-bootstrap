from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_ALL = ROOT / "run_all.sh"


class RunAllContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RUN_ALL.read_text(encoding="utf-8")

    def test_shell_is_strict_and_has_small_cli(self):
        self.assertIn("set -Eeuo pipefail", self.text)
        for option in ("--raw", "--config", "--expected-raw-sha256", "--verbose"):
            self.assertIn(option, self.text)
        self.assertNotIn("--flux", self.text)
        self.assertNotIn("--contact-angle", self.text)

    def test_orchestrator_calls_real_installer_and_sop_entrypoints(self):
        for entrypoint in (
            "verify_sources.sh",
            "setup.sh",
            "bin/post_install_acceptance.sh",
            "bin/run_to_parameterization.sh",
        ):
            self.assertIn(entrypoint, self.text)
        self.assertIn("--skip-postinstall", self.text)
        self.assertIn("--first-case-smoke", self.text)

    def test_all_nine_stages_are_explicit(self):
        stages = (
            ("package_integrity", "stage_package_integrity"),
            ("host_preflight", "stage_host_preflight"),
            ("source_verification", "stage_source_verification"),
            ("installer", "stage_installer"),
            ("environment_identity", "stage_environment_identity"),
            ("sop_deployment", "stage_sop_deployment"),
            ("sop_acceptance", "stage_sop_acceptance"),
            ("raw_and_first_rock", "stage_raw_and_first_rock"),
        )
        for stage, function in stages:
            self.assertRegex(self.text, rf"\b{re.escape(stage)}\b")
            self.assertRegex(
                self.text,
                rf"run_stage\s+\d+\s+{re.escape(stage)}\s+.*\s+{re.escape(function)}\s+",
            )
        self.assertRegex(self.text, r"\bevidence\b")

    def test_run_root_is_fail_closed_without_tmp_fallback(self):
        self.assertNotIn("fallback_root", self.text)
        self.assertNotIn("using bounded fallback", self.text)
        self.assertIn("Unable to create configured BOOTSTRAP_RUN_ROOT", self.text)

    def test_dangerous_or_out_of_scope_automation_is_absent(self):
        lowered = self.text.lower()
        for forbidden in ("rm -rf", "sed -i", "curl ", "wget ", "apt install", "git clone"):
            self.assertNotIn(forbidden, lowered)
        self.assertNotRegex(lowered, r"\b(transpose|relabel|reshape)\b")

    def test_failure_path_always_invokes_summary_and_evidence(self):
        self.assertIn("finalize_run", self.text)
        self.assertIn("collect_evidence.py", self.text)
        self.assertIn("write_summary.py", self.text)
        self.assertRegex(self.text, r"trap\s+['\"]?on_exit")


if __name__ == "__main__":
    unittest.main()
