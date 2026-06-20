# Off-Topic Detection via AI Guardrail

## Status
Proposed

## Overview
Mengaktifkan fitur `logic_listener.check_relevance()` yang saat ini merupakan dead code dengan mengintegrasikannya ke dalam sistem AI Guardrail Preset yang sudah ada.

## Motivation

### Problem
- `logic_listener.check_relevance()` sudah diimplementasikan tapi tidak pernah dipanggil (dead code)
- Fitur ini bisa mendeteksi off-topic discussion secara real-time
- Tidak ada mekanisme untuk mencegah mahasiswa ngobrol di luar topik diskusi

### Opportunity
- AI Guardrail Preset sudah ada dan terintegrasi (database, API, socket, ai-engine)
- Tinggal extend existing JSON field `aiGuardrailConfig`
- Lecturer sudah familiar dengan guardrail settings
- No schema migration needed

## Proposed Solution

### Integration Strategy: Extend AI Guardrail Config
Tambah 2 fields baru ke `aiGuardrailConfig` JSON:
- `enableOffTopicCheck: boolean` (default: false)
- `offTopicThreshold: number` (default: 0.6)

### Why This Approach
✅ **Explicit Control** - Lecturer tahu persis apa yang di-enable  
✅ **Backward Compatible** - Default disabled, tidak ganggu existing courses  
✅ **Flexible** - Bisa fine-tune threshold per course  
✅ **Clean Architecture** - Extend existing flow, tidak perlu fitur baru  
✅ **Testable** - Easy to unit test  
✅ **User-Friendly** - Tinggal tambah UI toggle  

## Scope

### In Scope
- Extend validation schema di `course.validator.ts`
- Update service layer di `course.service.ts`
- Update socket layer di `socket/index.ts`
- Wire up `logic_listener.check_relevance()` di `orchestration.py`
- Unit tests untuk semua layers
- UI form di lecturer dashboard (optional)

### Out of Scope
- Database schema migration (JSON field flexible)
- New API endpoints (extend existing PATCH /api/courses/:id)
- Real-time UI feedback (future enhancement)
- Group-level override (course-level only untuk now)

## Success Criteria
- [ ] Lecturer bisa enable/disable off-topic check via course settings
- [ ] Off-topic detection aktif ketika enabled
- [ ] Intervention message muncul saat mahasiswa off-topic
- [ ] Backward compatible (default behavior tidak berubah)
- [ ] Semua existing tests masih pass
- [ ] New tests cover off-topic detection flow

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| False positives (message relevan tapi similarity rendah) | Medium | High | Tunable threshold (0.3-0.9), default conservative (0.6) |
| Performance impact (embedding calls) | Low | Medium | Reuse existing embedding service, cache topic embeddings |
| Lecturer confusion (tidak paham threshold) | Medium | Low | UI help text, sensible defaults |
| Conflict dengan orchestration intervention | Low | Medium | Clear priority: off-topic override orchestration |

## Alternatives Considered

### Alternative 1: Tie to Preset Only
```typescript
if (preset === 'strict') {
  enableOffTopicCheck = true  // Auto-enable
}
```
**Rejected because:** Less flexible, magic behavior, lecturer tidak tahu strict = off-topic check

### Alternative 2: Separate Feature
Buat feature baru "Discussion Focus Mode" terpisah dari guardrail
**Rejected because:** Duplicate infrastructure, more complex, inconsistent UX

### Alternative 3: Hybrid (Preset + Manual Override)
Preset-based dengan manual override option
**Rejected because:** More complex logic, marginal benefit over Option 1

## Timeline Estimate
- Phase 1 (Core Implementation): 2-3 hours
- Phase 2 (Testing & Verification): 1-2 hours
- Phase 3 (UI Implementation): 1 hour (optional)
- **Total: 4-6 hours**

## Dependencies
- `logic_listener.check_relevance()` - Already implemented
- AI Guardrail system - Already implemented
- Embedding service - Already implemented
- Course settings API - Already implemented

## Related Documents
- [Design Document](./design.md)
- [Specifications](./specs.md)
- [Implementation Tasks](./tasks.md)
