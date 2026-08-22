## Context

See `proposal.md` for motivation. The independent admin repository contains a React/vinext web app and a FastAPI admin service. The FastAPI service already authenticates content-management APIs with a bearer management token and connects directly to the same MySQL database as DeepTravel. Production is started with Docker Compose; the DeepTravel API currently writes operational output to container stdout/stderr. The Flutter application has no structured remote logger today.

The feature therefore has two different source shapes: ephemeral ordered text from a container runtime and durable structured events submitted by mobile devices. Treating both as one storage pipeline would either require changing the main API logging system or duplicate every backend line in MySQL. The implementation instead normalizes both into one delivery DTO while retaining source-specific adapters.

## Goals / Non-Goals

**Goals:**

- Provide a genuinely live operator experience with bounded recent history and reconnect behavior.
- Keep container access server-side, source-allowlisted, read-only at the application level, and inaccessible to the browser.
- Persist only client events that need cross-session diagnosis; avoid using browser storage as an authoritative log store.
- Keep log collection separable from existing content CRUD code and compatible with the current single admin deployment.
- Define a stable ingestion contract that the DeepTravel Flutter client can adopt without sharing the admin credential.

**Non-Goals:**

- Replace a production observability stack such as Loki, OpenSearch, Sentry, or OpenTelemetry.
- Provide Docker shell access, container lifecycle controls, arbitrary file browsing, or unrestricted Docker API proxying.
- Guarantee delivery of every mobile debug line while a device is offline or the process is terminated.
- Persist all backend stdout in MySQL.
- Make the admin page publicly accessible or expose log streams without authentication.

## Decisions

### 1. Use source adapters behind one normalized event contract

Add a `server/runtime_logs/` package with `LogEvent`, redaction/normalization utilities, a Docker backend source, and a MySQL client-log source. Both adapters emit a DTO containing `cursor`, `occurred_at`, `received_at`, `source_type`, `source`, `level`, `category`, `message`, `context`, and `truncated`.

This keeps API and UI behavior consistent while preserving the right storage model for each source. A single generic repository was rejected because Docker follow streams and indexed database queries have materially different lifecycle and failure behavior.

### 2. Follow allowlisted containers through the Docker Engine API

The admin service receives an environment mapping such as `travel-api=deeptravel-api-1,admin-api=deeptravel-admin-admin-api-1`. Browser requests reference only aliases. The adapter resolves the configured target and uses the Docker logs API with a bounded `tail`, timestamps, and follow mode. No generic Docker route, exec call, container mutation, or user-supplied container identifier is exposed.

The Docker Unix socket is mounted into `admin-api` only for deployments that enable backend streaming. This is operationally simple and works with current stdout logging. Reading Docker JSON files directly was rejected because paths and formats vary by logging driver. Requiring the main API to write a shared file was rejected because it couples two Compose projects and changes the existing backend logging contract.

The socket remains a high-value capability even when mounted read-only, so the code surface using it is deliberately narrow and the admin service must not be treated as a low-trust workload.

### 3. Use authenticated HTTP streaming parsed from `fetch`

Expose an authenticated stream endpoint that returns Server-Sent Event framing, but consume it with `fetch` and a stream parser instead of the browser `EventSource` constructor. This retains the existing bearer header and avoids putting the management token in a query string, URL history, proxy log, or referrer.

Each stream begins with metadata, sends normalized events and periodic heartbeats, and ends with a structured source-status event on recoverable source failure. Client-log cursors are database IDs. Backend cursors are connection-local timestamp/sequence values, so reconnect uses a fresh bounded tail rather than claiming exactly-once delivery.

WebSockets were rejected because the console is server-to-browser only and SSE framing is easier to inspect and proxy. Interval polling was rejected for backend follow because it adds latency and repeatedly retrieves overlapping tails.

### 4. Persist client logs in the existing MySQL service

Add a `client_runtime_logs` table with an auto-increment cursor, client event timestamp, receive timestamp, normalized level/category/message, session/app/platform metadata, optional JSON context, and truncation flag. Index receive time, event time, severity, session ID, and category. The admin service creates only this owned table idempotently during startup, rather than calling `Base.metadata.create_all()` for the borrowed content schema.

