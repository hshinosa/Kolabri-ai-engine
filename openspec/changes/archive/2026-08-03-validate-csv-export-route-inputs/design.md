# Design

## Validation Strategy

### Path Parameter Constraint

```python
from fastapi import Path

@router.get("/export/activity/group/{group_id}")
async def export_group_activity_csv(
    group_id: str = Path(..., regex=r"^[a-zA-Z0-9_-]{1,64}$"),
):
    ...
```

Regex `^[a-zA-Z0-9_-]{1,64}$` allows:
- Alphanumeric
- Underscore, hyphen
- 1-64 chars (prevent abuse)

Reject by default:
- Path separators (`/`, `\`)
- Quote chars (`"`, `'`)
- CRLF (`\r`, `\n`)
- Whitespace
- Other special chars

### Filename Sanitization

```python
from urllib.parse import quote

def safe_csv_filename(prefix: str, identifier: str) -> str:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_id = quote(identifier, safe='')  # URL-encode all special chars
    return f"{prefix}_{safe_id}_{timestamp}.csv"
```

### RFC 6266 Compliant Content-Disposition

```python
filename = safe_csv_filename("student_breakdown", group_id)
return Response(
    content=csv_data,
    media_type="text/csv",
    headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    },
)
```

Note: RFC 6266 menyarankan `filename*` untuk Unicode, tapi karena kita restrict ke ASCII via regex, plain `filename=` cukup.

## Endpoints to Update

1. `/export/activity/group/{group_id}`
2. `/export/activity/chat-space/{chat_space_id}`
3. `/export/group/{group_id}/csv`
4. `/export/individual/{user_id}/csv`
5. `/export/process-mining/csv` (kalau ada body params)
6. Endpoint lain di analytics.py

## Trade-offs

- **Strict regex** mencegah valid IDs yang punya char selain alphanum/underscore/hyphen. Kalau core-api pakai UUID atau format khusus, regex disesuaikan.
- **Filename URL-encoding** mungkin produce filename yang kurang user-friendly (e.g., `%20` instead of space). Trade-off untuk security.
