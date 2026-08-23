## Purpose

为后台提供多城市 JSON 文件的上传、零写入校验预览和原子草稿导入界面，并确保导入结果继续使用现有编辑器、媒体库和审核发布流程。

## ADDED Requirements

### Requirement: JSON file upload and schema validation
The admin SHALL accept an authorized editor's JSON file for a versioned multi-city package, enforce configured size and entity limits, and report malformed JSON or schema errors with precise paths before offering confirmation.

#### Scenario: Uploaded JSON is malformed
- **WHEN** an editor uploads malformed JSON
- **THEN** the admin shows the parse location and creates no content records

#### Scenario: Package contains embedded media
- **WHEN** an uploaded package contains audio or image binary instead of a permitted media descriptor
- **THEN** the admin rejects the field and explains that managed media references and checksums are required

### Requirement: Zero-write diff preview
The admin SHALL display a complete dry-run summary and record-level details for new, updated, unchanged, conflicted, and invalid content, including missing media and relation errors, before enabling import.

#### Scenario: Preview contains mixed changes
- **WHEN** a valid package contains new, updated, and unchanged records
- **THEN** the preview groups those records and lets the editor inspect stable IDs and field diffs without writing content

#### Scenario: A nested reference is invalid
- **WHEN** a story references a missing point in the uploaded package and database
- **THEN** the preview identifies its city/story record and exact JSON path

### Requirement: Preview-bound confirmation
The admin SHALL enable confirmation only for an unexpired successful dry-run and SHALL submit the server-issued token bound to the editor, package checksum, and target revision snapshot.

#### Scenario: Target changes before confirmation
- **WHEN** another editor changes an affected record after dry-run
- **THEN** confirmation reports a conflict and requires a new preview

### Requirement: Atomic draft import
The admin SHALL confirm the entire package as one transaction, show success counts and stable identifiers, keep all imported content in draft or the applicable pre-publication state, and show record-level failure details when the transaction rolls back.

#### Scenario: Import succeeds
- **WHEN** an editor confirms a valid unchanged preview
- **THEN** all records become available to existing manual editors and none is automatically published

#### Scenario: One write fails
- **WHEN** any record fails during confirmed import
- **THEN** the admin reports the record and reason and no package content change remains committed

### Requirement: Idempotent package handling
The admin SHALL identify package ID, version, and checksum replays and SHALL not offer duplicate creation for the same successfully imported version.

#### Scenario: Same package is uploaded again
- **WHEN** an editor previews the same package ID, version, and checksum after successful import
- **THEN** the preview reports unchanged content rather than duplicate additions

### Requirement: Shared manual and import semantics
The multi-city importer and supported single-route importer SHALL use the same normalization, validation, media-reference, stable-ID, and lifecycle semantics as manual editing.

#### Scenario: Legacy single-route import is used
- **WHEN** an editor imports a supported existing single-route package
- **THEN** the workflow remains compatible and its records can be edited with the same forms as multi-city records
