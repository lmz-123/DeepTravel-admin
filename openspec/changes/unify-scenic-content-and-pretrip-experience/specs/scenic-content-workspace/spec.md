## Purpose

让运营人员围绕一个明确选中的景点集中维护普通站点、碎片故事、旁白、标签与出发前内容，同时保持既有模型、审核发布和用户旅程兼容性。

## ADDED Requirements

### Requirement: One scenic-content navigation entry
The CMS SHALL provide one “景点内容” navigation entry for ordinary stop/story and fragmented-tour administration and SHALL NOT require operators to switch between separate “站点与故事” and “碎片导览” columns to edit one scenic area.

#### Scenario: Scenic area contains both content kinds
- **WHEN** an operator opens a scenic area with legacy stops and managed fragments
- **THEN** one workspace exposes clearly separated sections for both kinds under the same scenic context

#### Scenario: Scenic area contains only one content kind
- **WHEN** one section has no records
- **THEN** the workspace shows an actionable empty section without hiding or fabricating the other content kind

### Requirement: Scenic selection is searchable and city-grouped
The workspace SHALL label the action “选择景点” and present a searchable selection surface grouped by backend-provided city, with each result showing enough identity to distinguish scenic areas, including title, cover or fallback, lifecycle status, and available content summary. It MUST support keyboard operation, a clear selected state, and restoration of the most recent valid scenic context; it MUST NOT rely on a single long native select list.

#### Scenario: Operator searches many scenic areas
- **WHEN** the operator searches by city name, scenic title, or slug
- **THEN** matching cards remain grouped by city and selecting one closes the surface and loads only that scenic context

#### Scenario: Recent scenic area is no longer available
- **WHEN** the saved recent ID is absent from the latest authorized catalog
- **THEN** the CMS clears it and asks the operator to choose instead of loading stale content

#### Scenario: Operator uses a keyboard
- **WHEN** focus enters the selection surface
- **THEN** the operator can search, traverse results, choose a scenic area, and close the surface without pointer input

### Requirement: Scenic context protects edits
All content sections SHALL read and write against the same selected scenic ID. Switching, closing, or refreshing while a section has unsaved changes SHALL require an explicit discard or save decision, and a delayed response from a previous scenic area MUST NOT overwrite the current view.

#### Scenario: Operator switches with unsaved changes
- **WHEN** an edited field is dirty and the operator chooses another scenic area
- **THEN** the CMS keeps the current context until the operator saves or explicitly discards changes

#### Scenario: Previous request finishes late
- **WHEN** a response for scenic area A arrives after the operator has selected scenic area B
- **THEN** it is ignored for presentation and cannot populate or save B's form

### Requirement: Pre-departure is edited within the scenic workspace
The workspace SHALL include a per-scenic pre-departure section for concise introduction text and its matching reviewed narration, with draft/review/publish state and preview. The standalone pre-departure panel under city stories SHALL be removed from the active administration surface.

#### Scenario: Operator configures pre-departure
- **WHEN** an operator writes the introduction and selects or generates narration for the selected scenic area
- **THEN** the preview shows the same compact text/audio content intended for the first manual surface and saves it only to that scenic area

#### Scenario: Text changes after audio approval
- **WHEN** published or approved introduction text changes
- **THEN** stale narration approval is invalidated and publication remains blocked until matching audio is reviewed

### Requirement: Tags round-trip across both node editors
Both legacy-stop and managed-fragment sections SHALL expose ordered free-form `experience_tags`, apply the shared normalization limits, and preserve them across structured edits, advanced JSON, import/export, and lifecycle transitions.

#### Scenario: Operator adds an unknown tag
- **WHEN** an operator enters a valid new tag not known to the CMS frontend
- **THEN** it saves and returns through the same editor without an allowlist error

#### Scenario: Existing tags are edited elsewhere
- **WHEN** a graph or import round-trip includes ordered tags
- **THEN** reopening the corresponding node editor shows the same normalized order without loss
