# Off-Topic Detection via AI Guardrail - Implementation Tasks

## Overview
This document outlines the implementation tasks for enabling off-topic detection through the AI Guardrail system.

## Current Status
- **Proposal**: ✅ Complete
- **Design**: ✅ Complete
- **Specifications**: ✅ Complete
- **Tasks**: ✅ Complete (this document)
- **Implementation**: ⏸️ Not started (awaiting decision)

---

## Phase 1: Core API Layer (Kolabri-core-api)

### Task 1.1: Extend Validation Schema
**File:** `src/validators/course.validator.ts`

**Actions:**
1. Add `ai_guardrail_enable_off_topic: z.boolean().optional()`
2. Add `ai_guardrail_off_topic_threshold: z.number().min(0.3).max(0.9).optional()`
3. Add custom error messages for threshold validation

**Acceptance Criteria:**
- [ ] Schema accepts valid threshold values (0.3-0.9)
- [ ] Schema rejects invalid threshold values
- [ ] Both fields are optional
- [ ] Existing validation tests still pass

**Estimated Time:** 15 minutes

---

### Task 1.2: Extend Course Service
**File:** `src/services/course.service.ts`

**Actions:**
1. Update `updateCourse()` method to handle new guardrail fields
2. Add logic to merge new fields with existing `aiGuardrailConfig`
3. Ensure default values are applied when fields are missing

**Code Snippet:**
```typescript
// Inside updateCourse() method
if (data.ai_guardrail_enable_off_topic !== undefined) {
  updateData.aiGuardrailConfig = {
    ...existingConfig,
    enableOffTopicCheck: data.ai_guardrail_enable_off_topic,
    offTopicThreshold: data.ai_guardrail_off_topic_threshold ?? existingConfig?.offTopicThreshold ?? 0.6,
  };
}
```

**Acceptance Criteria:**
- [ ] Can update only off-topic fields without affecting other guardrail settings
- [ ] Default values applied when fields not provided
- [ ] Existing guardrail config preserved when updating off-topic fields
- [ ] All existing tests pass

**Estimated Time:** 30 minutes

---

### Task 1.3: Add Unit Tests for Course Service
**File:** `src/services/course.service.test.ts`

**Actions:**
1. Test enabling off-topic check
2. Test updating threshold
3. Test partial updates (only off-topic fields)
4. Test default values
5. Test preservation of existing config

**Test Cases:**
```typescript
describe('CourseService.updateCourse - Off-topic detection', () => {
  it('should enable off-topic check', async () => {
    // Test implementation
  });
  
  it('should update threshold', async () => {
    // Test implementation
  });
  
  it('should apply default threshold when not provided', async () => {
    // Test implementation
  });
  
  it('should preserve existing guardrail config', async () => {
    // Test implementation
  });
});
```

**Acceptance Criteria:**
- [ ] All test cases pass
- [ ] Coverage for new code > 80%
- [ ] Edge cases covered (null values, missing fields)

**Estimated Time:** 45 minutes

---

### Task 1.4: Extend Socket Layer
**File:** `src/socket/index.ts`

**Actions:**
1. Extract off-topic fields from `courseRecord.aiGuardrailConfig`
2. Add to `guardrailPolicy` object
3. Apply default values when fields not present

**Code Snippet (around line 1108):**
```typescript
const guardrailPolicy = {
  preset: courseRecord?.aiGuardrailConfig?.preset ?? 'balanced',
  allow_rewrite: courseRecord?.aiGuardrailConfig?.allowRewrite ?? true,
  allow_flag_only: courseRecord?.aiGuardrailConfig?.allowFlagOnly ?? false,
  
  // NEW: Off-topic detection fields
  enable_off_topic_check: courseRecord?.aiGuardrailConfig?.enableOffTopicCheck ?? false,
  off_topic_threshold: courseRecord?.aiGuardrailConfig?.offTopicThreshold ?? 0.6,
};
```

**Acceptance Criteria:**
- [ ] Fields correctly extracted from config
- [ ] Defaults applied when fields missing
- [ ] Socket tests pass

**Estimated Time:** 20 minutes

---

