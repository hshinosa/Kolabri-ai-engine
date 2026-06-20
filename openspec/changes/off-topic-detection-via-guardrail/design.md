# Off-Topic Detection via AI Guardrail - Design Document

## Technical Architecture

### System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Lecturer Dashboard (UI)                                          │
│ - Toggle: Enable off-topic detection                            │
│ - Slider: Similarity threshold (0.3-0.9)                        │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ Course API (PATCH /api/courses/:id)                              │
│ - Validate: ai_guardrail_enable_off_topic (boolean)            │
│ - Validate: ai_guardrail_off_topic_threshold (0.3-0.9)         │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ Database (PostgreSQL)                                            │
│ course.ai_guardrail_config: {                                    │
│   preset: 'strict',                                              │
│   allowRewrite: true,                                            │
│   allowFlagOnly: false,                                          │
│   enableOffTopicCheck: true,          ← NEW                      │
│   offTopicThreshold: 0.6              ← NEW                      │
│ }                                                                │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ Socket Layer (socket/index.ts)                                   │
│ - Load course config per message                                 │
│ - Extract guardrail_policy with new fields                       │
│ - Send to ai-engine                                              │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ AI Engine (orchestration.py)                                     │
│ 1. Normal orchestration flow (RAG, guardrails, etc.)            │
│ 2. Check if enable_off_topic_check == True                      │
│ 3. If yes:                                                      │
│    - Set topic: logic_listener.set_group_topic(group_id, topic)│
│    - Check relevance: logic_listener.check_relevance(message)   │
│ 4. If off-topic detected:                                       │
│    - Override intervention message                              │
│    - Set intervention_type = 'off_topic_strict'                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ Logic Listener (logic_listener.py)                               │
│ - Calculate embedding similarity (message vs topic)             │
│ - Track consecutive off-topic messages                          │
│ - Trigger intervention if threshold exceeded                    │
└─────────────────────────────────────────────────────────────────┘
```

## Data Model Changes

### Database Schema
No migration needed - `ai_guardrail_config` is already `Json` type (flexible)

```prisma
model Course {
  id                   String   @id @default(uuid())
  code                 String   @unique
  name                 String
  description          String?
  ai_guardrail_config  Json?    // Extended with new fields
  ai_scaffolding_config Json?
  // ... other fields
}
```

### TypeScript Types

```typescript
// core-api/src/types/course.types.ts
interface AIGuardrailConfig {
  preset: 'strict' | 'balanced' | 'relaxed';
  allowRewrite: boolean;
  allowFlagOnly: boolean;
  
  // NEW fields
  enableOffTopicCheck?: boolean;
  offTopicThreshold?: number;
}

interface Course {
  id: string;
  code: string;
  name: string;
  aiGuardrailConfig?: AIGuardrailConfig;
  // ... other fields
}
```

### Python Types

```python
# ai-engine/app/models/guardrail.py
from pydantic import BaseModel
from typing import Literal, Optional

class GuardrailPolicy(BaseModel):
    preset: Literal['strict', 'balanced', 'relaxed'] = 'balanced'
    allow_rewrite: bool = True
    allow_flag_only: bool = False
    
    # NEW fields
    enable_off_topic_check: bool = False
    off_topic_threshold: float = 0.6
```

## API Changes

### Existing Endpoint (Extended)

**PATCH /api/courses/:id**

```typescript
// Request body (new fields)
{
  ai_guardrail_enable_off_topic: boolean,
  ai_guardrail_off_topic_threshold: number  // 0.3 - 0.9
}

