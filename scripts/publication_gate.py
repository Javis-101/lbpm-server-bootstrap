#!/usr/bin/env python3
"""Fail-closed static publication audit for the source repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CITATION.cff",
    "CHANGELOG.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "VERSION",
    ".gitignore",
    "bootstrap.env.example",
    "docs/validation/v1.0.3.md",
    "installer/lib/path_safety.sh",
)

FORBIDDEN_SUFFIXES = {
    ".raw",
    ".dat",
    ".tif",
    ".tiff",
    ".vtk",
    ".vti",
    ".zip",
    ".tgz",
    ".pem",
    ".key",
}
FORBIDDEN_NAMES = {
    ".env",
    "bootstrap.env",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
    "authorized_keys",
    "credentials",
}
IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache"}
MAX_TRACKED_FILE_BYTES = 5 * 1024 * 1024

ASSIGNMENT_SECRET = re.compile(
    r"(?im)^\s*(GITHUB_TOKEN|GH_TOKEN|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|"
    r"API_KEY|APIKEY|ACCESS_TOKEN)\s*[:=]\s*[\"']?([^\s\"'#]+)"
)
BEARER_SECRET = re.compile(r"(?im)^\s*authorization\s*[:=]\s*bearer\s+(\S+)")
PRIVATE_KEY_MARKERS = tuple(
    "-----BEGIN " + key_type + " PRIVATE KEY-----"
    for key_type in ("OPENSSH", "RSA", "EC")
)
PLACEHOLDERS = {"example", "changeme", "replace-me", "redacted", "none", "null"}


def _iter_files(root: Path):
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if any(part in IGNORED_PARTS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().strip('"\'').lower()
    return (
        not normalized
        or normalized in PLACEHOLDERS
        or normalized.startswith("<")
        or normalized.startswith("${")
        or normalized.startswith("your_")
        or normalized.startswith("your-")
    )


def _citation_version(text: str) -> str | None:
    match = re.search(r'(?m)^version:\s*["\']?([^"\'\s]+)', text)
    return match.group(1) if match else None


def audit_repository(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []

    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"MISSING_REQUIRED_FILE: {relative}")

    for path in _iter_files(root):
        relative = path.relative_to(root).as_posix()
        lowered = path.name.lower()
        lowered_relative = relative.lower()
        if (
            path.suffix.lower() in FORBIDDEN_SUFFIXES
            or lowered.endswith(".tar.gz")
            or lowered in FORBIDDEN_NAMES
            or lowered.startswith("restart.")
            or re.fullmatch(r"id\.\d+\.raw", lowered)
            or re.fullmatch(r"id_t\d+\.raw", lowered)
            or "validation-records/" in lowered_relative
        ):
            errors.append(f"FORBIDDEN_TRACKED_FILE: {relative}")
        if path.stat().st_size > MAX_TRACKED_FILE_BYTES:
            errors.append(
                f"OVERSIZED_TRACKED_FILE: {relative}:{path.stat().st_size}"
            )

        text = _read_text(path)
        if text is None:
            continue
        for marker in PRIVATE_KEY_MARKERS:
            if marker in text:
                line = text[: text.index(marker)].count("\n") + 1
                errors.append(f"SECRET_PATTERN: {relative}:{line}:PRIVATE_KEY")
        for match in ASSIGNMENT_SECRET.finditer(text):
            if not _is_placeholder(match.group(2)):
                line = text[: match.start()].count("\n") + 1
                errors.append(f"SECRET_PATTERN: {relative}:{line}:{match.group(1)}")
        for match in BEARER_SECRET.finditer(text):
            if not _is_placeholder(match.group(1)):
                line = text[: match.start()].count("\n") + 1
                errors.append(f"SECRET_PATTERN: {relative}:{line}:AUTHORIZATION_BEARER")

    version_path = root / "VERSION"
    citation_path = root / "CITATION.cff"
    if version_path.is_file() and citation_path.is_file():
        version = version_path.read_text(encoding="utf-8").strip()
        citation_version = _citation_version(
            citation_path.read_text(encoding="utf-8")
        )
        if citation_version != version:
            errors.append(
                f"VERSION_MISMATCH: VERSION={version} CITATION.cff={citation_version or 'MISSING'}"
            )

    readme_path = root / "README.md"
    if readme_path.is_file():
        readme = readme_path.read_text(encoding="utf-8").lower()
        for phrase in (
            "independent community project",
            "not an official opm project",
            "does **not** constitute physical validation",
        ):
            if phrase not in readme:
                errors.append(f"README_REQUIRED_BOUNDARY_MISSING: {phrase}")

    license_path = root / "LICENSE"
    if license_path.is_file():
        license_text = license_path.read_text(encoding="utf-8", errors="replace")
        if "GNU GENERAL PUBLIC LICENSE" not in license_text or "Version 3" not in license_text:
            errors.append("LICENSE_NOT_GPL_V3_TEXT")

    notices_path = root / "THIRD_PARTY_NOTICES.md"
    if notices_path.is_file():
        notices = notices_path.read_text(encoding="utf-8").lower()
        for project in ("opm/lbpm", "open mpi", "zlib", "hdf5"):
            if project not in notices:
                errors.append(f"THIRD_PARTY_NOTICE_MISSING: {project}")

    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    errors = audit_repository(Path(args.root))
    if errors:
        print("PUBLICATION_GATE=FAIL")
        for error in errors:
            print(error)
        return 1
    print("PUBLICATION_GATE=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
