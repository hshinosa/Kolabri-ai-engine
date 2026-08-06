## track-activity-endpoint

Endpoint ringan untuk Core API menotifikasi AI Engine tentang aktivitas grup.

### Requirements

#### REQ-TAE-01: POST /api/track-activity Endpoint

Endpoint menerima:
```json
{ "group_id": "string" }
```
Dan mengembalikan:
```json
{ "success": true }
```

#### REQ-TAE-02: TrackActivityRequest Schema

Tambah ke `app/api/schemas.py`:
```python
class TrackActivityRequest(BaseModel):
    group_id: str
```

#### REQ-TAE-03: Panggil update_last_message_time

Handler memanggil `await logic_listener.update_last_message_time(request.group_id)`. Ini adalah operasi in-memory O(1) — tidak ada LLM, tidak ada DB write.

#### REQ-TAE-04: Dilindungi Auth Middleware

Endpoint menggunakan auth middleware yang sama dengan endpoint lain (X-API-Key header). Tidak ada perubahan pada middleware.

#### REQ-TAE-05: Response Time < 10ms

Karena hanya in-memory dict update, response time harus sangat cepat. Tidak ada operasi I/O.
