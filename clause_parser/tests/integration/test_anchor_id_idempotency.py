"""§9.1/§2.1: re-ingesting identical source content yields byte-identical
anchor_ids (replay idempotency) — anchor_id is a pure function of
(document_id, source_version, structural_path)."""

from clause_parser.src.canonicalize.canonicalizer import build_structure, canonicalize_text

_TEXT = (
    "Article 21\n"
    "1. The operator shall notify the competent authority within 30 days.\n"
    "Article 22\n"
    "1. The manufacturer must maintain records.\n"
)


def test_anchor_ids_are_byte_identical_across_repeated_canonicalization():
    canonical_1 = canonicalize_text(_TEXT)
    canonical_2 = canonicalize_text(_TEXT)
    assert canonical_1 == canonical_2

    structure_1 = build_structure(canonical_1, document_id="doc_fixed123456", source_version="v1")
    structure_2 = build_structure(canonical_2, document_id="doc_fixed123456", source_version="v1")

    ids_1 = [a.anchor_id for a in structure_1]
    ids_2 = [a.anchor_id for a in structure_2]
    assert ids_1 == ids_2
    assert len(ids_1) > 0


def test_anchor_id_does_not_depend_on_source_version_identity_of_other_documents():
    canonical = canonicalize_text(_TEXT)
    structure_v1 = build_structure(canonical, document_id="doc_fixed123456", source_version="v1")
    structure_v2 = build_structure(canonical, document_id="doc_fixed123456", source_version="v2")

    ids_v1 = {a.anchor_id for a in structure_v1}
    ids_v2 = {a.anchor_id for a in structure_v2}
    assert ids_v1.isdisjoint(ids_v2), "anchor_ids must be scoped by source_version"
