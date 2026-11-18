import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.database import SessionLocal
from backend.app.services.rag_index_service import reindex


def main() -> int:
    parser = argparse.ArgumentParser(description="Réindexe les PDF persistés dans le stockage vectoriel local.")
    parser.add_argument("--document-id", type=int, default=None, help="Identifiant d'un document à réindexer.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = reindex(db, document_id=args.document_id)
    finally:
        db.close()

    print(result["message"])
    if args.document_id is not None and result["indexed_documents"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
