from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "bin" / "check_color_sanity.py"
HEADER = "sw krw krn krwf krnf vw vn force pw pn wet peff\n"


class NumericalSanityTests(unittest.TestCase):
    def run_check(self, *, row="0.5 1 1 1 1 1 1 1 1 1 1 1\n", final=True, header=HEADER):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        log = root / "color.log"
        timelog = root / "timelog.csv"
        log.write_text("MPI rank=0 will use GPU ID 0\n")
        timelog.write_text(header + row)
        if final:
            (root / "id_t200.raw").write_bytes(bytes(16))
        completed = subprocess.run(
            [
                sys.executable,
                str(CHECK),
                "--run-log",
                str(log),
                "--timelog",
                str(timelog),
                "--output-dir",
                str(root),
                "--expected-final-timestep",
                "200",
                "--expected-raw-bytes",
                "16",
                "--tolerance",
                "1e-9",
            ],
            text=True,
            capture_output=True,
        )
        return td, completed

    def test_valid_timelog_gpu_binding_range_and_final_raw_pass(self):
        td, completed = self.run_check()
        self.addCleanup(td.cleanup)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertIn("COLOR_NUMERICAL_SANITY_PASS", completed.stdout)

    def test_nan_and_inf_are_rejected(self):
        for bad in ("nan", "inf", "-inf"):
            td, completed = self.run_check(row=f"0.5 1 1 1 1 1 1 1 1 1 1 {bad}\n")
            self.addCleanup(td.cleanup)
            self.assertNotEqual(completed.returncode, 0, bad)
            self.assertIn("non-finite", (completed.stderr + completed.stdout).lower())

    def test_saturation_uses_tolerance_but_rejects_real_out_of_range(self):
        td, within = self.run_check(row="1.0000000005 1 1 1 1 1 1 1 1 1 1 1\n")
        self.addCleanup(td.cleanup)
        self.assertEqual(within.returncode, 0, within.stderr + within.stdout)
        td2, outside = self.run_check(row="1.01 1 1 1 1 1 1 1 1 1 1 1\n")
        self.addCleanup(td2.cleanup)
        self.assertNotEqual(outside.returncode, 0)
        self.assertIn("saturation", (outside.stderr + outside.stdout).lower())

    def test_missing_required_columns_fails(self):
        td, completed = self.run_check(header="sw krw\n", row="0.5 1\n")
        self.addCleanup(td.cleanup)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("required columns", (completed.stderr + completed.stdout).lower())

    def test_missing_expected_final_raw_fails(self):
        td, completed = self.run_check(final=False)
        self.addCleanup(td.cleanup)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("id_t200.raw", completed.stderr + completed.stdout)


if __name__ == "__main__":
    unittest.main()
