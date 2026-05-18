## 1. Pre-flight

- [ ] 1.1 Run baseline: `pytest tests/ -q` — 2009 passing
- [ ] 1.2 List semua CSV export endpoints di `analytics.py`: `grep -n "Content-Disposition\|\.csv" app/api/routes/analytics.py`
- [ ] 1.3 Confirm ID format yang dipakai core-api (UUID? slug? alphanumeric?)

## 2. Create utility function

- [ ] 2.1 Buat `app/api/utils.py` (atau extend yang sudah ada)
- [ ] 2.2 Implement `safe_csv_filename(prefix: str, identifier: str) -> str`
- [ ] 2.3 Define regex constant `SAFE_ID_REGEX = r"^[a-zA-Z0-9_-]{1,64}$"`

## 3. Update endpoints

- [ ] 3.1 `export_group_activity_csv` (L107) — add `Path(..., regex=SAFE_ID_REGEX)` ke `group_id`, use `safe_csv_filename`
- [ ] 3.2 `export_chat_space_activity_csv` (L132) — same untuk `chat_space_id`
- [ ] 3.3 `/export/group/{group_id}/csv` endpoint — same
- [ ] 3.4 `/export/individual/{user_id}/csv` endpoint — same
- [ ] 3.5 Process mining CSV endpoint — same
- [ ] 3.6 Review semua `Response(... Content-Disposition ...)` di analytics.py

## 4. Add tests

- [ ] 4.1 `test_csv_export_rejects_invalid_id` — test 422 untuk `group_id="../etc/passwd"`
- [ ] 4.2 `test_csv_export_rejects_crlf_injection` — test 422 untuk `group_id="abc\r\nX-Inject: bad"`
- [ ] 4.3 `test_csv_export_filename_safe` — verify Content-Disposition tidak contain unescaped quote/CRLF

## 5. Verify

- [ ] 5.1 `pytest tests/ -q` — passing
- [ ] 5.2 Manual curl: `curl -i 'http://localhost:8000/export/activity/group/../../etc'` — should return 422
- [ ] 5.3 `openspec validate validate-csv-export-route-inputs --strict`
