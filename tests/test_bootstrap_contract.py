from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "bin" / "bootstrap_contract.py"
LBPM_COMMIT = "6d686d354e5b8140841d3601e4c8c0e4e4b77e48"
PATCH_SHA256 = "fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_contract(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CONTRACT), *args], text=True, capture_output=True
    )


def make_installer_zip(
    path: Path,
    *,
        builder_version: str = "2.0.7",
        installer_version: str = "2.0.7-offline",
) -> Path:
    manifest = "\n".join(
        (
            "BUNDLE_FORMAT=2",
            f"BUILDER_VERSION={builder_version}",
            "LBPM_REPO=OPM/LBPM",
            f"LBPM_COMMIT={LBPM_COMMIT}",
            "LBPM_LOCAL_PATCHSET=outletlayersphase-fix-v1",
            "LBPM_LOCAL_PATCH=0001-fix-OutletLayersPhase.patch",
            f"LBPM_LOCAL_PATCH_SHA256={PATCH_SHA256}",
            "OPENMPI_VERSION=4.1.8",
            "ZLIB_VERSION=1.3.2",
            "HDF5_VERSION=1.14.6",
            "CREATED_AT=2026-08-27T00:00:00Z",
            "",
        )
    )
    installer = "\n".join(
        (
            "#!/usr/bin/env bash",
            f'INSTALLER_VERSION="{installer_version}"',
            'LBPM_REPO="https://github.com/OPM/LBPM"',
            f'LBPM_COMMIT="{LBPM_COMMIT}"',
            'PATCHSET_ID="outletlayersphase-fix-v1"',
            f'PATCH_SHA256="{PATCH_SHA256}"',
            'OPENMPI_VERSION="4.1.8"',
            'ZLIB_VERSION="1.3.2"',
            'HDF5_VERSION="1.14.6"',
            "INSTALLER_VERSION=$INSTALLER_VERSION",
            "LBPM_COMMIT=$LBPM_COMMIT",
            "",
        )
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        prefix = "LBPM-portable-offline-installer/"
        archive.writestr(prefix + "sources/BUNDLE_MANIFEST.txt", manifest)
        archive.writestr(prefix + "install_lbpm_offline.sh", installer)
        archive.writestr(prefix + "setup.sh", "#!/usr/bin/env bash\n")
        archive.writestr(prefix + "verify_sources.sh", "#!/usr/bin/env bash\n")
    return path


def make_sop_zip(path: Path, *, version: str = "1.3.2") -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        prefix = "LBPM-postinstall-SOP-v1.3.2/"
        archive.writestr(prefix + "VERSION", version + "\n")
        archive.writestr(prefix + "SHA256SUMS", "")
    return path


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class PackageIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def inspect(self, installer: Path, sop: Path) -> subprocess.CompletedProcess[str]:
        return run_contract(
            "inspect-packages",
            "--installer-zip",
            str(installer),
            "--sop-zip",
            str(sop),
            "--expected-installer-sha256",
            sha256(installer),
            "--expected-sop-sha256",
            sha256(sop),
            "--output",
            str(self.root / "identity.json"),
        )

    def test_inspect_packages_accepts_exact_pinned_identity(self):
        installer = make_installer_zip(self.root / "installer.zip")
        sop = make_sop_zip(self.root / "sop.zip")
        completed = self.inspect(installer, sop)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads((self.root / "identity.json").read_text())
        self.assertEqual(payload["builder_version"], "2.0.7")
        self.assertEqual(payload["installer_version"], "2.0.7-offline")
        self.assertEqual(payload["sop_version"], "1.3.2")
        self.assertEqual(payload["lbpm_commit"], LBPM_COMMIT)
        self.assertEqual(payload["patch_sha256"], PATCH_SHA256)

    def test_inspect_packages_rejects_wrong_builder_version(self):
        installer = make_installer_zip(
            self.root / "installer.zip", builder_version="2.0.5"
        )
        completed = self.inspect(installer, make_sop_zip(self.root / "sop.zip"))
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("BUILDER_VERSION", completed.stderr)

    def test_inspect_packages_rejects_wrong_sop_version(self):
        installer = make_installer_zip(self.root / "installer.zip")
        completed = self.inspect(
            installer, make_sop_zip(self.root / "sop.zip", version="1.3.0")
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("SOP VERSION", completed.stderr)

    def test_inspect_packages_rejects_zip_hash_mismatch(self):
        installer = make_installer_zip(self.root / "installer.zip")
        sop = make_sop_zip(self.root / "sop.zip")
        completed = run_contract(
            "inspect-packages",
            "--installer-zip",
            str(installer),
            "--sop-zip",
            str(sop),
            "--expected-installer-sha256",
            "0" * 64,
            "--expected-sop-sha256",
            sha256(sop),
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Installer ZIP SHA256", completed.stderr)


class StackContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        installer = make_installer_zip(self.root / "installer.zip")
        sop = make_sop_zip(self.root / "sop.zip")
        self.identity = self.root / "identity.json"
        completed = run_contract(
            "inspect-packages",
            "--installer-zip",
            str(installer),
            "--sop-zip",
            str(sop),
            "--expected-installer-sha256",
            sha256(installer),
            "--expected-sop-sha256",
            sha256(sop),
            "--output",
            str(self.identity),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def compatible_manifest(self) -> str:
        return "\n".join(
            (
                "INSTALLER_VERSION=2.0.7-offline",
                "LBPM_REPO=https://github.com/OPM/LBPM",
                f"LBPM_COMMIT={LBPM_COMMIT}",
                "PATCHSET_ID=outletlayersphase-fix-v1",
                f"PATCH_SHA256={PATCH_SHA256}",
                "OPENMPI_VERSION=4.1.8",
                "ZLIB_VERSION=1.3.2",
                "HDF5_VERSION=1.14.6",
                "",
            )
        )

    def check(
        self, manifest: Path, *, require_present: bool = False
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            "check-stack",
            "--manifest",
            str(manifest),
            "--package-identity",
            str(self.identity),
            "--output",
            str(self.root / "stack.json"),
        ]
        if require_present:
            arguments.append("--require-present")
        return run_contract(*arguments)

    def test_missing_manifest_selects_install(self):
        completed = self.check(self.root / "missing.txt")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads((self.root / "stack.json").read_text())
        self.assertEqual(payload["install_action"], "INSTALL")

    def test_exact_manifest_selects_compatible_skip(self):
        manifest = self.root / "LBPM_BUILD_MANIFEST.txt"
        manifest.write_text(self.compatible_manifest())
        completed = self.check(manifest)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads((self.root / "stack.json").read_text())
        self.assertEqual(payload["install_action"], "SKIP_EXISTING_COMPATIBLE")

    def test_strict_post_install_rejects_missing_manifest(self):
        completed = self.check(self.root / "missing.txt", require_present=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("POST_INSTALL_STACK_MISSING", completed.stderr)

    def test_strict_post_install_accepts_exact_manifest(self):
        manifest = self.root / "LBPM_BUILD_MANIFEST.txt"
        manifest.write_text(self.compatible_manifest())
        completed = self.check(manifest, require_present=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads((self.root / "stack.json").read_text())
        self.assertTrue(payload["manifest_present"])
        self.assertTrue(payload["compatible"])
        self.assertEqual(
            payload["install_action"], "VERIFIED_INSTALLED_COMPATIBLE"
        )

    def test_mismatch_fails_without_modifying_existing_manifest(self):
        manifest = self.root / "LBPM_BUILD_MANIFEST.txt"
        original = self.compatible_manifest().replace(LBPM_COMMIT, "wrong-commit")
        manifest.write_text(original)
        completed = self.check(manifest)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("FAIL_EXISTING_STACK_MISMATCH", completed.stderr)
        self.assertEqual(manifest.read_text(), original)


class RawAndSopReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_raw_correct_size_and_hash_pass_without_mutation(self):
        raw = self.root / "41_001.raw"
        raw.write_bytes(b"\0" * 2_097_152)
        before = sha256(raw)
        output = self.root / "raw.json"
        completed = run_contract(
            "check-raw",
            "--raw",
            str(raw),
            "--expected-bytes",
            "2097152",
            "--expected-sha256",
            before,
            "--output",
            str(output),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(output.read_text())["sha256_before"], before)
        self.assertEqual(sha256(raw), before)

    def test_raw_wrong_size_and_wrong_hash_fail(self):
        raw = self.root / "bad.raw"
        raw.write_bytes(b"\0" * 32)
        size_failure = run_contract(
            "check-raw", "--raw", str(raw), "--expected-bytes", "2097152"
        )
        self.assertNotEqual(size_failure.returncode, 0)
        self.assertIn("RAW byte size", size_failure.stderr)
        raw.write_bytes(b"\0" * 2_097_152)
        hash_failure = run_contract(
            "check-raw",
            "--raw",
            str(raw),
            "--expected-bytes",
            "2097152",
            "--expected-sha256",
            "f" * 64,
        )
        self.assertNotEqual(hash_failure.returncode, 0)
        self.assertIn("RAW SHA256", hash_failure.stderr)

    def acceptance_payload(self) -> dict:
        names = (
            "lbpm_identity",
            "patch",
            "dynamic_linking",
            "gpu",
            "cuda",
            "mpi",
            "testsetdevice",
            "piston",
        )
        return {
            "schema_version": 1,
            "sop_version": "1.3.2",
            "status": "PASS",
            "checks": {name: "PASS" for name in names},
            "provenance": {},
        }

    def test_acceptance_requires_all_eight_pass_checks(self):
        report = write_json(self.root / "acceptance.json", self.acceptance_payload())
        completed = run_contract("check-acceptance", "--report", str(report))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = self.acceptance_payload()
        payload["checks"].pop("piston")
        write_json(report, payload)
        failed = run_contract("check-acceptance", "--report", str(report))
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("required checks", failed.stderr)

    def test_acceptance_explicit_fail_is_rejected(self):
        payload = self.acceptance_payload()
        payload["status"] = "FAIL"
        report = write_json(self.root / "acceptance.json", payload)
        completed = run_contract("check-acceptance", "--report", str(report))
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Acceptance status", completed.stderr)

    def test_ready_requires_immutable_preserved_spanning_smoke_and_unchanged_raw(self):
        raw = self.root / "41_001.raw"
        raw.write_bytes(b"\1" * 2_097_152)
        raw_hash = sha256(raw)
        raw_check = write_json(
            self.root / "raw.json",
            {
                "status": "PASS",
                "source_file": str(raw.resolve()),
                "size": 2_097_152,
                "sha256_before": raw_hash,
            },
        )
        ready = write_json(
            self.root / "READY_FOR_PARAMETERIZATION.json",
            {
                "schema_version": 1,
                "sop_version": "1.3.2",
                "status": "READY",
                "environment": "ACCEPTED",
                "case_preparation": "PASS",
                "smoke_test": "PASS",
                "final": "READY",
                "source_immutable": True,
                "simulation_roi_preserved": True,
            },
        )
        manifest = write_json(
            self.root / "case_manifest.json",
            {
                "schema_version": 1,
                "sop_version": "1.3.2",
                "source_roi": {
                    "source_file": str(raw.resolve()),
                    "sha256": raw_hash,
                    "geometry_modified": False,
                },
                "simulation": {"roi_preserved": True},
            },
        )
        connectivity = write_json(
            self.root / "connectivity_report.json",
            {
                "schema_version": 1,
                "status": "PASS",
                "z_percolating": True,
                "geometry_modified": False,
            },
        )
        smoke = write_json(
            self.root / "PASS.json",
            {
                "schema_version": 1,
                "sop_version": "1.3.2",
                "status": "PASS",
                "numerical_sanity": "PASS",
            },
        )
        completed = run_contract(
            "check-ready",
            "--ready",
            str(ready),
            "--case-manifest",
            str(manifest),
            "--connectivity",
            str(connectivity),
            "--smoke-report",
            str(smoke),
            "--raw-check",
            str(raw_check),
            "--output",
            str(self.root / "ready-check.json"),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads((self.root / "ready-check.json").read_text())["status"],
            "PASS",
        )
        payload = json.loads(ready.read_text())
        payload["source_immutable"] = False
        write_json(ready, payload)
        failed = run_contract(
            "check-ready",
            "--ready",
            str(ready),
            "--case-manifest",
            str(manifest),
            "--connectivity",
            str(connectivity),
            "--smoke-report",
            str(smoke),
            "--raw-check",
            str(raw_check),
        )
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("source_immutable", failed.stderr)

    def test_ready_rejects_smoke_failure(self):
        raw = self.root / "41_001.raw"
        raw.write_bytes(b"\1" * 2_097_152)
        raw_hash = sha256(raw)
        paths = {
            "raw": write_json(
                self.root / "raw.json",
                {"status": "PASS", "source_file": str(raw.resolve()), "sha256_before": raw_hash},
            ),
            "ready": write_json(
                self.root / "ready.json",
                {
                    "schema_version": 1,
                    "sop_version": "1.3.2",
                    "status": "READY",
                    "environment": "ACCEPTED",
                    "case_preparation": "PASS",
                    "smoke_test": "FAIL",
                    "final": "READY",
                    "source_immutable": True,
                    "simulation_roi_preserved": True,
                },
            ),
            "manifest": write_json(
                self.root / "manifest.json",
                {
                    "schema_version": 1,
                    "sop_version": "1.3.2",
                    "source_roi": {
                        "source_file": str(raw.resolve()),
                        "sha256": raw_hash,
                        "geometry_modified": False,
                    },
                    "simulation": {"roi_preserved": True},
                },
            ),
            "connectivity": write_json(
                self.root / "connectivity.json",
                {
                    "schema_version": 1,
                    "status": "PASS",
                    "z_percolating": True,
                    "geometry_modified": False,
                },
            ),
            "smoke": write_json(
                self.root / "smoke.json",
                {
                    "schema_version": 1,
                    "sop_version": "1.3.2",
                    "status": "FAIL",
                    "numerical_sanity": "FAIL",
                },
            ),
        }
        completed = run_contract(
            "check-ready",
            "--ready",
            str(paths["ready"]),
            "--case-manifest",
            str(paths["manifest"]),
            "--connectivity",
            str(paths["connectivity"]),
            "--smoke-report",
            str(paths["smoke"]),
            "--raw-check",
            str(paths["raw"]),
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("smoke_test", completed.stderr)


if __name__ == "__main__":
    unittest.main()
