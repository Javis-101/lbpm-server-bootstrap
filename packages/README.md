# Offline package payloads

This directory is intentionally source-only. Git must not track the complete Portable Installer ZIP, SOP ZIP, upstream tarballs, or the frozen bootstrap ZIP.

`run_all.sh` is retained as the frozen orchestration reference and expects exact package archives with pinned hashes. Do not insert rebuilt archives under the v1.0.3 name. A future deployable artifact must use a new version, fresh hashes, and a complete real-GPU validation cycle.
