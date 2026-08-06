## gold-standard-dataset

Dataset berlabel untuk evaluasi Logic Listener, berisi 30 segmen diskusi yang merepresentasikan skenario nyata pembelajaran kolaboratif.

### Requirements

#### REQ-GSD-01: Struktur Dataset

Dataset disimpan di `data/evaluation/logic_listener_gold_standard.json` dengan struktur:

```json
{
  "metadata": {
    "version": "1.0",
    "created": "YYYY-MM-DD",
    "total_items": 30,
    "description": "Gold standard dataset untuk evaluasi Logic Listener Kolabri AI Engine",
    "labeling_guidelines": "..."
  },
  "items": [
    {
      "id": "item_001",
      "intervention_type": "off_topic | silence | participation_inequity",
      "expected_should_intervene": true,
      "input": { ... },
      "labeling_rationale": "Alasan mengapa item ini dilabeli demikian"
    }
  ]
}
```

#### REQ-GSD-02: Distribusi Item

Dataset harus berisi tepat 30 item dengan distribusi seimbang:
- 10 item untuk `off_topic` (5 positive: harus intervensi, 5 negative: tidak perlu)
- 10 item untuk `silence` (5 positive, 5 negative)
- 10 item untuk `participation_inequity` (5 positive, 5 negative)

#### REQ-GSD-03: Input Format per Intervention Type

**off_topic items:**
```json
{
  "input": {
    "group_id": "group_test_XX",
    "course_topic": "Topik mata kuliah (misal: Pemrograman Web)",
    "recent_messages": ["pesan1", "pesan2", "pesan3"],
    "message_count": 3
  }
}
```

**silence items:**
```json
{
  "input": {
    "group_id": "group_test_XX",
    "last_message_seconds_ago": 650,
    "silence_threshold_seconds": 600
  }
}
```

**participation_inequity items:**
```json
{
  "input": {
    "group_id": "group_test_XX",
    "message_counts_per_user": {"user_A": 15, "user_B": 2, "user_C": 1}
  }
}
```

#### REQ-GSD-04: Kualitas Label

- Setiap item harus memiliki `labeling_rationale` yang menjelaskan alasan label
- Label harus konsisten dengan definisi intervention type di `logic_listener.py`
- Dataset harus merepresentasikan variasi skenario: diskusi akademik, diskusi off-track, grup aktif, grup pasif

#### REQ-GSD-05: Aksesibilitas

- File JSON harus valid dan bisa di-load dengan `json.load()`
- Path relatif dari root project: `data/evaluation/logic_listener_gold_standard.json`
- File harus di-commit ke repository sebagai artefak penelitian
