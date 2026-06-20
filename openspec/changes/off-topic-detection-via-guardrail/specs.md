# Off-Topic Detection via AI Guardrail - Specifications

## Technical Specifications

### 1. Validation Schema (course.validator.ts)

#### Location
`Kolabri-core-api/src/validators/course.validator.ts`

#### Changes
Extend `updateCourseSchema` dengan 2 optional fields:

```typescript
// Existing schema
export const updateCourseSchema = z.object({
  code: z.string().min(1).max(10).optional(),
  name: z.string().min(1).max(100).optional(),
  description: z.string().max(500).optional(),
  
  // Existing guardrail fields
  ai_guardrail_preset: z.enum(['strict', 'balanced', 'relaxed']).optional(),
  ai_guardrail_allow_rewrite: z.boolean().optional(),
  ai_guardrail_allow_flag_only: z.boolean().optional(),
  
  // NEW: Off-topic detection fields
  ai_guardrail_enable_off_topic: z.boolean().optional(),
  ai_guardrail_off_topic_threshold: z.number()
    .min(0.3, 'Threshold terlalu rendah, minimal 0.3')
    .max(0.9, 'Threshold terlalu tinggi, maksimal 0.9')
    .optional(),
  
  // Other existing fields...
});
```

#### Validation Rules
- `ai_guardrail_enable_off_topic`: Optional boolean
- `ai_guardrail_off_topic_threshold`: Optional number, range [0.3, 0.9]
- Both fields independent (can enable without setting threshold, uses default)

#### Error Messages
```typescript
{
  'ai_guardrail_off_topic_threshold.too_small': 'Threshold terlalu rendah, minimal 0.3',
  'ai_guardrail_off_topic_threshold.too_big': 'Threshold terlalu tinggi, maksimal 0.9',
  'ai_guardrail_off_topic_threshold.invalid_type': 'Threshold harus berupa angka',
}
```

---

### 2. Service Layer (course.service.ts)

#### Location
`Kolabri-core-api/src/services/course.service.ts`

#### Method: `updateCourse()`

#### Current Signature
```typescript
static async updateCourse(
  courseId: string, 
  userId: string, 
  data: UpdateCourseInput
): Promise<Course>
```

#### Changes
Extend guardrail config update logic:

```typescript
// Check if any guardrail fields are being updated
if (data.ai_guardrail_preset !== undefined || 
    data.ai_guardrail_allow_rewrite !== undefined ||
    data.ai_guardrail_allow_flag_only !== undefined ||
    data.ai_guardrail_enable_off_topic !== undefined ||      // NEW
    data.ai_guardrail_off_topic_threshold !== undefined) {   // NEW
  
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
```

#### Behavior
- **Partial Updates:** Can update only off-topic fields without touching other guardrail fields
- **Preservation:** Existing guardrail config preserved when not updated
- **Defaults:**
  - `enableOffTopicCheck`: false (disabled by default)
  - `offTopicThreshold`: 0.6 (conservative threshold)

#### Example Usage
```typescript
// Enable off-topic check only
await CourseService.updateCourse('course-1', 'lecturer-1', {
  ai_guardrail_enable_off_topic: true
});

// Update threshold only
await CourseService.updateCourse('course-1', 'lecturer-1', {
  ai_guardrail_off_topic_threshold: 0.7
});

// Update both
await CourseService.updateCourse('course-1', 'lecturer-1', {
  ai_guardrail_enable_off_topic: true,
  ai_guardrail_off_topic_threshold: 0.7
});
```

---

### 3. Socket Layer (socket/index.ts)

#### Location
`Kolabri-core-api/src/socket/index.ts`

#### Function: Extract guardrail policy

#### Current Code (Line ~1108)
```typescript
const guardrailPolicy = {
  preset: courseRecord?.aiGuardrailConfig?.preset ?? 'balanced',
  allow_rewrite: courseRecord?.aiGuardrailConfig?.allowRewrite ?? true,
  allow_flag_only: courseRecord?.aiGuardrailConfig?.allowFlagOnly ?? false,
};
```

#### Changes
Add off-topic detection fields:

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

#### Behavior
- Extract from `courseRecord.aiGuardrailConfig` (already loaded)
- Apply defaults if fields not present
- Send to ai-engine via `sendMessage()` call

