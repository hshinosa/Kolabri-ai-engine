## rag-evaluation-dataset

Dataset query-answer pairs untuk evaluasi formal RAG pipeline.

### Requirements

#### REQ-RED-01: Struktur Dataset

Dataset disimpan di `data/evaluation/rag_evaluation_dataset.json`:

```json
{
  "metadata": {
    "version": "1.0",
    "created": "YYYY-MM-DD",
    "total_items": 20,
    "description": "Dataset evaluasi RAG pipeline Kolabri AI Engine",
    "course_topic": "Topik mata kuliah yang digunakan sebagai konteks"
  },
  "items": [
    {
      "id": "rag_001",
      "query": "Pertanyaan mahasiswa",
      "expected_answer_keywords": ["kata kunci 1", "kata kunci 2"],
      "expected_source_contains": "Nama dokumen atau bagian yang relevan",
      "difficulty": "easy | medium | hard",
      "query_type": "factual | conceptual | procedural"
    }
  ]
}
```

#### REQ-RED-02: Distribusi Item

- Total: 20 query
- Distribusi difficulty: 7 easy, 8 medium, 5 hard
- Distribusi query type: 8 factual, 7 conceptual, 5 procedural
- Semua query harus relevan dengan materi yang ada di knowledge base

#### REQ-RED-03: Kualitas Query

- Query harus realistis — mencerminkan pertanyaan mahasiswa nyata
- `expected_answer_keywords` minimal 2 kata kunci yang harus muncul di jawaban
- `expected_source_contains` harus merujuk ke dokumen yang benar-benar ada di vector store
