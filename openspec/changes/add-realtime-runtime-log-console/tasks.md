## 1. Log domain and persistence

- [x] 1.1 Add normalized log event, severity, cursor, source-status, truncation, and bounded structured-context types in a dedicated server log module.
- [x] 1.2 Implement server-side secret redaction, control-character cleanup, size limits, and deterministic normalization with focused unit tests.
- [x] 1.3 Add the owned `client_runtime_logs` SQLAlchemy model, indexes, idempotent startup table creation, and bounded age/row-count retention.

## 2. Client log ingestion

- [x] 2.1 Add strict single-event and batch request schemas covering timestamps, severity, category, message, session, app/platform metadata, and optional context.
- [x] 2.2 Implement the dedicated-token client ingestion endpoint with request/batch limits, transactional all-or-nothing persistence, normalization, and stable validation errors.
- [x] 2.3 Add API tests for valid ingestion, invalid token, malformed/oversized batches, redaction before persistence, and retention behavior.

## 3. Backend container log source

- [x] 3.1 Add configuration parsing for enabled state, Docker socket path, source alias allowlist, tail/line limits, heartbeat, stream concurrency, and reconnect bounds.
- [x] 3.2 Implement the read-only Docker log adapter with timestamp/frame parsing, alias-only target resolution, cancellation, source-status events, and bounded buffering.
- [x] 3.3 Add adapter tests using deterministic Docker stream fixtures for stdout/stderr frames, unavailable containers, cancellation, truncation, and secret redaction.

## 4. Protected history and streaming APIs

- [x] 4.1 Add an authorized source-discovery endpoint that reports configured source aliases and availability without exposing container identifiers or credentials.
- [x] 4.2 Add bounded client-log history queries with source, level, keyword, session, cursor, and limit filters.
- [x] 4.3 Add bearer-authenticated SSE-framed stream endpoints for backend and client sources with initial metadata, event cursors, heartbeats, slow-consumer handling, and structured terminal status.
- [x] 4.4 Add API/stream tests for authorization, unknown aliases, historical ordering, cursor resume, heartbeat framing, disconnect cleanup, and concurrency limits.

## 5. Realtime management interface

- [x] 5.1 Add a “运行日志” navigation destination and load it independently from content catalog requests so log source failure does not break the rest of the admin app.
- [x] 5.2 Implement the authenticated fetch-stream client with incremental SSE parsing, abort-on-source-change/unmount, bounded rows/pending buffer, cursor resume, and capped exponential reconnect.
- [x] 5.3 Build the backend/client source selector, severity and keyword filters, pause/resume, auto-scroll, clear-view, connection indicator, skipped-event notice, timestamps, metadata, and responsive log rows.
- [x] 5.4 Add accessible keyboard/focus behavior and frontend tests for stream parsing, filtering, pause buffering, clear semantics, and reconnect state.

## 6. Deployment and operations

- [x] 6.1 Update server dependencies, Docker Compose, and `.env.example` with the client ingestion token, retention limits, Docker source aliases, socket mount, stream limits, and secure defaults.
- [x] 6.2 Update operator documentation with Linux deployment, container-name discovery, reverse-proxy streaming/timeout settings, health checks, log-source verification, rollback, and Docker socket risk.
- [x] 6.3 Document the Flutter ingestion contract and required companion application settings, explicitly distinguishing “collector ready” from “current APK reporting”.

## 7. Verification and delivery

- [x] 7.1 Run Python unit/API tests, frontend tests, lint, production build, and strict OpenSpec validation; fix all regressions introduced by the change.
- [x] 7.2 Exercise a local end-to-end stream with synthetic backend and client events, confirming redaction, filters, pause/resume, cursor reconnect, and bounded retention.
- [ ] 7.3 Commit the completed change on `main` and push it to the `DeepTravel-admin` origin after verifying no unrelated files are included.
