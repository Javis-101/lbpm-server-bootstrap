from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "bin" / "common.sh"


def to_shell_path(path: Path) -> str:
    path = path.resolve()
    if os.name != "nt":
        return path.as_posix()
    drive = path.drive.rstrip(":").lower()
    tail = path.as_posix()[3:]
    return f"/mnt/{drive}/{tail}"


def bash_command(script: str) -> list[str]:
    if os.name == "nt":
        if not shutil.which("wsl.exe"):
            raise unittest.SkipTest("WSL is not available for the POSIX manifest contract test")
        distro = os.environ.get("SOP_TEST_WSL_DISTRIBUTION", "Ubuntu-24.04")
        return ["wsl.exe", "-d", distro, "--", "bash", "-lc", script]
    if not shutil.which("bash"):
        raise unittest.SkipTest("bash is not available for the POSIX manifest contract test")
    return ["bash", "-lc", script]


def run_bash(script: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(bash_command(script), capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise unittest.SkipTest(f"POSIX shell runner is unavailable: {exc}") from exc


class CompatibilityTests(unittest.TestCase):
    def test_manifest_get_returns_the_same_value_for_lf_and_crlf(self):
        source = shlex.quote(to_shell_path(COMMON))
        for ending in (b"\n", b"\r\n"):
            with self.subTest(ending=ending):
                with tempfile.TemporaryDirectory() as td:
                    manifest = Path(td) / "LBPM_BUILD_MANIFEST.txt"
                    manifest.write_bytes(b"INSTALLER_VERSION=2.0.6-offline" + ending)
                    script = (
                        f"source {source}; "
                        f"manifest_get INSTALLER_VERSION {shlex.quote(to_shell_path(manifest))}"
                    )
                    completed = run_bash(script)
                    self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
                    self.assertEqual(completed.stdout, b"2.0.6-offline\n")

    def test_installer_version_allowlist_accepts_205_206_and_207_only(self):
        source = shlex.quote(to_shell_path(COMMON))
        script = (
            f"source {source}; "
            "installer_version_supported 2.0.5-offline; "
            "installer_version_supported 2.0.6-offline; "
            "installer_version_supported 2.0.7-offline; "
            "if installer_version_supported 9.9.9-offline; then exit 3; fi"
        )
        completed = run_bash(script)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
