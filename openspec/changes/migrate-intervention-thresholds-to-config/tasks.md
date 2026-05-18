## 1. Discovery

- [x] 1.1 Cari semua referensi `OFF_TOPIC_THRESHOLD`, `INACTIVITY_THRESHOLD_MINUTES`, `MINIMUM_MESSAGES_FOR_SUMMARY` di luar `app/services/intervention.py` — ditemukan di `tests/test_unit/test_intervention_and_goals.py:682-684`. Test diupdate ke instance attribute lower-case.

## 2. Config

- [x] 2.1 Tambah section `# Intervention Thresholds` di `app/core/config.py:152-160` dengan 8 setting baru: `INTERVENTION_OFF_TOPIC_THRESHOLD=0.6`, `INTERVENTION_INACTIVITY_THRESHOLD_MINUTES=30`, `INTERVENTION_MINIMUM_MESSAGES_FOR_SUMMARY=10`, `INTERVENTION_PROMPT_TEMPERATURE=0.8`, `INTERVENTION_CONFIDENCE_OFF_TOPIC=0.5`, `INTERVENTION_CONFIDENCE_INACTIVITY=0.8`, `INTERVENTION_CONFIDENCE_SUMMARIZE=0.7`, `INTERVENTION_CONFIDENCE_PROMPT=0.6`.

## 3. Service refactor

- [x] 3.1 Update `ChatInterventionService.__init__` agar membaca semua threshold dari `settings.*` ke instance attributes lower-case.
- [x] 3.2 Hapus class constants `OFF_TOPIC_THRESHOLD`, `INACTIVITY_THRESHOLD_MINUTES`, `MINIMUM_MESSAGES_FOR_SUMMARY`.
- [x] 3.3 Ganti inline literal `temperature=0.8` menjadi `temperature=self.prompt_temperature`.
- [x] 3.4 Ganti inline confidence literal di `_select_intervention` (`0.5`/`0.8`/`0.7`/`0.6`) menjadi `self.confidence_*`.
- [x] 3.5 Update `self.INACTIVITY_THRESHOLD_MINUTES` (1 occurrence) dan `self.MINIMUM_MESSAGES_FOR_SUMMARY` (4 occurrences) ke instance attribute lower-case via ast-grep.

## 4. Verifikasi

- [x] 4.1 `pytest tests/test_unit/test_intervention_and_goals.py -v` → 139 passed.
- [x] 4.2 `python3 -m py_compile app/services/intervention.py app/core/config.py` exit 0.
- [x] 4.3 `openspec validate migrate-intervention-thresholds-to-config --strict` → valid.