### Task 1.5: Extend AI Engine Service Types
**File:** `src/services/aiEngine.service.ts`

**Actions:**
1. Update `GuardrailPolicy` interface to include new fields
2. Ensure TypeScript type safety

**Code Snippet:**
```typescript
interface GuardrailPolicy {
  preset: 'strict' | 'balanced' | 'relaxed';
  allow_rewrite: boolean;
  allow_flag_only: boolean;
  
  // NEW
  enable_off_topic_check: boolean;
  off_topic_threshold: number;
}
```

**Acceptance Criteria:**
- [ ] TypeScript compilation succeeds
- [ ] Type definitions match actual usage

**Estimated Time:** 10 minutes

---

## Phase 2: AI Engine Layer (Kolabri-ai-engine)

### Task 2.1: Extend Orchestration Service
**File:** `app/services/orchestration.py`

**Actions:**
1. Add off-topic check logic after orchestration
2. Extract `enable_off_topic_check` from `guardrail_policy`
3. Call `logic_listener.check_relevance()` when enabled
4. Override orchestration result when off-topic detected
5. Log intervention to MongoDB

**Code Snippet:**
```python
# After orchestration, check for off-topic
guardrail_policy = kwargs.get('guardrail_policy', {})

if guardrail_policy.get('enable_off_topic_check'):
    topic = kwargs.get('topic')
    if topic:
        relevance_result = await self.logic_listener.check_relevance(
            message=message,
            group_id=group_id,
            threshold=guardrail_policy.get('off_topic_threshold', 0.6)
        )
        
        if relevance_result.should_intervene:
            # Override orchestration result
            result.intervention = relevance_result.suggested_message
            result.intervention_type = 'off_topic_strict'
            result.quality_score = 0.0
            
            # Log intervention
            await self.mongo_logger.log_intervention(
                group_id=group_id,
                intervention_type='off_topic_strict',
                message=relevance_result.suggested_message,
                metadata={
                    'similarity_score': relevance_result.similarity_score,
                    'threshold': guardrail_policy.get('off_topic_threshold'),
                    'consecutive_off_topic': relevance_result.consecutive_count
                }
            )
```

**Acceptance Criteria:**
- [ ] Off-topic check only runs when enabled
- [ ] Logic listener called correctly
- [ ] Result overridden when off-topic detected
- [ ] Intervention logged to MongoDB
- [ ] Graceful degradation on errors

**Estimated Time:** 1 hour

---

### Task 2.2: Optimize Logic Listener
**File:** `app/services/logic_listener.py`

**Actions:**
1. Add topic embedding cache (`self.topic_embeddings`)
2. Update `set_group_topic()` to cache embedding
3. Update `check_relevance()` to use cached embedding
4. Reduce embedding calls from 2 to 1 per check

**Code Snippet:**
```python
class LogicListener:
    def __init__(self):
        self.group_topics: Dict[str, str] = {}
        self.topic_embeddings: Dict[str, List[float]] = {}  # NEW: Cache
        self.off_topic_counters: Dict[str, int] = {}
    
    async def set_group_topic(self, group_id: str, topic: str):
        """Set topic and cache embedding."""
        self.group_topics[group_id] = topic
        
        # Cache embedding for this topic
        embedding = await self.embedding_service.get_embedding(topic)
        self.topic_embeddings[group_id] = embedding
    
    async def check_relevance(self, message: str, group_id: str, threshold: float = 0.6):
        """Check relevance using cached topic embedding."""
        topic_embedding = self.topic_embeddings.get(group_id)
        if not topic_embedding:
            return RelevanceResult(should_intervene=False, ...)
        
        # Only need 1 embedding call (for message)
        message_embedding = await self.embedding_service.get_embedding(message)
        
        # Calculate similarity
        similarity_score = cosine_similarity(message_embedding, topic_embedding)
        
        # ... rest of logic
```

**Acceptance Criteria:**
- [ ] Topic embeddings cached
- [ ] Embedding calls reduced from 2 to 1 per check
- [ ] Memory usage reasonable (~1KB per topic)
- [ ] Existing tests pass

**Estimated Time:** 45 minutes

---