#### Type Definition
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

---

### 4. AI Engine Service (aiEngine.service.ts)

#### Location
`Kolabri-core-api/src/services/aiEngine.service.ts`

#### Interface: `SendMessageParams`

#### Changes
Extend interface to include new guardrail fields:

```typescript
interface SendMessageParams {
  message: string;
  chat_room_id: string;
  guardrail_policy: {
    preset: 'strict' | 'balanced' | 'relaxed';
    allow_rewrite: boolean;
    allow_flag_only: boolean;
    
    // NEW
    enable_off_topic_check: boolean;
    off_topic_threshold: number;
  };
  // ... other fields
}
```

#### Behavior
- No logic changes in this service
- Just pass guardrail_policy to ai-engine HTTP call

---

### 5. AI Engine Orchestration (orchestration.py)

#### Location
`Kolabri-ai-engine/app/services/orchestration.py`

#### Method: `handle_message()`

#### Current Flow
```python
async def handle_message(self, user_id, group_id, message, **kwargs):
    # Step 1: Orchestrate
    result = await self.orchestrate(...)
    
    # Step 2: Return result
    return result
```

#### Changes
Add off-topic check after orchestration:

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

#### Behavior
- **Conditional Execution:** Only check if `enable_off_topic_check` is True
- **Topic Required:** Skip check if no topic available
- **Override Priority:** Off-topic intervention overrides orchestration intervention
- **Quality Score:** Set to 0.0 when off-topic detected
- **Logging:** Log intervention to MongoDB for analytics

#### Edge Cases
1. **No Topic:** Skip check, return orchestration result unchanged
2. **Logic Listener Not Initialized:** Skip check, log warning
3. **Embedding Service Error:** Skip check, log error, return orchestration result

---

### 6. Logic Listener (logic_listener.py)

#### Location
`Kolabri-ai-engine/app/services/logic_listener.py`

#### Status
**No changes needed** - `check_relevance()` already implemented

#### Method Signature (Existing)
```python
async def check_relevance(
    self, 
    message: str, 
    group_id: str, 
    threshold: float = 0.6
) -> RelevanceResult:
    """Check if message is relevant to group topic."""
```

#### Return Type (Existing)
```python
@dataclass
class RelevanceResult:
    should_intervene: bool
    similarity_score: float
    consecutive_count: int
    suggested_message: str | None
```

#### Optimization Opportunity
Cache topic embeddings to reduce embedding calls:

```python
class LogicListener:
    def __init__(self):
        self.group_topics: Dict[str, str] = {}
        self.topic_embeddings: Dict[str, List[float]] = {}  # NEW: Cache
        self.off_topic_counters: Dict[str, int] = {}
    
    async def set_group_topic(self, group_id: str, topic: str):
        """Set topic and cache embedding."""
        self.group_topics[group_id] = topic
        
        # Cache embedding for this topic (optimization)
        embedding = await self.embedding_service.get_embedding(topic)
        self.topic_embeddings[group_id] = embedding
    
    async def check_relevance(self, message: str, group_id: str, threshold: float = 0.6):
        """Check relevance using cached topic embedding."""
        topic_embedding = self.topic_embeddings.get(group_id)
        if not topic_embedding:
            # No topic set, skip check
            return RelevanceResult(
                should_intervene=False,
                similarity_score=0.0,
                consecutive_count=0,
                suggested_message=None
            )
        
        # Only need 1 embedding call (for message)
        message_embedding = await self.embedding_service.get_embedding(message)
        
        # Calculate similarity
        similarity_score = cosine_similarity(message_embedding, topic_embedding)
        
        # Track consecutive off-topic messages
        is_off_topic = similarity_score < threshold
        self._update_off_topic_counter(group_id, is_off_topic)
        
        # Intervene if 3+ consecutive off-topic messages
        consecutive_count = self.off_topic_counters.get(group_id, 0)
        should_intervene = consecutive_count >= 3
        
        if should_intervene:
            topic = self.group_topics.get(group_id, 'the discussion topic')
            suggested_message = f"Please stay on topic: {topic}"
        else:
            suggested_message = None
        
        return RelevanceResult(
            should_intervene=should_intervene,
            similarity_score=similarity_score,
            consecutive_count=consecutive_count,
            suggested_message=suggested_message
        )
```

