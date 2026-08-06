## reranker-activation

Verifikasi dan pastikan reranker aktif di environment, tambah observability via health endpoint.

### Requirements

#### REQ-RA-01: Reranker Status di Health Endpoint

Response `/api/health` harus menyertakan field `reranker_enabled: bool` yang mencerminkan status aktual `CrossEncoderReranker.enabled` saat runtime.

#### REQ-RA-02: Config Sudah Benar

`ENABLE_RERANKING: bool = True` di `config.py` harus dipertahankan sebagai default. Tidak ada perubahan nilai.

#### REQ-RA-03: Verifikasi CROSS_ENCODER_AVAILABLE

Tambah log saat startup yang mencatat apakah cross-encoder package tersedia dan reranker aktif:
```
reranker_status: enabled=True, model_loaded=True
```
atau
```
reranker_status: enabled=False, reason="cross_encoder_not_available"
```

#### REQ-RA-04: Dokumentasi di README

Tambah catatan di README bahwa reranker membutuhkan `sentence-transformers` package dan model akan di-download otomatis saat pertama kali digunakan.