// Response (existing structure, extended data)
{
  id: string,
  ai_guardrail_config: {
    preset: 'strict',
    allowRewrite: true,
    allowFlagOnly: false,
    enableOffTopicCheck: true,        // NEW
    offTopicThreshold: 0.6            // NEW
  }
}
```

### Validation Rules

```typescript
// course.validator.ts
const updateCourseSchema = z.object({
  // ... existing fields
  
  ai_guardrail_enable_off_topic: z.boolean().optional(),
  ai_guardrail_off_topic_threshold: z.number()
    .min(0.3, 'Threshold terlalu rendah')
    .max(0.9, 'Threshold terlalu tinggi')
    .optional(),
});
```

## Core Implementation

### 1. Service Layer (course.service.ts)

```typescript
static async updateCourse(courseId: string, userId: string, data: UpdateCourseInput) {
  const updateData: any = {};
  
  // Check if any guardrail fields are being updated
  if (data.ai_guardrail_preset !== undefined || 
      data.ai_guardrail_allow_rewrite !== undefined ||
      data.ai_guardrail_allow_flag_only !== undefined ||
      data.ai_guardrail_enable_off_topic !== undefined ||
      data.ai_guardrail_off_topic_threshold !== undefined) {
    
    const currentPolicy = course.aiGuardrailConfig ?? {};
    
    updateData.aiGuardrailConfig = {
      preset: data.ai_guardrail_preset ?? currentPolicy.preset ?? 'balanced',
      allowRewrite: data.ai_guardrail_allow_rewrite ?? currentPolicy.allowRewrite ?? true,
      allowFlagOnly: data.ai_guardrail_allow_flag_only ?? currentPolicy.allowFlagOnly ?? false,
      
      // NEW: Off-topic detection fields
      enableOffTopicCheck: data.ai_guardrail_enable_off_topic 
        ?? currentPolicy.enableOffTopicCheck ?? false,
      offTopicThreshold: data.ai_guardrail_off_topic_threshold 
        ?? currentPolicy.offTopicThreshold ?? 0.6,
    };
  }
  
  return prisma.course.update({
    where: { id: courseId },
    data: updateData
  });
}
```

### 2. Socket Layer (socket/index.ts)

```typescript
// Line ~1108: Extract guardrail policy
const guardrailPolicy = {
  preset: courseRecord?.aiGuardrailConfig?.preset ?? 'balanced',
  allow_rewrite: courseRecord?.aiGuardrailConfig?.allowRewrite ?? true,
  allow_flag_only: courseRecord?.aiGuardrailConfig?.allowFlagOnly ?? false,
  
  // NEW: Off-topic detection fields
  enable_off_topic_check: courseRecord?.aiGuardrailConfig?.enableOffTopicCheck ?? false,
  off_topic_threshold: courseRecord?.aiGuardrailConfig?.offTopicThreshold ?? 0.6,
};

// Send to ai-engine (existing flow)
const result = await aiEngineService.sendMessage({
  message: msg,
  chat_room_id: chatSpaceId,
  guardrail_policy: guardrailPolicy,  // Includes new fields
  // ... other params
});
```

### 3. AI Engine (orchestration.py)

```python
async def handle_message(self, user_id, group_id, message, topic=None, **kwargs):
    """Main message handler with orchestration flow."""
    
    # Step 1: Normal orchestration (RAG, guardrails, etc.)
    result = await self.orchestrate(user_id, group_id, message, **kwargs)
    
    # Step 2: Off-topic check (if enabled in guardrail policy)
    guardrail_policy = kwargs.get('guardrail_policy', {})
    
    if guardrail_policy.get('enable_off_topic_check'):
        # Set topic for logic_listener (if available)
        if topic:
            await self.logic_listener.set_group_topic(group_id, topic)
        
        # Check message relevance
        relevance_result = await self.logic_listener.check_relevance(
            message=message,
            group_id=group_id,
            threshold=guardrail_policy.get('off_topic_threshold', 0.6)
        )
        
        # If off-topic detected, override orchestration result
        if relevance_result.should_intervene:
            result.intervention = relevance_result.suggested_message
            result.intervention_type = 'off_topic_strict'
            result.quality_score = 0.0  # Off-topic = zero quality
            
            # Log the off-topic detection
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
    
    return result
```

### 4. Logic Listener (logic_listener.py)

Already implemented - no changes needed. Just need to wire it up in orchestration.

```python
async def check_relevance(self, message: str, group_id: str, threshold: float = 0.6):
    """Check if message is relevant to group topic."""
    # Get topic for this group
    topic = self.group_topics.get(group_id)
    if not topic:
        return RelevanceResult(should_intervene=False)
    
    # Calculate embedding similarity
    similarity_score = await self.embedding_service.calculate_similarity(
        text1=message,
        text2=topic
    )
    
    # Track consecutive off-topic messages
    is_off_topic = similarity_score < threshold
    self._update_off_topic_counter(group_id, is_off_topic)
    
    # Intervene if 3+ consecutive off-topic messages
    consecutive_count = self.off_topic_counters.get(group_id, 0)
    should_intervene = consecutive_count >= 3
    
    if should_intervene:
        suggested_message = self._generate_off_topic_intervention(topic)
    else:
        suggested_message = None
    
    return RelevanceResult(
        should_intervene=should_intervene,
        similarity_score=similarity_score,
        consecutive_count=consecutive_count,
        suggested_message=suggested_message
    )