#### Performance Improvement
- **Before:** 2 embedding calls per check (message + topic)
- **After:** 1 embedding call per check (message only, topic cached)
- **Memory:** ~1KB per cached embedding (384 dimensions × 4 bytes)

---

### 7. MongoDB Logger (mongodb_logger.py)

#### Location
`Kolabri-ai-engine/app/services/mongodb_logger.py`

#### Method: `log_intervention()`

#### Status
**No changes needed** - already supports `intervention_type='off_topic_strict'`

#### Signature (Existing)
```python
async def log_intervention(
    self,
    group_id: str,
    intervention_type: str,
    message: str,
    metadata: Dict[str, Any]
):
    """Log intervention to MongoDB."""
```

#### Usage in Orchestration
```python
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

---

### 8. Response Schema (orchestration.py)

#### Location
`Kolabri-ai-engine/app/models/orchestration.py`

#### Class: `OrchestrationResult`

#### Status
**No changes needed** - already has required fields

#### Schema (Existing)
```python
@dataclass
class OrchestrationResult:
    intervention: str | None
    intervention_type: str | None
    quality_score: float | None
    # ... other fields
```

#### Off-Topic Values
When off-topic detected:
```python
result.intervention = 'Please stay on topic: Machine Learning'
result.intervention_type = 'off_topic_strict'
result.quality_score = 0.0
```

---

## API Specification

### Endpoint: Update Course Settings

**PATCH** `/api/courses/:id`

#### Request Headers
```
Authorization: Bearer <token>
Content-Type: application/json
```

#### Request Body
```json
{
  "ai_guardrail_enable_off_topic": true,
  "ai_guardrail_off_topic_threshold": 0.6
}
```

#### Response (Success - 200)
```json
{
  "data": {
    "id": "course-1",
    "code": "IF101",
    "name": "Introduction to Programming",
    "ai_guardrail_config": {
      "preset": "balanced",
      "allowRewrite": true,
      "allowFlagOnly": false,
      "enableOffTopicCheck": true,
      "offTopicThreshold": 0.6
    }
  }
}
```

#### Response (Validation Error - 400)
```json
{
  "error": {
    "message": "Validation failed",
    "details": [
      {
        "field": "ai_guardrail_off_topic_threshold",
        "message": "Threshold terlalu rendah, minimal 0.3"
      }
    ]
  }
}
```

#### Response (Authorization Error - 403)
```json
{
  "error": {
    "message": "Only course owner can update settings"
  }
}
```

#### Response (Not Found - 404)
```json
{
  "error": {
    "message": "Course not found"
  }
}
```

---

## Database Schema

### Table: `courses`

#### Field: `ai_guardrail_config` (JSON)

```json
{
  "preset": "strict" | "balanced" | "relaxed",
  "allowRewrite": boolean,
  "allowFlagOnly": boolean,
  
  // NEW fields
  "enableOffTopicCheck": boolean,
  "offTopicThreshold": number  // 0.3 - 0.9
}
```

#### Default Values
```json
{
  "preset": "balanced",
  "allowRewrite": true,
  "allowFlagOnly": false,
  "enableOffTopicCheck": false,
  "offTopicThreshold": 0.6
}
```

#### Prisma Schema
```prisma
model Course {
  id                    String   @id @default(uuid())
  code                  String   @unique
  name                  String
  ai_guardrail_config   Json?    // Extended with new fields
  // ... other fields
}
```

#### No Migration Needed
- Field type is `Json` (flexible schema)
- Can add/remove fields without migration
- Backward compatible (old code ignores new fields)

---

## Configuration

### Environment Variables
No new environment variables needed. All config stored in database.

### Default Values
```python
# orchestration.py
DEFAULT_ENABLE_OFF_TOPIC_CHECK = False
DEFAULT_OFF_TOPIC_THRESHOLD = 0.6
DEFAULT_CONSECUTIVE_THRESHOLD = 3  # Intervene after 3 consecutive off-topic messages
```

### Tuning Parameters
- **off_topic_threshold:** 0.3 (very strict) to 0.9 (very lenient)
  - Recommended: 0.6 (balanced)
  - Lower = more interventions (strict)
  - Higher = fewer interventions (lenient)
  
- **consecutive_threshold:** Hardcoded to 3 in `logic_listener.py`
  - Intervene only after 3 consecutive off-topic messages
  - Prevents false positives from single messages

---

## Error Handling

### 1. Validation Errors (API Layer)
```typescript
// course.validator.ts
if (threshold < 0.3 || threshold > 0.9) {
  throw new ValidationError('Threshold must be between 0.3 and 0.9');
}
```

### 2. Topic Not Set (Orchestration Layer)
```python
# orchestration.py
if not topic:
    # Skip off-topic check, return orchestration result unchanged
    return result
