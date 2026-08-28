from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POROSITY_CHECK = ROOT / "bin" / "check_lbpm_porosity.py"
OUTPUT_CHECK = ROOT / "bin" / "check_case_output.py"


class PorosityCheckTests(unittest.TestCase):
    def make_case(self, reported: str):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        manifest = root / "case_manifest.json"
        log = root / "smoke.log"
        manifest.write_text(json.dumps({"source_roi": {"porosity": 0.25}}))
        log.write_text(reported)
        return td, manifest, log

    def run_check(self, manifest: Path, log: Path):
        return subprocess.run(
            [sys.executable, str(POROSITY_CHECK), "--manifest", str(manifest), "--log", str(log)],
            text=True,
            capture_output=True,
        )

    def test_porosity_check_accepts_source_roi_match(self):
        td, manifest, log = self.make_case("Media porosity = 0.250000\n")
        self.addCleanup(td.cleanup)
        completed = self.run_check(manifest, log)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertIn("LBPM_POROSITY_CHECK_PASS", completed.stdout)

    def test_porosity_check_rejects_mismatch(self):
        td, manifest, log = self.make_case("Media porosity = 0.300000\n")
        self.addCleanup(td.cleanup)
        completed = self.run_check(manifest, log)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("mismatch", (completed.stderr + completed.stdout).lower())

    def test_porosity_check_rejects_missing_value(self):
        td, manifest, log = self.make_case("Domain set.\n")
        self.addCleanup(td.cleanup)
        completed = self.run_check(manifest, log)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("media porosity", (completed.stderr + completed.stdout).lower())


class SourceRoiOutputTests(unittest.TestCase):
    def make_case(self, *, solid_changed=False):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        case = root / "case"
        output = root / "output"
        case.mkdir()
        output.mkdir()
        # source ROI: z,y,x = 2,2,2; four pore voxels and four solid voxels
        source = bytes([1, 0, 1, 0, 1, 0, 1, 0])
        (case / "rock_geometry.raw").write_bytes(source)
        manifest = {
            "source_roi": {"shape_zyx": [2, 2, 2], "pore_voxels": 4},
            "simulation": {
                "simulation_domain": {"shape_zyx": [4, 2, 2]},
                "roi_offset_zyx": [1, 0, 0],
            },
        }
        (case / "case_manifest.json").write_text(json.dumps(manifest))
        core = bytearray([2, 0, 1, 0, 2, 0, 1, 0])
        if solid_changed:
            core[1] = 1
        domain = bytes([2]) * 4 + bytes(core) + bytes([1]) * 4
        (output / "id_t2000.raw").write_bytes(domain)
        return td, case, output

    def run_check(self, case: Path, output: Path):
        return subprocess.run(
            [
                sys.executable,
                str(OUTPUT_CHECK),
                "--case-dir",
                str(case),
                "--output-dir",
                str(output),
                "--expected-final-timestep",
                "2000",
            ],
            text=True,
            capture_output=True,
        )

    def test_output_saturation_uses_source_roi_pore_basis(self):
        td, case, output = self.make_case()
        self.addCleanup(td.cleanup)
        completed = self.run_check(case, output)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertIn("CASE_OUTPUT_CHECK_PASS", completed.stdout)
        self.assertIn("0.500000 0.500000", completed.stdout)

    def test_output_rejects_source_solid_changed_to_fluid(self):
        td, case, output = self.make_case(solid_changed=True)
        self.addCleanup(td.cleanup)
        completed = self.run_check(case, output)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("source solid voxels changed", completed.stderr + completed.stdout)


if __name__ == "__main__":
    unittest.main()
