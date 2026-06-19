## ADDED Requirements

### Requirement: Personal-Chat RAG Must Cover All Requested Courses Within Schema Bound

The personal-chat retrieval function (`search_personal_rag`) SHALL search every course collection carried in the request up to the schema-advertised maximum (`PersonalChatRequest.course_ids` `max_length=20`). It MUST NOT silently truncate the scanned set below that bound. Currently the function hard-slices `course_ids[:10]`, so courses beyond the tenth are never retrieved even though the schema permits up to twenty.

#### Scenario: Request carries more than ten courses

- **WHEN** a personal-chat request includes 15 course IDs whose collections contain matching content
- **THEN** retrieval searches all 15 collections (not only the first 10) and may return citations sourced from any of them

#### Scenario: Request at the schema upper bound

- **WHEN** a personal-chat request includes 20 course IDs
- **THEN** retrieval searches all 20 collections without truncation

### Requirement: Personal-Chat RAG Must Behave Identically Across Streaming and Non-Streaming Transports

The streaming and non-streaming personal-chat endpoints SHALL invoke retrieval with the same resolved provider context, so that embedding and retrieval produce identical scoring for an identical query and course set. Currently the streaming endpoint calls `search_personal_rag` without `provider_context` while the non-streaming endpoint passes it; under unified-provider embedding this yields divergent retrieval between transports.

#### Scenario: Same query over both transports yields same retrieval

- **WHEN** the same query and `course_ids` are sent to both `personal_chat` and `personal_chat_stream` with unified-provider embedding enabled
- **THEN** both endpoints resolve the same provider context for retrieval and return the same set of source documents
