## Purpose

让 CMS 媒体库按城市和景点解释资源归属与用途，并如实显示本地或 OSS 存储状态，从而支持安全编辑、迁移和生产发布判断。

## ADDED Requirements

### Requirement: Media library is browsable by city and scenic area
The media library SHALL offer a hierarchy of city, scenic area, and referenced resources derived from current content relations. Each resource SHALL list its referencing entity and role; shared and unassigned resources SHALL have explicit groups and MUST NOT be duplicated or falsely attributed.

#### Scenario: Operator opens a city
- **WHEN** the operator expands a city in the media library
- **THEN** its scenic areas show resource counts and can be expanded to images, narration, and other referenced assets with usage labels

#### Scenario: Resource has several references
- **WHEN** one asset is used by multiple stories or scenic areas
- **THEN** each usage is visible while delete protection and identity apply to the one underlying asset

#### Scenario: Resource has no reference
- **WHEN** an uploaded asset is not yet used
- **THEN** it appears in “未归属资源” with no invented city or scenic owner

### Requirement: Provider and canonical reference are visible
Each media row SHALL display a human-readable provider badge, object key or safe path, MIME type, available size/checksum, canonical public URL, and reference count. Upload copy SHALL name the active provider and MUST NOT claim “OSS” while configured for local storage.

#### Scenario: CMS is connected to local development storage
- **WHEN** provider health reports `local`
- **THEN** the upload panel and asset badges say local development storage and no OSS success claim appears

#### Scenario: CMS is connected to OSS
- **WHEN** provider health reports `oss`
- **THEN** uploads and generated narration show OSS object keys and safe public URLs without showing credentials

### Requirement: Production local media is a visible blocker
When connected to a production environment, the CMS SHALL present a prominent blocking warning if either service reports a non-OSS public provider or any sampled published asset resolves through the backend local-asset path. The warning SHALL identify affected counts and provide a migration/recheck action without exposing secrets.

#### Scenario: Production still uses local compatibility URLs
- **WHEN** the provider or published-asset audit finds local media
- **THEN** the media library does not report production storage as ready and links the operator to the dry-run/recheck workflow

#### Scenario: Production audit passes
- **WHEN** both services report matching OSS configuration and published samples resolve through the configured OSS/CDN base
- **THEN** the library shows a successful production-storage status with the audit time and counts
