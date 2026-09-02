"""Pydantic models mirroring the literal JSON Schema contracts under shared_contracts/schemas/.

These are used for API (de)serialization convenience only. Validation against the literal
schema files (see validation.py) remains authoritative per rabbitqa_spec_v1.0.0.md §2 —
a payload that passes Pydantic construction is still schema-validated before persistence
or transmission across a module boundary.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Instrument = Literal["NIS2", "CRA", "DORA"]


# --- CanonicalDocument (§2.1) -------------------------------------------------


class AnchorNode(BaseModel):
    anchor_id: str
    type: Literal["article", "paragraph", "annex", "table", "footnote", "recital"]
    label: str | None = None
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    parent_anchor_id: str | None = None


class CanonicalDocument(BaseModel):
    document_id: str
    source_version: str
    instrument: Instrument
    checksum_sha256: str
    language: str
    jurisdiction: Literal["EU"] = "EU"
    structure: list[AnchorNode] = Field(default_factory=list)
    raw_storage_uri: str | None = None
    created_at: datetime
    schema_version: Literal["1.0.0"] = "1.0.0"


# --- ObligationObject (§2.2) --------------------------------------------------


class ObligationIdentity(BaseModel):
    document_id: str
    source_version: str
    language: str
    jurisdiction: Literal["EU"] = "EU"
    instrument: Instrument
    clause_id: str
    schema_version: Literal["1.0.0"] = "1.0.0"


class SourceEvidence(BaseModel):
    anchor_id: str
    char_start: int
    char_end: int
    verbatim_text: str
    evidence_hash: str


class Deadline(BaseModel):
    type: Literal["absolute_date", "relative_period", "recurring"]
    value: str
    normalized_iso: str | None = None


class LegalSemantics(BaseModel):
    norm_type: Literal["obligation", "prohibition", "permission", "definition_only"]
    actor: list[str] = Field(min_length=1)
    modality: Literal["shall", "must", "may", "should"]
    action: str
    object: str
    scope: str
    trigger: str | None = None
    deadline: Deadline | None = None
    frequency: str | None = None
    conditions: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)


class References(BaseModel):
    definition_links: list[str] = Field(default_factory=list)
    related_articles: list[str] = Field(default_factory=list)
    annex_references: list[str] = Field(default_factory=list)
    resolved_target_ids: list[str] = Field(default_factory=list)


class RevisionHistoryEntry(BaseModel):
    reviewer_id: str
    timestamp: datetime
    action: Literal["accept", "edit", "reject", "escalate"]
    rationale: str = Field(min_length=1)
    diff: dict[str, Any] | None = None


class Governance(BaseModel):
    field_confidence: dict[str, float] = Field(default_factory=dict)
    ambiguity_flag: bool = False
    inference_flag: bool = False
    model_version: str | None = None
    prompt_version: str | None = None
    review_status: Literal["pending", "accepted", "edited", "rejected", "escalated"]
    revision_history: list[RevisionHistoryEntry] = Field(default_factory=list)


class ObligationObject(BaseModel):
    identity: ObligationIdentity
    source_evidence: SourceEvidence
    legal_semantics: LegalSemantics
    references: References = Field(default_factory=References)
    governance: Governance


# --- ValidationReport (§2.3) --------------------------------------------------

CheckName = Literal[
    "schema_validity",
    "controlled_vocabulary",
    "evidence_span_fidelity",
    "date_normalization",
    "quantity_normalization",
    "reference_validity",
    "cross_field_consistency",
]


class ValidationCheck(BaseModel):
    check_name: CheckName
    status: Literal["pass", "fail", "warn"]
    message: str


class ValidationReport(BaseModel):
    target_clause_id: str
    run_id: str
    checks: list[ValidationCheck] = Field(default_factory=list)
    overall_status: Literal["pass", "fail", "needs_review"]


# --- ConstraintReport (interim, see shared_contracts/schemas/README.md) ------

RuleName = Literal[
    "obligation_derived_from_provision",
    "obligation_imposes_on_actor",
    "maps_to_control_endpoint_restriction",
    "evidenced_by_endpoint_restriction",
    "no_dangling_node_reference",
    "relationship_type_pair_allowed",
]


class ConstraintRule(BaseModel):
    rule_name: RuleName
    status: Literal["pass", "fail"]
    message: str
    offending_node_ids: list[str] = Field(default_factory=list)
    offending_relationship: dict[str, str] | None = None


class ConstraintReport(BaseModel):
    changeset_id: str
    rules: list[ConstraintRule] = Field(default_factory=list)
    overall_status: Literal["pass", "fail"]


# --- GraphChangeSet (§2.4) ----------------------------------------------------

NodeType = Literal[
    "Regulation", "Provision", "Definition", "Obligation", "Actor", "Action", "Condition",
    "Exception", "Deadline", "Control", "Risk", "EvidenceRequirement", "Asset", "System",
    "API", "Dataset", "TestAsset", "Agent",
]

RelationshipType = Literal[
    "DERIVED_FROM", "IMPOSES_ON", "REQUIRES", "CONDITIONED_BY", "EXCEPTION_TO", "REFERENCES",
    "DEFINES", "AMENDS", "SUPERSEDES", "APPLIES_TO", "MAPS_TO_CONTROL", "AFFECTS_ASSET",
    "SATISFIED_BY", "EVIDENCED_BY",
]


class NodeProvenance(BaseModel):
    clause_id: str


class ProposedNode(BaseModel):
    node_id: str
    type: NodeType
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: NodeProvenance


class ProposedRelationship(BaseModel):
    from_node_id: str
    to_node_id: str
    type: RelationshipType
    valid_from: date | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class GraphChangeSet(BaseModel):
    changeset_id: str
    base_snapshot_id: str | None
    source_clause_ids: list[str] = Field(min_length=1)
    ontology_version: str
    proposed_nodes: list[ProposedNode] = Field(default_factory=list)
    proposed_relationships: list[ProposedRelationship] = Field(default_factory=list)
    superseded_assertions: list[str] = Field(default_factory=list)
    constraint_report: ConstraintReport
    status: Literal["draft", "validated", "approved", "rejected", "published"]


# --- GraphSnapshotExport (§2.5) -----------------------------------------------


class ExportedObligation(BaseModel):
    clause_id: str
    obligation_node_id: str
    mapped_controls: list[str] = Field(default_factory=list)
    mapped_assets: list[str] = Field(default_factory=list)
    mapped_evidence: list[str] = Field(default_factory=list)
    review_status: str
    source_anchor: str
    confidence: float = Field(ge=0, le=1)


class GraphSnapshotExport(BaseModel):
    snapshot_id: str
    ontology_version: str
    valid_from: date
    superseded_snapshot_id: str | None = None
    obligations: list[ExportedObligation] = Field(default_factory=list)
    schema_version: Literal["1.0.0"] = "1.0.0"
