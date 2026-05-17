## Why

The inspection found that the current RAG path has room for improvement around retrieval precision, configurable ranking behavior, and evaluation discipline. This change is needed now to raise answer quality and make retrieval tuning an explicit, spec-driven capability instead of an implementation detail.

## What Changes

- Introduce a capability for configurable retrieval quality controls across retrieval and ranking stages.
- Introduce a capability for retrieval evaluation and quality measurement that can guide future tuning.
- Define behavior expectations for ranking, filtering, and fallback handling in the RAG path.
- Make quality-sensitive RAG behavior configurable instead of relying on hidden defaults.

## Capabilities

### New Capabilities
- `rag-retrieval-quality-controls`: Configurable retrieval, filtering, and ranking behavior for better answer relevance.
- `rag-quality-evaluation`: Requirements for measuring and validating retrieval quality changes before adoption.

### Modified Capabilities
- None.

## Impact

- Affected areas: `app/services/rag.py`, `app/services/vector_store.py`, `app/services/reranker.py`, retrieval-related config, and evaluation/testing utilities.
- Affected systems: vector store search, ranking pipeline, response quality, and tuning workflow.
- Dependencies/systems impacted: embedding retrieval settings, reranking path, and quality verification process.