```

## Testing Strategy

### Unit Tests

#### 1. Validator Tests
```typescript
describe('updateCourseSchema - off-topic fields', () => {
  it('accepts valid enable_off_topic_check', () => {
    const result = updateCourseSchema.safeParse({
      ai_guardrail_enable_off_topic: true,
    });
    expect(result.success).toBe(true);
  });
  
  it('accepts valid threshold (0.3-0.9)', () => {
    const result = updateCourseSchema.safeParse({
      ai_guardrail_off_topic_threshold: 0.6,
    });
    expect(result.success).toBe(true);
  });
  
  it('rejects threshold below 0.3', () => {
    const result = updateCourseSchema.safeParse({
      ai_guardrail_off_topic_threshold: 0.2,
    });
    expect(result.success).toBe(false);
  });
  
  it('rejects threshold above 0.9', () => {
    const result = updateCourseSchema.safeParse({
      ai_guardrail_off_topic_threshold: 0.95,
    });
    expect(result.success).toBe(false);
  });
});
```

#### 2. Service Tests
```typescript
describe('CourseService.updateCourse - off-topic fields', () => {
  it('saves enable_off_topic_check to ai_guardrail_config', async () => {
    await CourseService.updateCourse('course-1', 'lecturer-1', {
      ai_guardrail_enable_off_topic: true,
    });
    
    expect(prisma.course.update).toHaveBeenCalledWith({
      where: { id: 'course-1' },
      data: {
        ai_guardrail_config: expect.objectContaining({
          enableOffTopicCheck: true,
        }),
      },
    });
  });
  
  it('preserves existing guardrail config when updating off-topic fields', async () => {
    prismaMock.course.findFirst.mockResolvedValue({
      ai_guardrail_config: {
        preset: 'strict',
        allowRewrite: true,
        allowFlagOnly: false,
      },
    });
    
    await CourseService.updateCourse('course-1', 'lecturer-1', {
      ai_guardrail_enable_off_topic: true,
      ai_guardrail_off_topic_threshold: 0.7,
    });
    
    expect(prisma.course.update).toHaveBeenCalledWith({
      data: {
        ai_guardrail_config: {
          preset: 'strict',
          allowRewrite: true,
          allowFlagOnly: false,
          enableOffTopicCheck: true,
          offTopicThreshold: 0.7,
        },
      },
    });
  });
});
```

#### 3. Socket Tests
```typescript
describe('Socket - off-topic policy extraction', () => {
  it('extracts enable_off_topic_check from course config', () => {
    const courseRecord = {
      aiGuardrailConfig: {
        enableOffTopicCheck: true,
        offTopicThreshold: 0.7,
      },
    };
    
    const policy = extractGuardrailPolicy(courseRecord);
    
    expect(policy.enable_off_topic_check).toBe(true);
    expect(policy.off_topic_threshold).toBe(0.7);
  });
  
  it('defaults to false when not configured', () => {
    const courseRecord = {
      aiGuardrailConfig: null,
    };
    
    const policy = extractGuardrailPolicy(courseRecord);
    
    expect(policy.enable_off_topic_check).toBe(false);
    expect(policy.off_topic_threshold).toBe(0.6);
  });
});
```

#### 4. AI Engine Tests
```python
# tests/test_off_topic_detection.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_off_topic_check_disabled():
    """Should skip off-topic check when disabled."""
    orchestrator = Orchestrator()
    orchestrator.orchestrate = AsyncMock(return_value=MockResult())
    orchestrator.logic_listener.check_relevance = AsyncMock()
    
    await orchestrator.handle_message(
        user_id='user-1',
        group_id='group-1',
        message='Hello',
        guardrail_policy={'enable_off_topic_check': False}
    )
    
    # Should not call check_relevance
    orchestrator.logic_listener.check_relevance.assert_not_called()

@pytest.mark.asyncio
async def test_off_topic_check_enabled():
    """Should check relevance when enabled."""
    orchestrator = Orchestrator()
    orchestrator.orchestrate = AsyncMock(return_value=MockResult())
    orchestrator.logic_listener.set_group_topic = AsyncMock()
    orchestrator.logic_listener.check_relevance = AsyncMock(
        return_value=RelevanceResult(should_intervene=False)
    )
    
    await orchestrator.handle_message(
        user_id='user-1',
        group_id='group-1',
        message='Hello',
        topic='Machine Learning',
        guardrail_policy={
            'enable_off_topic_check': True,
            'off_topic_threshold': 0.6
        }
    )
    
    # Should call check_relevance
    orchestrator.logic_listener.check_relevance.assert_called_once()

@pytest.mark.asyncio
async def test_off_topic_override_intervention():
    """Should override orchestration result when off-topic detected."""
    orchestrator = Orchestrator()
    orchestrator.orchestrate = AsyncMock(return_value=MockResult(
        intervention='Original intervention',
        intervention_type='other_type'
    ))
    
    # Mock off-topic detection
    orchestrator.logic_listener.check_relevance = AsyncMock(
        return_value=RelevanceResult(
            should_intervene=True,
            similarity_score=0.3,
            consecutive_count=3,
            suggested_message='Please stay on topic'
        )
    )
    
    result = await orchestrator.handle_message(
        user_id='user-1',
        group_id='group-1',
        message='Random off-topic message',
        guardrail_policy={
            'enable_off_topic_check': True,
            'off_topic_threshold': 0.6
        }
    )
    
    # Should override with off-topic intervention
    assert result.intervention == 'Please stay on topic'
    assert result.intervention_type == 'off_topic_strict'
    assert result.quality_score == 0.0
