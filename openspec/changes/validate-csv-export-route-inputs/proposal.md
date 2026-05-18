# Validate CSV Export Route Inputs

## Problem Statement

CSV export endpoints di `analytics.py` interpolate path parameters langsung ke filename `Content-Disposition` header:

```python
# analytics.py:112
filename = f"student_breakdown_{group_id}_{datetime.now().strftime('%Y%m%d_%H')}.csv"
return Response(
    content=csv_data,
    media_type="text/csv",
    headers={"Content-Disposition": f"attachment; filename={filename}"},
)
```

Risk:
- **Header injection / response splitting** — kalau `group_id` mengandung CRLF (`\r\n`), bisa inject HTTP headers
- **Filename smuggling** — kalau `group_id` mengandung quote/backslash/path separator, filename tidak escape

Endpoint affected:
- `/export/activity/group/{group_id}`
- `/export/activity/chat-space/{chat_space_id}`
- `/export/group/{group_id}/csv`
- `/export/individual/{user_id}/csv`
- + 2 endpoint lain di analytics.py

Defense-in-depth: walaupun core-api gateway validate, ai-engine tetap harus protect.

## Proposed Solution

1. Add path parameter validation menggunakan FastAPI `Path` dengan regex constraint:
   ```python
   group_id: str = Path(..., regex=r"^[a-zA-Z0-9_-]+$")
   ```
2. Sanitize `filename` dengan `urllib.parse.quote` atau strip non-safe chars
3. Use RFC 6266 compliant `Content-Disposition` format

## Scope

- `app/api/routes/analytics.py` — semua CSV export endpoints (6+)
- Pydantic validators atau Path constraints
- Optional: helper function `safe_filename(...)` di `app/api/utils.py`

## Out of Scope

- Authentication/authorization (handled di core-api gateway)
- CSV content sanitization (formula injection — separate concern)
