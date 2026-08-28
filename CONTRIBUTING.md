# Contributing

Keep changes small, reproducible, and explicit about their validation boundary.

Before proposing a change:

1. run all Python tests and Bash syntax checks;
2. run `bash tests/test_installer_path_safety.sh` on Linux or WSL;
3. run `python3 scripts/publication_gate.py .`;
4. confirm no credentials, private config, research data, evidence archives, or upstream source archives are tracked;
5. update version and compatibility documentation when behavior or pinned identities change.

Changes affecting LBPM commit, CUDA assumptions, Open MPI, HDF5, the local patch, package checksums, bootstrap stage behavior, or destructive paths must state the exact test environment and provide fresh evidence. Static CI is not a substitute for a real Linux NVIDIA GPU validation run.

Do not silently repair, filter, crop, or relabel research RAW. Do not broaden the scientific claims beyond the evidence.
