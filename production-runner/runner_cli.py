#!/usr/bin/env python3
import os
import sys
# Keep numerical libraries from spawning large CPU thread pools next to 8 GPU clients.
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
if sys.version_info < (3,9):
    raise SystemExit('Python >=3.9 is required. Select it with LBPM_RUNNER_PYTHON.')
try:
    from runner.cli import main
except ModuleNotFoundError as exc:
    raise SystemExit('DEPENDENCY_MISSING: '+str(exc)+'; select a Python with NumPy via LBPM_RUNNER_PYTHON. No online installation is attempted.')
if __name__=='__main__': raise SystemExit(main())