Ingestion uses a separate `CLIENT_LOG_INGEST_TOKEN`, batch transaction, strict Pydantic limits, and request-size cap. Retention is enforced by bounded deletion after successful ingestion and on service startup: delete records older than configured days, then trim oldest excess rows above the configured maximum. This avoids a scheduler dependency for the MVP.

D1/browser persistence was rejected because the deployed admin API already shares MySQL with the product and client logs must remain visible to the independently hosted UI through that API.

### 5. Redact before persistence and before delivery

Central normalization caps fields, maps arbitrary levels to `debug/info/warning/error/critical`, removes control characters, and applies case-insensitive redaction to secret-bearing key/value patterns, bearer/basic authorization, cookies, common token query parameters, and database URLs. Structured context is traversed with depth/key/count limits and sensitive keys are replaced wholesale.

Client records are normalized before insert. Docker lines are normalized immediately after read and before being put on a per-connection queue. The browser performs no security-critical redaction. Operators can still intentionally log personal data that no pattern recognizes, so production logging guidance must avoid names, phone numbers, exact location histories, and photo content.

### 6. Use a bounded client-side stream model

Add a `logs` tab to the existing navigation and a focused `LogsView` component. It keeps at most the configured UI row count, uses `AbortController` for source changes/unmount, parses incremental SSE frames, and implements exponential reconnect with a ceiling. Pause stops rendering/auto-scroll but keeps only a bounded pending buffer; overflow is represented by a skipped-count notice.

Filters are applied locally to the bounded current set for immediate interaction. Historical retrieval can accept source, level, keyword, session, before/after cursor and limit parameters, allowing a future server-side search UI without changing the event contract.

### 7. Keep Flutter integration as an explicit companion

The ingestion contract is delivered by this repository, but real client events require a companion change in the DeepTravel repository. That client integration will capture framework errors, unhandled async errors, API failures, location/audio state failures, and selected lifecycle breadcrumbs; batch only non-sensitive structured summaries; retain a small disk queue; and use build-time `CLIENT_LOG_URL` and `CLIENT_LOG_INGEST_TOKEN` values.

The management repository cannot honestly claim current APK telemetry without that companion change. Backend-log viewing remains functional independently.

## Risks / Trade-offs

- [Docker socket grants broad daemon capability to a compromised admin API] → Keep the admin service private, retain bearer authorization, expose no Docker proxy primitives, validate aliases against static configuration, run no user-authored code, and document that a dedicated log collector should replace the socket for higher-security environments.
- [A container name changes after Compose redeployment] → Make aliases configurable and show an actionable unavailable-source state; document `docker compose ps --format json` as the deployment check.
- [Long-lived HTTP streams are buffered or timed out by a reverse proxy] → Send heartbeats, disable proxy buffering in deployment guidance, use reconnect cursors for client logs, and display connection state.
- [Client logs contain personal or credential data] → Redact server-side, constrain context, avoid raw request/response bodies and precise location payloads in the client contract, and enforce short configurable retention.
- [MySQL maintenance work affects content requests] → Use indexed bounded deletes, conservative defaults, and perform cleanup after ingestion rather than on every read.
- [Multiple admin API replicas duplicate backend stream work] → Each operator connection follows its own source in the MVP; document this cost and keep concurrency/tail limits configurable.
- [Current Flutter app does not submit logs] → Track and ship the companion DeepTravel change before declaring client log collection operational.

## Migration Plan

1. Deploy the database model and admin API with backend streaming disabled by default; startup creates only `client_runtime_logs` idempotently.
2. Configure client ingestion token, retention limits, allowed log sources, and CORS independently from the management token.
3. Mount the Docker socket and enable configured aliases on the Linux server; verify health and a bounded backend tail before exposing the UI tab.
4. Deploy the admin web build and verify authorization, filtering, pause, reconnect, and redaction with synthetic logs.
5. Ship the companion Flutter logger with the ingestion URL/token and verify one synthetic client event appears with the expected session/app metadata.
6. Roll back by removing the UI/API deployment and socket mount. The additive client-log table can remain safely; it can be dropped later after retention/export review.

## Open Questions

- The exact production Compose container names will be supplied through environment configuration at deployment and do not change the alias-based contract.