```

### 3. Embedding Service Error (Logic Listener Layer)
```python
# logic_listener.py
try:
    embedding = await self.embedding_service.get_embedding(message)
except EmbeddingServiceError as e:
    logger.error(f"Embedding service error: {e}")
    # Return no intervention (graceful degradation)
    return RelevanceResult(should_intervene=False, ...)
```

### 4. Logic Listener Not Initialized
```python
# orchestration.py
if not hasattr(self, 'logic_listener'):
    logger.warning("Logic listener not initialized, skipping off-topic check")
    return result
```

---

## Logging

### Log Levels
- **INFO:** Off-topic check enabled/disabled
- **INFO:** Off-topic intervention triggered
- **WARNING:** Logic listener not initialized
- **ERROR:** Embedding service failure

### Log Format
```python
# orchestration.py
logger.info(
    "off_topic_check_enabled",
    course_id=course_id,
    group_id=group_id,
    threshold=guardrail_policy.get('off_topic_threshold')
)

logger.info(
    "off_topic_intervention_triggered",
    group_id=group_id,
    similarity_score=relevance_result.similarity_score,
    consecutive_count=relevance_result.consecutive_count
)
```

### MongoDB Logs
Off-topic interventions logged to `interventions` collection:
```json
{
  "group_id": "group-1",
  "intervention_type": "off_topic_strict",
  "message": "Please stay on topic: Machine Learning",
  "metadata": {
    "similarity_score": 0.3,
    "threshold": 0.6,
    "consecutive_off_topic": 3
  },
  "created_at": "2026-01-20T10:00:00Z"
}
```

---

## Monitoring

### Metrics to Track
1. **Off-topic check enabled count:** Number of courses with feature enabled
2. **Off-topic interventions per day:** Track intervention frequency
3. **Average similarity score:** Understand threshold effectiveness
4. **False positive rate:** (Requires lecturer feedback mechanism)

### Alerts
- **High intervention rate:** >10 interventions per group per session (may indicate threshold too strict)
- **Embedding service errors:** >5% error rate (service degradation)

### Dashboards
- Course settings: Show off-topic check status
- Intervention analytics: Breakdown by type (off_topic_strict vs other)
- Similarity score distribution: Help lecturers tune threshold

---

## Security

### Input Validation
- **Threshold:** Validated at API layer (0.3-0.9)
- **Boolean fields:** Validated by Zod schema
- **SQL Injection:** Prevented by Prisma ORM

### Access Control
- **Authorization:** Only course owner can update guardrail settings
- **Existing checks:** Leverage existing course ownership validation
- **No privilege escalation:** Students cannot modify course settings

### Data Privacy
- **Embeddings:** Stored in memory only (not persisted)
- **Messages:** Already logged to MongoDB (no additional privacy impact)
- **Topic:** Course metadata (not sensitive)

---

## Backward Compatibility

### Database
- ✅ No schema migration required
- ✅ Old code ignores new JSON fields
- ✅ Default values applied when fields missing

### API
- ✅ New fields are optional
- ✅ Existing API clients unaffected
- ✅ Validation only applies when fields provided

### Socket Layer
- ✅ Defaults applied if fields not in config
- ✅ Old ai-engine versions ignore new fields

### AI Engine
- ✅ Conditional execution (only if enabled)
- ✅ Graceful degradation (skip check on errors)
- ✅ Old orchestration code path preserved

### Rollback Plan
1. **Disable via database:** Remove new fields from all courses
2. **Code rollback:** Revert service/socket/orchestration changes
3. **No data loss:** Feature is optional, no existing functionality affected
