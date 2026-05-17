## threshold-config

Konsolidasi threshold Logic Listener dari class constants ke `config.py`.

### Requirements

#### REQ-TC-01: Threshold Baru di config.py

Tambahkan ke `app/core/config.py` dalam section baru `# Logic Listener Thresholds`:

```python
# Logic Listener Thresholds
LOGIC_LISTENER_OFF_TOPIC_SIMILARITY_THRESHOLD: float = 0.6
LOGIC_LISTENER_OFF_TOPIC_CONSECUTIVE_THRESHOLD: int = 3
LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD: float = 0.6
```

`SILENCE_THRESHOLD_MINUTES: int = 10` sudah ada — tidak perlu ditambah lagi.

#### REQ-TC-02: Update LogicListener

`app/services/logic_listener.py` harus mengambil threshold dari `settings` saat `__init__`, bukan dari class constants:

```python
def __init__(self, **kwargs):
    self.off_topic_similarity_threshold = settings.LOGIC_LISTENER_OFF_TOPIC_SIMILARITY_THRESHOLD
    self.off_topic_consecutive_threshold = settings.LOGIC_LISTENER_OFF_TOPIC_CONSECUTIVE_THRESHOLD
    self.silence_threshold_minutes = settings.SILENCE_THRESHOLD_MINUTES
    self.participation_inequity_threshold = settings.LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD
```

#### REQ-TC-03: Hapus Duplikasi

Class constants berikut di `LogicListener` harus dihapus setelah dipindah ke config:
- `OFF_TOPIC_SIMILARITY_THRESHOLD = 0.6`
- `OFF_TOPIC_CONSECUTIVE_THRESHOLD = 3`
- `SILENCE_THRESHOLD_MINUTES = 10` (duplikat dengan `settings.SILENCE_THRESHOLD_MINUTES`)
- `PARTICIPATION_INEQUITY_THRESHOLD = 0.6`

#### REQ-TC-04: Nilai Tidak Berubah

Semua nilai threshold harus tetap sama setelah dipindah. Ini bukan tuning, hanya refactor.

#### REQ-TC-05: Test Tidak Rusak

Semua test yang ada untuk Logic Listener harus tetap passing setelah perubahan ini. Update mock/fixture jika ada yang menggunakan class constants secara langsung.
