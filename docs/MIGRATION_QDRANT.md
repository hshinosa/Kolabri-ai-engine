# Migration: ChromaDB → Qdrant + FastEmbed

## Overview

Migrated the vector database from ChromaDB to Qdrant, and the embedding service from Google Gemini API to local FastEmbed (ONNX-based).

## Why

| Aspect | ChromaDB (before) | Qdrant (after) |
|---|---|---|
| Production readiness | Prototyping tool | Production-grade |
| Scalability | Single-node | Distributed, sharding |
| Persistence | SQLite (fragile) | Custom engine (robust) |
| Docker image | Heavy, crash-prone | ~50MB, stable |
| Embedding | Gemini API (paid, latency) | Local FastEmbed (free, ~10ms) |
| Offline | Requires internet | Fully offline capable |

## Changes Made

### Files Modified
- `app/services/embeddings.py` - `GeminiEmbeddingService` → `LocalEmbeddingService` (FastEmbed)
- `app/services/vector_store.py` - ChromaDB client → Qdrant client
- `app/core/config.py` - Removed `CHROMA_*`, added `QDRANT_*` and `EMBEDDING_MODEL`
- `app/core/logging.py` - Changed logger name from `chromadb` to `qdrant_client`
- `main.py` - Removed `CHROMA_PERSIST_DIR` directory creation
- `requirements.txt` - Removed `chromadb`, added `qdrant-client[fastembed]`
- `.env.example` - Updated config variables
- `docker-compose.yml` - Added Qdrant container
- `tests/conftest.py` - Added qdrant/fastembed mocks

### New Environment Variables
```env
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_PREFIX=kolabri
EMBEDDING_MODEL=intfloat/multilingual-e5-small
```

### Removed Environment Variables
```env
CHROMA_PERSIST_DIR (removed)
CHROMA_COLLECTION_PREFIX (removed)
GEMINI_API_KEY (no longer needed for embeddings)
GOOGLE_API_KEY (no longer needed for embeddings)
```

## Running Qdrant

### Docker (recommended)
```bash
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage qdrant/qdrant:latest
```

### Docker Compose (full stack)
```bash
docker-compose up qdrant -d
```

### Verify
```bash
curl http://localhost:6333/healthz
```

## Re-ingesting Documents

After migration, all documents must be re-ingested because:
1. Embedding dimensions changed (768 → 384)
2. Vector database format changed (ChromaDB SQLite → Qdrant)

```bash
# Start services
docker-compose up qdrant ai-engine -d

# Re-ingest via API
curl -X POST http://localhost:8001/api/ingest \
  -F "file=@document.pdf" \
  -F "course_id=course_123"
```

## Embedding Model

Using `intfloat/multilingual-e5-small`:
- 384 dimensions
- Supports 100+ languages including Indonesian
- ~10ms per embedding (vs ~200-500ms for Gemini API)
- No API key required
- ONNX runtime (no PyTorch dependency)
- ~130MB model download (cached after first use)

## API Interface (unchanged)

The public API remains identical. No changes needed in Core API or Client App.
All endpoints (`/api/ask`, `/api/ingest`, `/api/chat`, etc.) work the same way.
