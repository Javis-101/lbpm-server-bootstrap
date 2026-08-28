from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "bin" / "prepare_rock_case.py"
VERIFY = ROOT / "bin" / "verify_case_contract.py"


def load_prepare_module():
    spec = importlib.util.spec_from_file_location("prepare_rock_case", PREPARE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREPARE_MODULE = load_prepare_module()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def voxel_index(x: int, y: int, z: int, nx: int, ny: int) -> int:
    return z * ny * nx + y * nx + x


class ConnectivityValidatorTests(unittest.TestCase):
    def analyse(self, pores: set[tuple[int, int, int]], shape=(3, 3, 3)):
        nz, ny, nx = shape
        raw = bytearray(nx * ny * nz)
        for x, y, z in pores:
            raw[voxel_index(x, y, z, nx, ny)] = 1
        before = bytes(raw)
        result = PREPARE_MODULE.connectivity_6(before, nx, ny, nz, 1)
        self.assertEqual(bytes(raw), before)
        return result

    def test_z_spanning_component(self):
        result = self.analyse({(1, 1, 0), (1, 1, 1), (1, 1, 2)})
        self.assertTrue(result["z_percolating"])
        self.assertEqual(result["connected_component_count"], 1)
        self.assertEqual(result["spanning_voxels"], 3)

    def test_non_spanning_isolated_component_is_reported_not_deleted(self):
        result = self.analyse({(1, 1, 0), (1, 1, 1), (1, 1, 2), (0, 0, 1)})
        self.assertTrue(result["z_percolating"])
        self.assertEqual(result["connected_component_count"], 2)
        self.assertEqual(result["pore_voxels"], 4)
        self.assertEqual(result["spanning_voxels"], 3)

    def test_multiple_spanning_components(self):
        pores = {(0, 0, z) for z in range(3)} | {(2, 2, z) for z in range(3)}
        result = self.analyse(pores)
        self.assertEqual(result["spanning_component_count"], 2)
        self.assertEqual(result["spanning_voxels"], 6)

    def test_dead_end_branch_remains_part_of_spanning_component(self):
        result = self.analyse({(1, 1, 0), (1, 1, 1), (1, 1, 2), (2, 1, 1)})
        self.assertTrue(result["z_percolating"])
        self.assertEqual(result["spanning_voxels"], 4)

    def test_diagonal_only_connection_does_not_span_under_6_neighbor_rule(self):
        result = self.analyse({(0, 0, 0), (1, 1, 1), (2, 2, 2)})
        self.assertFalse(result["z_percolating"])
        self.assertEqual(result["connected_component_count"], 3)


class PrepareContractTests(unittest.TestCase):
    def run_prepare(
        self,
        raw: bytes,
        *,
        shape=(4, 2, 2),
        test_shape=True,
        extra_args: list[str] | None = None,
        source_inside_case: str | None = None,
    ):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        case = root / "case"
        if source_inside_case:
            case.mkdir()
            src = case / source_inside_case
        else:
            src = root / "source.raw"
        src.write_bytes(raw)
        nz, ny, nx = shape
        cmd = [
            sys.executable,
            str(PREPARE),
            "--input",
            str(src),
            "--case-dir",
            str(case),
            "--nx",
            str(nx),
            "--ny",
            str(ny),
            "--nz",
            str(nz),
            "--reservoir-layers",
            "3",
            "--keep",
            "all",
        ]
        if test_shape:
            cmd.append("--test-only-allow-non-128")
        if extra_args:
            cmd.extend(extra_args)
        completed = subprocess.run(cmd, text=True, capture_output=True)
        return td, src, case, completed

    def test_production_128_cube_sparse_spanning_raw_passes(self):
        n = 128
        raw = bytearray(n**3)
        for z in range(n):
            raw[voxel_index(0, 0, z, n, n)] = 1
        td, src, case, completed = self.run_prepare(
            bytes(raw), shape=(n, n, n), test_shape=False
        )
        self.addCleanup(td.cleanup)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        manifest = json.loads((case / "case_manifest.json").read_text())
        self.assertEqual(manifest["source_roi"]["shape_zyx"], [128, 128, 128])
        self.assertFalse(manifest["source_roi"]["geometry_modified"])
        self.assertEqual(manifest["source_roi"]["sha256"], digest(src.read_bytes()))

    def test_wrong_byte_size_fails(self):
        td, _, _, completed = self.run_prepare(bytes(15))
        self.addCleanup(td.cleanup)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("RAW size mismatch", completed.stderr + completed.stdout)

    def test_non_128_production_shape_fails_even_when_byte_size_matches(self):
        td, _, _, completed = self.run_prepare(bytes([1]) * 16, test_shape=False)
        self.addCleanup(td.cleanup)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("INPUT_ROCK_SHAPE_UNSUPPORTED", completed.stderr + completed.stdout)

    def test_all_solid_fails_connectivity_without_geometry_output(self):
        td, src, case, completed = self.run_prepare(bytes(16))
        self.addCleanup(td.cleanup)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("INPUT_ROCK_CONNECTIVITY_FAILED", completed.stderr + completed.stdout)
        self.assertEqual(src.read_bytes(), bytes(16))
        self.assertFalse((case / "rock_geometry.raw").exists())
        report = json.loads((case / "connectivity_report.json").read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["geometry_modified"])

    def test_all_pore_fixture_is_preserved_byte_for_byte(self):
        raw = bytes([1]) * 16
        td, src, case, completed = self.run_prepare(raw)
        self.addCleanup(td.cleanup)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertEqual((case / "rock.raw").read_bytes(), raw)
        self.assertEqual((case / "rock_geometry.raw").read_bytes(), raw)
        self.assertEqual(src.read_bytes(), raw)

    def test_valid_binary_labels_pass_and_unknown_label_fails(self):
        valid = bytes([1, 0, 0, 0] * 4)
        td, _, _, completed = self.run_prepare(valid)
        self.addCleanup(td.cleanup)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)

        invalid = bytearray(valid)
        invalid[1] = 7
        td2, _, _, completed2 = self.run_prepare(bytes(invalid))
        self.addCleanup(td2.cleanup)
        self.assertNotEqual(completed2.returncode, 0)
        self.assertIn("INPUT_ROCK_LABEL_INVALID", completed2.stderr + completed2.stdout)

    def test_equal_solid_and_pore_labels_are_rejected(self):
        raw = bytes([1]) * 16
        td, _, _, completed = self.run_prepare(
            raw, extra_args=["--solid-value", "1", "--pore-value", "1"]
        )
        self.addCleanup(td.cleanup)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("solid and pore labels must differ", (completed.stderr + completed.stdout).lower())

    def test_deprecated_percolating_policy_fails_without_modifying_source(self):
        raw = bytes([1, 0, 0, 0] * 4)
        td, src, case, completed = self.run_prepare(raw, extra_args=["--keep", "percolating"])
        self.addCleanup(td.cleanup)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Geometry mutation is no longer supported", completed.stderr + completed.stdout)
        self.assertEqual(src.read_bytes(), raw)
        self.assertFalse((case / "rock_geometry.raw").exists())

    def test_source_collision_with_candidate_output_fails_before_write(self):
        raw = bytes([1, 0, 0, 0] * 4)
        before = digest(raw)
        td, src, _, completed = self.run_prepare(
            raw, source_inside_case="rock_geometry.raw"
        )
        self.addCleanup(td.cleanup)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("SOURCE_OUTPUT_PATH_COLLISION", completed.stderr + completed.stdout)
        self.assertEqual(digest(src.read_bytes()), before)

    def test_augmented_domain_embeds_exact_source_roi_and_reports_contract(self):
        raw = bytes([1, 0, 0, 0] * 4)
        td, src, case, completed = self.run_prepare(raw)
        self.addCleanup(td.cleanup)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        manifest = json.loads((case / "case_manifest.json").read_text())
        report = json.loads((case / "connectivity_report.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(report["schema_version"], 1)
        self.assertTrue(manifest["simulation"]["roi_preserved"])
        self.assertEqual(
            manifest["saturation_contract"]["pore_space_basis"],
            "source_128_cube_roi",
        )
        ext = (case / "rock_waterdrive.raw").read_bytes()
        start = manifest["simulation"]["roi_offset_zyx"][0] * 4
        self.assertEqual(ext[start : start + len(raw)], src.read_bytes())
        self.assertEqual(report["connectivity_definition"]["neighbors"], 6)
        self.assertEqual(report["flow_axis"], "+Z")
        self.assertFalse(report["geometry_modified"])

    def test_verify_case_contract_rechecks_source_hash_and_embedded_roi(self):
        raw = bytes([1, 0, 0, 0] * 4)
        td, _, case, completed = self.run_prepare(raw)
        self.addCleanup(td.cleanup)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        verified = subprocess.run(
            [sys.executable, str(VERIFY), "--case-dir", str(case)],
            text=True,
            capture_output=True,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.assertIn("CASE_CONTRACT_VERIFICATION_PASS", verified.stdout)

    def test_verify_case_contract_rejects_source_changed_after_preparation(self):
        raw = bytes([1, 0, 0, 0] * 4)
        td, src, case, completed = self.run_prepare(raw)
        self.addCleanup(td.cleanup)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        src.write_bytes(bytes([1]) * 16)
        verified = subprocess.run(
            [sys.executable, str(VERIFY), "--case-dir", str(case)],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn("source RAW is missing or its SHA256 changed", verified.stderr + verified.stdout)

    def test_verify_case_contract_rejects_corrupted_embedded_roi(self):
        raw = bytes([1, 0, 0, 0] * 4)
        td, _, case, completed = self.run_prepare(raw)
        self.addCleanup(td.cleanup)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        domain = case / "rock_waterdrive.raw"
        corrupted = bytearray(domain.read_bytes())
        corrupted[12] ^= 1
        domain.write_bytes(corrupted)
        verified = subprocess.run(
            [sys.executable, str(VERIFY), "--case-dir", str(case)],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn("simulation domain", (verified.stderr + verified.stdout).lower())


if __name__ == "__main__":
    unittest.main()
