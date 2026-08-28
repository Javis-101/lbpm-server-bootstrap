# Templates

Production physics is intentionally not frozen in SOP v1.3.2.
`bin/prepare_rock_case.py` creates `input-production.TEMPLATE.db` in each case directory with explicit placeholders.

The generated v1.3.2 production template uses `Domain.Filename = "rock_waterdrive.raw"`; `ID.00000` is retained as decomposition/QC evidence only. The original 128³ source ROI embedded in `rock_waterdrive.raw` is verified byte-for-byte and is never filtered or relabeled by the SOP.
