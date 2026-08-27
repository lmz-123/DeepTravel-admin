## Purpose

让运营人员围绕一个明确选中的景点集中维护普通站点、碎片故事、旁白、标签与出发前内容，同时保持既有模型、审核发布和用户旅程兼容性。

## ADDED Requirements

### Requirement: One scenic-content navigation entry
The CMS SHALL provide one “景点内容” navigation entry for scenic metadata, ordinary stop/story and fragmented-tour administration and SHALL NOT expose independent “路线” or “题目” navigation entries. Route records SHALL remain internal scenic identities for compatible APIs and clients.

#### Scenario: Scenic area contains both content kinds
- **WHEN** an operator opens a scenic area with legacy stops and managed fragments
- **THEN** one workspace exposes clearly separated sections for both kinds under the same scenic context

#### Scenario: Scenic area contains only one content kind
- **WHEN** one section has no records
- **THEN** the workspace shows an actionable empty section without hiding or fabricating the other content kind

#### Scenario: Operator needs scenic metadata
- **WHEN** the operator edits the selected scenic area's title, description, cover or other necessary route-backed metadata
- **THEN** the edit opens from “景点内容” without navigating to a route table

### Requirement: Every content node uses one minimal card
Each legacy stop or managed fragment SHALL appear in exactly one normal editing card. The card SHALL expose only node title, story copy, address/location, arrival radius, and ordered experience tags needed for editorial work. Optional summaries, summary candidates, causal/source/claim fields, script versions, direct audio paths, and other graph implementation details MUST NOT be required or shown in the normal editor, and existing hidden values SHALL round-trip unchanged.

#### Scenario: Operator edits one node
- **WHEN** the operator changes its copy, location or tags and saves
- **THEN** that one card persists the change without requiring values in unrelated technical fields

#### Scenario: Legacy technical metadata exists
- **WHEN** a node already has footprint summaries, causal links, claims or script metadata
- **THEN** saving the minimal card preserves those values unless a dedicated compatibility process changes them

### Requirement: Narration generation is scenic-level
The workspace SHALL provide one compact narration control for the selected scenic area: choose an existing voice profile, generate missing or regenerate all content audio, inspect coverage, and publish matching audio. When pre-departure text exists, that coverage and batch operation SHALL include the pre-departure narration together with all later nodes. Voice-profile authoring and per-node technical audition controls SHALL NOT clutter content cards.

#### Scenario: Operator generates narration
- **WHEN** an operator chooses a voice and generates narration for the selected scenic area
- **THEN** missing/stale pre-departure and node coverage plus the batch result are shown without editing separate audio paths

#### Scenario: Operator regenerates the whole scenic area
- **WHEN** an operator chooses “重新生成全部语音” for a scenic area with pre-departure text and later nodes
- **THEN** the system generates matching audio for the pre-departure card and every node in the same batch using the selected voice

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
The workspace SHALL render pre-departure as the first normal content card below the scenic narration control and scenic-copy heading, followed by the later scenic nodes. The card SHALL contain concise introduction text, matching narration state, and draft/publish actions; it MUST NOT appear as a separate top-level panel or require a separate generation workflow.

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
