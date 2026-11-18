import os

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("WORKER_ENABLED", "false")
os.environ.setdefault("VECTOR_BACKEND", "chroma")
os.environ.setdefault("DATABASE_URL", "")

import tempfile as _tempfile

os.environ.setdefault("DATASET_DIR", _tempfile.mkdtemp(prefix="sd-datasets-"))