```

### Integration Tests

```python
# tests/integration/test_off_topic_flow.py
@pytest.mark.asyncio
async def test_full_off_topic_detection_flow(client, db_session):
    """Test complete flow from API to AI engine."""
    
    # 1. Lecturer enables off-topic check
    response = await client.patch(
        '/api/courses/course-1',
        json={
            'ai_guardrail_enable_off_topic': True,
            'ai_guardrail_off_topic_threshold': 0.6
        }
    )
    assert response.status_code == 200
    
    # 2. Verify database update
    course = await db_session.get(Course, 'course-1')
    assert course.ai_guardrail_config['enableOffTopicCheck'] is True
    assert course.ai_guardrail_config['offTopicThreshold'] == 0.6
    
    # 3. Simulate socket message
    # (This would normally happen via WebSocket)
    from socket.index import extract_guardrail_policy
    
    policy = extract_guardrail_policy(course)
    assert policy['enable_off_topic_check'] is True
    assert policy['off_topic_threshold'] == 0.6
    
    # 4. AI engine processes message
    # (Mock the actual message handling)
    result = await handle_test_message(
        group_id='group-1',
        message='Apa kabar semua?',  # Off-topic message
        topic='Machine Learning Algorithms',
        guardrail_policy=policy
    )
    
    # 5. Verify intervention
    assert result.intervention_type == 'off_topic_strict'
    assert 'stay on topic' in result.intervention.lower()
```

## Performance Considerations

### Embedding Service Calls
- **Current:** 1 call per message (for message itself)
- **With off-topic check:** +1 call (for topic embedding)
- **Optimization:** Cache topic embeddings per group (topics rarely change)

```python
# logic_listener.py
class LogicListener:
    def __init__(self):
        self.topic_embeddings: Dict[str, List[float]] = {}
    
    async def set_group_topic(self, group_id: str, topic: str):
        """Set topic and cache embedding."""
        self.group_topics[group_id] = topic
        
        # Cache embedding for this topic
        embedding = await self.embedding_service.get_embedding(topic)
        self.topic_embeddings[group_id] = embedding
    
    async def check_relevance(self, message: str, group_id: str, threshold: float):
        """Check relevance using cached topic embedding."""
        topic_embedding = self.topic_embeddings.get(group_id)
        if not topic_embedding:
            return RelevanceResult(should_intervene=False)
        
        # Only need 1 embedding call (for message)
        message_embedding = await self.embedding_service.get_embedding(message)
        
        # Calculate similarity
        similarity = cosine_similarity(message_embedding, topic_embedding)
        # ... rest of logic
```

### Database Queries
- No additional queries (config loaded once per socket connection)
- JSON field is efficient for small config objects

## Security Considerations

### Input Validation
- Threshold validated at API layer (0.3-0.9)
- Boolean fields validated by Zod schema
- No SQL injection risk (Prisma ORM)

### Access Control
- Only course owner can update guardrail settings
- Existing authorization checks apply
- Students cannot modify course settings

## Rollback Strategy

If issues arise after deployment:

1. **Disable via database:**
   ```sql
   UPDATE courses 
   SET ai_guardrail_config = ai_guardrail_config - 'enableOffTopicCheck' - 'offTopicThreshold'
   WHERE ai_guardrail_config ? 'enableOffTopicCheck';
   ```

2. **Code rollback:**
   - Revert service layer changes
   - Revert socket layer changes
   - Revert orchestration changes
   - Keep validator (harmless if not used)

3. **No data loss:**
   - Feature is optional (default disabled)
   - No schema migration to rollback
   - Existing courses unaffected

## Future Enhancements

### Phase 2: Real-time UI Feedback
- Show off-topic indicator in lecturer dashboard
- Display consecutive off-topic count
- Allow manual reset of off-topic counter

### Phase 3: Group-level Override
- Allow per-group threshold customization
- Different thresholds for different group types
- Inherit from course settings by default

### Phase 4: Analytics & Insights
- Track off-topic frequency per course
- Identify patterns (time of day, topic difficulty)
- Suggest topic improvements to lecturer

### Phase 5: Smart Topic Detection
- Auto-extract topic from course materials
- Dynamic topic updates based on current week
- Multi-topic support (broad courses)