### Task 2.3: Add Error Handling
**File:** `app/services/orchestration.py`

**Actions:**
1. Handle case when topic not set
2. Handle case when logic_listener not initialized
3. Handle embedding service errors
4. Log warnings/errors appropriately

**Code Snippet:**
```python
try:
    if guardrail_policy.get('enable_off_topic_check'):
        topic = kwargs.get('topic')
        if not topic:
            logger.warning("off_topic_check_skipped_no_topic", group_id=group_id)
            return result
        
        if not hasattr(self, 'logic_listener'):
            logger.warning("logic_listener_not_initialized")
            return result
        
        # ... check relevance logic
        
except Exception as e:
    logger.error("off_topic_check_failed", error=str(e), group_id=group_id)
    # Graceful degradation: return original result
    return result
```

**Acceptance Criteria:**
- [ ] All edge cases handled
- [ ] Errors logged appropriately
- [ ] Graceful degradation on failures
- [ ] No crashes on errors

**Estimated Time:** 30 minutes

---

### Task 2.4: Add Unit Tests for Orchestration
**File:** `tests/test_orchestration.py`

**Actions:**
1. Test off-topic check disabled (should not call logic_listener)
2. Test off-topic check enabled with topic
3. Test off-topic check enabled without topic (should skip)
4. Test off-topic detection triggers intervention
5. Test intervention overrides orchestration result
6. Test quality_score set to 0.0 on off-topic
7. Test intervention logged to MongoDB

**Test Cases:**
```python
class TestOffTopicDetection:
    @pytest.mark.asyncio
    async def test_off_topic_check_disabled(self):
        """Should not call logic_listener when disabled."""
        # Test implementation
    
    @pytest.mark.asyncio
    async def test_off_topic_check_enabled(self):
        """Should call logic_listener when enabled."""
        # Test implementation
    
    @pytest.mark.asyncio
    async def test_off_topic_intervention_override(self):
        """Should override orchestration result on off-topic."""
        # Test implementation
    
    @pytest.mark.asyncio
    async def test_quality_score_zero_on_off_topic(self):
        """Should set quality_score to 0.0 on off-topic."""
        # Test implementation
    
    @pytest.mark.asyncio
    async def test_no_topic_skips_check(self):
        """Should skip check when no topic provided."""
        # Test implementation
```

**Acceptance Criteria:**
- [ ] All test cases pass
- [ ] Coverage for new code > 80%
- [ ] Mocks used for logic_listener and mongodb_logger

**Estimated Time:** 1 hour

---

### Task 2.5: Add Unit Tests for Logic Listener
**File:** `tests/test_logic_listener.py`

**Actions:**
1. Test topic embedding caching
2. Test relevance check with cached embedding
3. Test consecutive off-topic counter
4. Test intervention trigger after 3 consecutive off-topic messages
5. Test similarity score calculation

**Acceptance Criteria:**
- [ ] All test cases pass
- [ ] Caching mechanism verified
- [ ] Consecutive counter logic tested

**Estimated Time:** 45 minutes

---

## Phase 3: Integration Testing

### Task 3.1: Write Integration Test Script
**File:** `scripts/test_off_topic_integration.py`

**Actions:**
1. Create test script that simulates full flow
2. Mock MongoDB, embedding service, and orchestration
3. Test end-to-end: API → Socket → AI Engine → Logic Listener

**Test Scenario:**
```python
async def test_off_topic_flow():
    # 1. Lecturer enables off-topic check
    await update_course_settings(
        course_id='course-1',
        enable_off_topic_check=True,
        off_topic_threshold=0.6
    )
    
    # 2. Simulate student message
    result = await send_message(
        group_id='group-1',
        message='Apa kabar semua?',  # Off-topic
        topic='Machine Learning Algorithms'
    )
    
    # 3. Verify intervention
    assert result.intervention_type == 'off_topic_strict'
    assert 'stay on topic' in result.intervention.lower()
    assert result.quality_score == 0.0
```

**Acceptance Criteria:**
- [ ] Full flow tested
- [ ] All components integrated correctly
- [ ] No errors in logs

**Estimated Time:** 1 hour

---

