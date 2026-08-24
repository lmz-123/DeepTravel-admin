## Purpose

让 CMS 媒体库按城市和景点解释资源归属与用途，并验证所有运行环境只使用同一套 OSS canonical 资源、公共 CDN 和私有鉴权交付。

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

### Requirement: OSS scope and canonical reference are visible
Each media row SHALL display its public/private OSS scope, object key, MIME type, available size/checksum, canonical CDN URL or protected-access mode, and reference count. The CMS MUST NOT expose credentials, filesystem paths, permanent private URLs, or a local provider as a valid upload target.

#### Scenario: Public OSS asset is listed
- **WHEN** an operator opens a published cover or narration
- **THEN** the row identifies the public OSS scope, immutable key, checksum, CDN URL, and all current references without showing credentials

#### Scenario: Private OSS asset is listed
- **WHEN** an authorized operator inspects user evidence, private community media, or a temporary preview
- **THEN** the row identifies the private scope and protected access method without rendering a permanent public URL

### Requirement: Shared canonical resource status is visible
The CMS SHALL show that production and test runtimes use the same public bucket, private bucket, object keys, media references, public CDN base, and private-access behavior. It SHALL compare safe public/private bucket identities, object counts, sampled keys/checksums, CDN resolution, and authorized private resolution. It MUST NOT create or encourage environment-specific business-media copies. Disposable integration-test writes SHALL be reported separately and limited to an authorized temporary prefix that cannot overwrite or delete canonical objects.

#### Scenario: Production and test agree
- **WHEN** both runtimes report identical public/private resource identities and sampled public and private assets have the same object keys/checksums and access behavior
- **THEN** the library shows complete shared-resource readiness with the audit time and scope counts

#### Scenario: Test points to copied or different canonical resources
- **WHEN** the environment audit detects a different public/private bucket, business-media key mapping, reference, CDN base, private-access behavior, or checksum
- **THEN** the CMS reports configuration drift and blocks readiness until the environments share the intended object set

### Requirement: Any local persistent media is a visible blocker
In every connected runtime environment, the CMS SHALL present a prominent blocking state if the API or admin service reports incomplete OSS configuration, a local provider, a media host mount, a filesystem reference, a local media read, or an unverified public/private migration. The warning SHALL identify affected categories/counts and provide migration/recheck guidance without exposing secrets.

#### Scenario: Runtime still uses local media
- **WHEN** readiness finds a local provider, `/api/v1/assets/` disk read, local path, or persistent media mount
- **THEN** the media library reports the environment as not ready and no upload or publication surface claims successful OSS storage

#### Scenario: Full OSS audit passes
- **WHEN** both services require OSS, public samples resolve through CDN, private samples require authorization, production/test share canonical identities, and every database reference reconciles
- **THEN** the library shows successful OSS-only readiness with the audit time and public/private counts
