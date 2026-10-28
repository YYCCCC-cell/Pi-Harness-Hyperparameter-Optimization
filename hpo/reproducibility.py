"""Process settings must be applied BEFORE Python/NumPy initialize."""

import os

PROCESS_ENV = {
    "PYTHONHASHSEED": "0",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
}


def require_process_environment():
    if any(os.environ.get(k) != v for k, v in PROCESS_ENV.items()):
        raise RuntimeError("Start Python with the documented reproducibility environment, "
                           "or use python -m hpo (which re-executes with it)")