### Task 3.2: Test on VPS (Development Environment)
**Actions:**
1. Sync code to VPS: `rsync -avz Kolabri-ai-engine/app/services/ vpsgw:/opt/kolabri/Kolabri-ai-engine/app/services/`
2. Rebuild ai-engine container: `docker compose build ai-engine`
3. Restart container: `docker compose up -d ai-engine`
4. Test via API endpoint
5. Verify MongoDB logs
6. Check container health

**Acceptance Criteria:**
- [ ] Code synced successfully
- [ ] Container rebuilt and healthy
- [ ] API endpoint works
- [ ] Off-topic detection triggers correctly
- [ ] MongoDB logs contain intervention

**Estimated Time:** 1 hour

---

## Phase 4: Frontend Integration (Optional - Future)

### Task 4.1: Extend Course Settings UI
**File:** `Kolabri-client-app/resources/js/pages/lecturer/courses/settings.vue`

**Actions:**
1. Add checkbox for "Enable off-topic detection"
2. Add slider for "Similarity threshold" (0.3-0.9)
3. Add help text explaining the feature
4. Update form submission to include new fields

**UI Mockup:**
```vue
<div class="form-group">
  <label>
    <input type="checkbox" v-model="form.ai_guardrail_enable_off_topic" />
    Enable off-topic detection
  </label>
  <p class="help-text">
    Automatically detect when students go off-topic during discussions
  </p>
</div>

<div class="form-group" v-if="form.ai_guardrail_enable_off_topic">
  <label>Similarity threshold: {{ form.ai_guardrail_off_topic_threshold }}</label>
  <input 
    type="range" 
    min="0.3" 
    max="0.9" 
    step="0.1"
    v-model="form.ai_guardrail_off_topic_threshold" 
  />
  <p class="help-text">
    Lower values (0.3) = more strict, Higher values (0.9) = more lenient
  </p>
</div>
```

**Acceptance Criteria:**
- [ ] UI displays new fields
- [ ] Form validation works
- [ ] API call includes new fields
- [ ] Settings persist after save

**Estimated Time:** 2 hours

---

### Task 4.2: Add Lecturer Documentation
**File:** `Kolabri-client-app/resources/docs/lecturer-guide.md`

**Actions:**
1. Explain off-topic detection feature
2. Provide threshold tuning guidelines
3. Add examples of on-topic vs off-topic messages
4. Explain intervention behavior

**Acceptance Criteria:**
- [ ] Documentation clear and concise
- [ ] Examples provided
- [ ] Guidelines for threshold tuning

**Estimated Time:** 30 minutes

---

## Phase 5: Deployment & Monitoring

### Task 5.1: Prepare Deployment Checklist
**File:** `openspec/changes/off-topic-detection-via-guardrail/deployment-checklist.md`

**Actions:**
1. Create deployment checklist
2. Include rollback procedures
3. List monitoring metrics
4. Define success criteria

**Checklist Template:**
```markdown
## Pre-Deployment
- [ ] All tests pass (unit + integration)
- [ ] Code reviewed
- [ ] Documentation updated
- [ ] Backup database

## Deployment
- [ ] Sync code to VPS
- [ ] Rebuild ai-engine container
- [ ] Verify container health
- [ ] Test API endpoint
- [ ] Check MongoDB logs

## Post-Deployment
- [ ] Monitor error rates
- [ ] Check intervention frequency
- [ ] Verify no performance degradation
- [ ] Collect user feedback
```

**Estimated Time:** 30 minutes

---

### Task 5.2: Define Monitoring Metrics
**Actions:**
1. Define metrics to track
2. Set up logging queries
3. Define alert thresholds

**Metrics:**
- Number of courses with off-topic detection enabled
- Number of off-topic interventions per day
- Average similarity score of interventions
- False positive rate (requires feedback mechanism)
- Performance impact (latency, embedding service load)

**Estimated Time:** 1 hour

---

### Task 5.3: Plan Rollback Procedure
**Actions:**
1. Document rollback steps
2. Test rollback on development
3. Prepare emergency disable script

