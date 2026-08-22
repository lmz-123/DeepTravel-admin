## Purpose

为 DeepTravel 运营者提供一个受保护、可实时跟随且可检索的统一运行日志入口，用于关联后端容器输出与 Flutter 客户端故障，同时限制敏感信息暴露和日志资源消耗。

## ADDED Requirements

### Requirement: Authorized operator can open the runtime log console
The management application SHALL expose a dedicated runtime-log workspace only after the configured management credential has been validated. All backend-log query and stream operations SHALL require that same authorization and SHALL reject missing or invalid credentials without returning log content.

#### Scenario: Authorized operator opens logs
- **WHEN** an operator with a valid management credential opens the runtime-log workspace
- **THEN** the application shows the available backend and client log sources and begins loading the selected source

#### Scenario: Unauthorized log access is rejected
- **WHEN** a request without a valid management credential asks for historical or streaming logs
- **THEN** the service returns an authorization error and no log content

### Requirement: Backend container logs stream in near real time
The system SHALL stream recent and newly emitted lines from configured backend container aliases, include a server timestamp and source alias for every event, and SHALL NOT accept an arbitrary container identifier from a browser request.

#### Scenario: Follow an allowed backend source
- **WHEN** an authorized operator selects a configured backend source
- **THEN** the console first shows a bounded recent tail and then appends new lines without requiring a page refresh

#### Scenario: Unknown backend source is requested
- **WHEN** a request selects a source alias that is not in the server configuration
- **THEN** the service rejects the request without querying the container runtime

#### Scenario: Container source becomes unavailable
- **WHEN** the selected container stops, restarts, or cannot be reached
- **THEN** the stream emits a non-secret source-status event and the console offers or performs bounded reconnection without freezing the rest of the admin application

### Requirement: Flutter clients can submit structured runtime logs
The system SHALL provide a client-log ingestion endpoint protected by a dedicated ingestion credential distinct from the management credential. The endpoint SHALL accept bounded batches containing timestamp, severity, message, category, session identifier, application version, platform, and optional structured context, and SHALL return a stable success or validation response.

#### Scenario: Valid client log batch is accepted
- **WHEN** a client sends a valid batch with the configured ingestion credential
- **THEN** the service persists each accepted event and acknowledges the batch without exposing the management credential

#### Scenario: Invalid or oversized batch is rejected
- **WHEN** a client sends malformed entries, too many entries, an overlong field, or an invalid ingestion credential
- **THEN** the service rejects the request with a bounded error response and does not partially persist the batch

#### Scenario: Client is temporarily offline
- **WHEN** the client cannot reach the ingestion endpoint
- **THEN** the ingestion protocol permits a later batch to retain original event timestamps and session context without requiring strict contiguous sequence numbers

### Requirement: Client logs are retained and streamed predictably
The system SHALL persist accepted client events in the shared relational database, SHALL expose a bounded historical query, and SHALL stream newly accepted records to authorized operators. It SHALL enforce configurable age and row-count retention so client logging cannot grow without limit.

#### Scenario: Operator follows client logs
- **WHEN** an authorized operator selects client logs
- **THEN** the console loads a bounded recent history and appends newly accepted events in ascending event order

#### Scenario: Stream reconnects with a cursor
- **WHEN** a client-log stream disconnects after delivering an event cursor
- **THEN** the operator can reconnect from that cursor without intentionally duplicating already acknowledged events

#### Scenario: Retention limit is exceeded
- **WHEN** accepted records exceed the configured maximum age or row count
- **THEN** expired records are removed in bounded maintenance work while newer records remain queryable

### Requirement: Log content is normalized and redacted on the server
Before storage or delivery, the service SHALL cap line and field sizes, normalize severity values, and redact configured sensitive patterns including authorization values, passwords, tokens, cookies, and database credentials. Raw unredacted client payloads SHALL NOT be persisted.

#### Scenario: Sensitive value appears in a log
- **WHEN** a backend line or client event contains a recognized secret-bearing field or credential pattern
- **THEN** every API response and persisted client record replaces the sensitive value with a redaction marker

#### Scenario: Very long message arrives
- **WHEN** a backend line or client message exceeds the configured event-size limit
- **THEN** the service truncates it deterministically and marks the event as truncated

### Requirement: Operator can control and filter the live view
The console SHALL support backend/client source selection, severity filtering, keyword filtering, pause/resume, automatic scrolling, manual view clearing, and a visible connection state. Pausing or clearing the browser view SHALL NOT delete persisted records or stop server-side collection.

#### Scenario: Operator pauses the view
- **WHEN** the operator pauses a connected stream
- **THEN** the visible list stops moving while the interface indicates that incoming events are buffered or awaiting resume

#### Scenario: Operator filters logs
- **WHEN** the operator selects one or more severity levels or enters a keyword
- **THEN** the visible rows update to matching events while preserving the current source and connection state

#### Scenario: Operator clears the view
- **WHEN** the operator clears the current view
- **THEN** displayed rows are removed locally and a later refresh can still retrieve retained server records

### Requirement: Log streaming has bounded resource usage
The service SHALL bound historical tail size, in-memory per-connection buffering, heartbeat interval, concurrent streams, and reconnect cadence. Slow or disconnected consumers SHALL be dropped or resumed by cursor rather than causing unbounded memory growth.

#### Scenario: Browser consumer cannot keep up
- **WHEN** a log consumer remains slower than the configured stream buffer
- **THEN** the service closes or advances the connection with an explicit status instead of accumulating unlimited events

#### Scenario: No events are emitted
- **WHEN** a stream has no new log events during the heartbeat interval
- **THEN** the service sends a lightweight heartbeat so intermediaries and the console can detect liveness
