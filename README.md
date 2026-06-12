# Kolabri AI Engine

FastAPI service that handles RAG queries, NLP analytics, and chat interventions for the Kolabri collaborative learning platform.

## Architecture

```
Core API (Express) → AI Engine (FastAPI) → OpenAI-compatible API (LLM)
                                         → Qdrant (vector store)
                                         → MongoDB (event logs)
                                         → Redis (cache)
```

The AI Engine receives requests from the Core API (authenticated via `CORE_API_SECRET`). It processes documents, answers questions using course materials as context, and analyzes group discussions for intervention triggers.

## What it does

- **RAG pipeline**: embed documents into Qdrant via FastEmbed (local multilingual model), retrieve relevant chunks, generate answers via LLM
- **Document processing**: extract text from PDF, DOCX, PPTX (with optional OCR)
- **Chat intervention**: detect silence, off-topic drift, low engagement — generate prompts or summaries
- **NLP analytics**: engagement scoring, Higher Order Thinking detection, lexical diversity (Gini coefficient)
- **Process mining**: log learning events in XES-compatible format for ProM/Disco analysis
- **Safety layer**: prompt injection detection, toxicity scoring, PII masking
- **Reranking**: cross-encoder reranking for improved retrieval quality (requires `sentence-transformers`)

## Tech stack

- Python 3.11+, FastAPI
- OpenAI-compatible API (DeepSeek V4 Flash or compatible model)
- Qdrant (vector database, Docker port 6333)
- FastEmbed — `paraphrase-multilingual-MiniLM-L12-v2` (local embedding, 384 dim)
- MongoDB via Motor (async event logging)
- Redis (caching, rate limiting)
- Pydantic v2 (request/response validation)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Configure `.env`:
```
OPENAI_API_KEY=your-openai-compatible-key
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_MODEL=your-model-name
MONGODB_URL=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379
CORE_API_SECRET=shared-secret-key
QDRANT_URL=http://localhost:6333
```

### Optional: Enable reranking

Reranking improves retrieval quality but requires an additional package:

```bash
pip install sentence-transformers
```

When `sentence-transformers` is installed, the cross-encoder reranker activates automatically (`ENABLE_RERANKING=true` by default). Check status via `GET /api/health` — field `reranker_enabled` shows the actual runtime state.

Run:
```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

## API endpoints

All endpoints require `Authorization: Bearer <CORE_API_SECRET>`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Service health check |
| POST | `/api/ask` | RAG query (for @AI mentions in group chat) |
| POST | `/api/chat` | Orchestrated chat with intervention logic |
| POST | `/api/chat/personal` | Personal AI chat |
| POST | `/api/chat/personal/stream` | SSE streaming personal chat |
| POST | `/api/ingest` | Ingest single document |
| POST | `/api/ingest/batch` | Batch document ingestion |
| DELETE | `/api/documents/{id}` | Remove document from vector store |
| POST | `/api/intervention/analyze` | Check if group needs intervention |
| POST | `/api/intervention/summary` | Generate discussion summary |
| POST | `/api/intervention/prompt` | Generate discussion prompt |
| POST | `/api/analytics/engagement` | Text engagement analysis |
| GET | `/api/analytics/group/{id}` | Group dashboard data |
| GET | `/api/analytics/export` | Export process mining data |
| POST | `/api/goals/validate` | SMART goal validation |

## Testing

```bash
# Run all unit tests
pytest tests/test_unit/ -v

# With coverage
pytest tests/test_unit/ --cov=app

# Quick check (no coverage report)
pytest tests/test_unit/ -q --override-ini="addopts="
```

Current status (Juni 2026, verifikasi TA): **2411** tests passed (**2414** collected), **99,92%** line coverage on `app` (`pytest tests/ --cov=app`). See `../docs/evidence/bab4/PHASE0_SNAPSHOT.md`.

## Project structure

```
app/
  api/
    routes.py         All API route handlers
    schemas.py        Pydantic request/response models
  core/
    config.py         Settings (env vars)
    guardrails.py     Safety layer (injection, toxicity, PII)
    logging.py        Structured logging
  services/
    rag.py            RAG pipeline
    orchestration.py  Message flow coordinator
    intervention.py   Silence/engagement intervention
    embeddings.py     Gemini embedding service
    llm.py            LLM service
    vector_store.py   ChromaDB wrapper
    mongodb_logger.py Event logging
    conformance_checker.py  Process mining conformance
    injection_detector.py   Prompt injection detection
    pii_detector.py         PII detection and masking
    toxicity_scorer.py      Toxicity scoring
    grounding_verifier.py   Output grounding verification
    socratic_filter.py      Socratic scaffolding
    srl_classifier.py       Self-Regulated Learning phase classification
    xes_exporter.py         XES format export
  middleware/
    auth.py           API key authentication
main.py               FastAPI app entrypoint
tests/
  test_unit/          Unit tests (bagian dari suite 2411+)
```

## Related services

- [Kolabri Core API](../Kolabri-core-api) — Express backend, routes requests here
- [Kolabri Client App](../Kolabri-client-app) — Laravel + React frontend
