# CSV Export Route Input Validation

## ADDED Requirements

### Requirement: Path parameters in CSV export routes MUST be validated

All CSV export endpoints SHALL validate path parameters against a strict regex pattern that excludes path separators, quotes, control characters, and other unsafe characters.

#### Scenario: Reject path traversal in group_id

- Given a request to `/export/activity/group/{group_id}` with `group_id="../etc/passwd"`
- When FastAPI validates the path parameter
- Then the response status MUST be 422
- And the request MUST NOT reach the route handler
- And no CSV file MUST be generated

#### Scenario: Reject CRLF injection in identifiers

- Given a request to a CSV export endpoint with `group_id` containing `\r\n`
- When FastAPI validates the path parameter
- Then the response status MUST be 422
- And no response headers MUST be modified by the malicious input

### Requirement: Filename in Content-Disposition MUST be sanitized

The `filename` value in `Content-Disposition` header SHALL be sanitized to prevent header injection and unsafe filename characters.

#### Scenario: Filename URL-encoding

- Given a CSV export endpoint generates a filename from a path parameter
- When the response is constructed
- Then the filename MUST be URL-encoded (special chars escaped)
- And the `Content-Disposition` value MUST follow `attachment; filename="<safe>"` format
- And no CRLF, quotes, or path separators MUST appear unescaped in the header value