**Rollback Steps:**
1. Disable feature via database:
   ```sql
   UPDATE courses 
   SET ai_guardrail_config = ai_guardrail_config - 'enableOffTopicCheck' - 'offTopicThreshold'
   WHERE ai_guardrail_config ? 'enableOffTopicCheck';
   ```
2. Revert code changes (if needed)
3. Rebuild containers
4. Verify system stability

**Estimated Time:** 30 minutes

---

## Phase 6: Future Enhancements

### Task 6.1: Plan Real-time UI Feedback
**Description:** Show off-topic indicator in lecturer dashboard in real-time

**Estimated Time:** 4 hours

---

### Task 6.2: Plan Group-level Override
**Description:** Allow per-group threshold customization

**Estimated Time:** 3 hours

---

### Task 6.3: Plan Analytics & Insights
**Description:** Track off-topic frequency, identify patterns, suggest topic improvements

**Estimated Time:** 6 hours

---

### Task 6.4: Plan Smart Topic Detection
**Description:** Auto-extract topic from course materials, dynamic topic updates

**Estimated Time:** 8 hours

---

## Dependencies

### External Dependencies
- **Embedding Service:** Already implemented, no changes needed
- **MongoDB Logger:** Already implemented, no changes needed
- **Logic Listener:** Already implemented, only optimization needed

### Internal Dependencies
- **Course API:** Must be updated first (Phase 1)
- **Socket Layer:** Depends on Course API (Phase 1)
- **AI Engine:** Depends on Socket Layer (Phase 2)

---

## Acceptance Criteria (Overall)

### Functional Requirements
- [ ] Lecturer can enable/disable off-topic check via API
- [ ] Lecturer can configure threshold (0.3-0.9)
- [ ] Off-topic detection triggers when enabled
- [ ] Intervention message appears when students off-topic
- [ ] Intervention overrides orchestration result
- [ ] Quality score set to 0.0 on off-topic
- [ ] Intervention logged to MongoDB

### Non-Functional Requirements
- [ ] Backward compatible (default behavior unchanged)
- [ ] All existing tests pass
- [ ] New tests cover >80% of new code
- [ ] Performance impact <100ms per message
- [ ] No additional database queries required
- [ ] Graceful degradation on errors

### User Experience
- [ ] Clear intervention messages
- [ ] Threshold tuning guidelines provided
- [ ] Feature discoverable in course settings
- [ ] Help text explains feature clearly

---

## Timeline Summary

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| Phase 1: Core API | 5 tasks | 2 hours |
| Phase 2: AI Engine | 5 tasks | 4 hours |
| Phase 3: Integration | 2 tasks | 2 hours |
| Phase 4: Frontend (Optional) | 2 tasks | 2.5 hours |
| Phase 5: Deployment | 3 tasks | 2 hours |
| **Total** | **17 tasks** | **12.5 hours** |

---

## Risk Mitigation

### High-Risk Tasks
1. **Task 2.1: Extend Orchestration Service**
   - Risk: Breaking existing orchestration flow
   - Mitigation: Comprehensive testing, graceful degradation

2. **Task 2.2: Optimize Logic Listener**
   - Risk: Memory issues with caching
   - Mitigation: Monitor memory usage, limit cache size

3. **Task 3.2: Test on VPS**
   - Risk: Container build failures
   - Mitigation: Test on development first, have rollback plan

### Rollback Plan
1. Disable feature via database (no code changes needed)
2. Revert code if necessary
3. Rebuild containers
4. Verify system stability

---

## Conclusion

This implementation plan provides a structured approach to enabling off-topic detection via AI Guardrail. The feature is:

- **Well-defined:** Clear specifications and acceptance criteria
- **Testable:** Comprehensive test coverage planned
- **Safe:** Backward compatible with rollback procedures
- **Performant:** Optimized with caching and minimal overhead
- **User-friendly:** Clear UI and documentation planned

**Next Steps:**
1. Review this task list
2. Prioritize phases (Phase 1-3 required, Phase 4-5 optional)
3. Begin implementation when ready
4. Monitor and iterate based on user feedback

---

## References

- [Proposal](./proposal.md)
- [Design Document](./design.md)
- [Specifications](./specs.md)
- [Deployment Checklist](./deployment-checklist.md)
