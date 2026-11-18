# SmartDatasheet AI

Application locale d’analyse de fiches techniques de composants électroniques. Elle combine extraction déterministe depuis PDF, workflow LangGraph, Ollama local, RAG local et interface React.

Aucun service payant ni OpenAI n’est utilisé.

## Prérequis

- Python 3.12 ou supérieur
- Node.js 20+
- Ollama avec le modèle `qwen2.5:1.5b`
- Tesseract OCR installé localement pour la route `/api/ocr/extract`
- PostgreSQL uniquement si `DATABASE_URL` est défini

## Installation

### Backend

```bash
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
```

Sous Windows :

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Copier `backend/.env.example` vers `backend/.env` puis ajuster les variables utiles. Le fichier `.env` est chargé automatiquement.

### Ollama

```bash
ollama pull qwen2.5:1.5b
ollama serve
```

La configuration refuse toute URL Ollama non locale et tout modèle différent de `qwen2.5:1.5b`.

### Modèle d’embedding RAG

Le premier chargement doit se faire avec accès réseau ; ensuite le modèle fonctionne hors ligne :

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

### Frontend

```bash
cd frontend
npm install
```

## Démarrage

Depuis la racine du dépôt :

```bash
uvicorn backend.app.main:app --reload --port 8000
```

```bash
cd frontend
npm run dev
```

L’interface est disponible sur `http://localhost:5173` et le proxy Vite envoie `/api` vers `http://localhost:8000`.

## Base de données

Par défaut, l’application utilise `backend/metadatasheet.db` en SQLite. Pour utiliser PostgreSQL :

```bash
export DATABASE_URL="postgresql://utilisateur:motdepasse@localhost:5432/smartdatasheet"
```

Les migrations sont gérées par Alembic :

```bash
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini current
```

La migration initiale est additive : elle ne supprime ni tables ni données.

## Authentification

L’authentification est désactivée par défaut en développement. En production :

```bash
export AUTH_ENABLED=true
export AUTH_TOKEN_TTL_SECONDS=86400
export BOOTSTRAP_ADMIN_EMAIL="admin@example.local"
export BOOTSTRAP_ADMIN_PASSWORD="choisir-un-mot-de-passe-long"
```

Au démarrage, un compte admin est créé si aucun utilisateur n’existe. Il est aussi possible d’appeler `POST /api/auth/bootstrap` une seule fois.

Les mots de passe sont hachés avec PBKDF2-SHA256 (260 000 itérations) et les tokens sont opaques, persistés et révocables.

## Worker de jobs

Les jobs créés par import de dataset sont traités par un worker local en arrière-plan.

Variables :

- `WORKER_ENABLED=true`
- `WORKER_POLL_SECONDS=2`

Les jobs peuvent aussi être démarrés, annulés et relancés via :

- `POST /api/imports/jobs/{job_id}/start`
- `POST /api/imports/jobs/{job_id}/cancel`
- `POST /api/imports/jobs/{job_id}/retry`

## RAG

Deux backends vectoriels sont disponibles :

- `VECTOR_BACKEND=chroma` : stockage local persistant dans `backend/rag_chroma`
- `VECTOR_BACKEND=pgvector` : nécessite PostgreSQL et `DATABASE_URL`

Endpoints :

- `GET /api/rag/health`
- `GET /api/rag/index`
- `POST /api/rag/reindex?document_id=1`
- `DELETE /api/rag/index/{document_id}`
- `POST /api/rag/ask`
- `GET /api/rag/sessions`

Les réponses incluent des citations avec page, bounding box et texte source. Si la preuve est insuffisante, l’API répond `insufficient_evidence`.

## OCR

L’OCR local utilise Tesseract via PyMuPDF et Pillow.

Endpoint : `POST /api/ocr/extract`.

Si le binaire Tesseract est absent, l’endpoint répond `503` avec un message public.

## API principale

### Documentation et santé

- `GET /api/health`
- `GET /api/ai/health`
- `GET /api/rag/health`

### Documents

- `POST /api/documents/upload`
- `GET /api/documents/`
- `GET /api/documents/export`
- `GET /api/documents/{id}`
- `GET /api/documents/{id}/file`
- `GET /api/documents/{id}/pages`
- `GET /api/documents/{id}/text-blocks`
- `GET /api/documents/{id}/parsed-fields`
- `GET /api/documents/{id}/tables`

### Imports

- `POST /api/imports/dataset`
- `GET /api/imports/datasets`
- `GET /api/imports/datasets/{id}`
- `POST /api/imports/datasheet?background=false`
- `POST /api/imports/datasheet/web?background=false`
- `GET /api/imports/downloads`
- `GET /api/imports/jobs`
- `GET /api/imports/jobs/{id}`
- `GET /api/imports/jobs/{id}/report?format=json|csv|excel`

### Auth et utilisateurs

- `POST /api/auth/bootstrap`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/auth/status`
- `GET /api/users`
- `PATCH /api/users/{id}`
- `POST /api/users/{id}/deactivate`

## Tests

Backend :

```bash
python -m pytest -q
```

Frontend :

```bash
cd frontend
npm run typecheck
npm run lint
npm test
```

Harnais d’évaluation du corpus :

```bash
python -m backend.app.evaluation.cli --list-cases
python -m backend.app.evaluation.cli --validate-only
python -m backend.app.evaluation.cli --case sn74lvc1g125
```

## Structure

```text
backend/
  app/
    agents/       LangGraph workflows
    ai/           Ollama client, prompts, structured output
    evaluation/   Corpus discovery, scoring, CLI
    extraction/   PyMuPDF extraction, table quality
    routes/       FastAPI routes
    services/     Documents, imports, jobs, auth, RAG, OCR
  alembic/        Migrations
  uploads/        PDF stockés par SHA-256
frontend/
  src/
    components/   UI components
    pages/        Routed views
    state/        AppContext, AuthContext
    __tests__/    Vitest tests
tests/
  cases/          Corpus de fiches techniques
```
