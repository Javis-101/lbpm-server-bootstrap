#!/usr/bin/env python3
"""Fail closed if LBPM's media porosity disagrees with the immutable source ROI."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

POROSITY_RE = re.compile(
    r"Media\s+porosity\s*=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--log", required=True, type=Path)
    ap.add_argument("--tolerance", type=float, default=2.0e-6)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    source_roi = manifest.get("source_roi", {})
    if "porosity" not in source_roi:
        raise SystemExit("case manifest has no source_roi.porosity; prepare with SOP v1.3.2")
    expected = float(source_roi["porosity"])

    matches = POROSITY_RE.findall(args.log.read_text(errors="replace"))
    if not matches:
        raise SystemExit("LBPM log does not contain 'Media porosity = ...'")
    reported = float(matches[-1])

    if not math.isfinite(reported):
        raise SystemExit(f"LBPM reported non-finite media porosity: {reported}")
    delta = abs(reported - expected)
    print(f"source_roi_porosity={expected:.12g}")
    print(f"lbpm_media_porosity={reported:.12g}")
    print(f"absolute_difference={delta:.12g}")
    if delta > args.tolerance:
        raise SystemExit(
            f"LBPM media porosity mismatch: reported={reported:.12g}, "
            f"expected={expected:.12g}, tolerance={args.tolerance:.12g}"
        )
    print("LBPM_POROSITY_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
