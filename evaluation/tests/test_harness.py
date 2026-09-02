"""Confirms the T093 metrics harness actually runs and produces sane, real
numbers against the synthetic corpus — not that it produces impressive numbers,
just that it computes what it claims to."""

from evaluation.metrics.harness import run_full_harness


def test_harness_runs_and_produces_bounded_metrics():
    results = run_full_harness()

    detection = results["detection"]
    assert 0.0 <= detection["precision"] <= 1.0
    assert 0.0 <= detection["recall"] <= 1.0
    assert detection["true_positive"] + detection["false_negative"] == sum(
        1 for c in __import__("json").loads(
            (__import__("pathlib").Path(__file__).resolve().parent.parent / "corpus" / "labels.json").read_text()
        )["clauses"].values()
        if c["is_normative"]
    )

    # The known hard-negative-definitional clause (article-2/paragraph-3) is
    # DESIGNED to fool the naive keyword detector — confirm it actually does,
    # which is what proves the corpus is exercising precision, not just recall.
    assert detection["false_positive"] >= 1

    for key in (
        "evidence_span_exact_overlap_rate",
        "source_anchor_validity_rate",
        "accepted_record_source_fidelity",
        "replay_idempotency",
    ):
        value = results[key]
        assert value is not None
        assert 0.0 <= value <= 1.0

    # §2.2 invariant 2 / §9.2: accepted-record source fidelity MUST be 100%.
    assert results["accepted_record_source_fidelity"] == 1.0
    assert results["replay_idempotency"] == 1.0

    # Core fields F1 (actor/action/object) — actor should score well (the
    # fixture extractor does real controlled-vocabulary matching for actor);
    # action/object are expected to score low since the fixture extractor
    # doesn't do real semantic extraction for those two fields (see
    # labels.json's $core_field_matching_note). Assert the SHAPE and the
    # actor/action asymmetry, not a specific score, so this test doesn't need
    # updating every time corpus wording changes.
    core = results["core_fields_f1"]
    assert core["macro_f1"] is not None
    assert core["per_field"]["actor"]["f1"] > core["per_field"]["action"]["f1"]
    assert core["per_field"]["action"]["f1"] == 0.0  # predicted action is always the full sentence

    # Graph mapping macro F1: the deterministic mapper unconditionally derives
    # Obligation/Provision/Actor + DERIVED_FROM/IMPOSES_ON for any accepted
    # obligation with an actor, so this should be a clean 1.0 given the current
    # corpus has no clause that breaks that (e.g. zero actors).
    assert results["graph_mapping_macro_f1"]["macro_f1"] == 1.0

    # Competency queries: all use full, internally-consistent fixture mappings,
    # so all should resolve correctly.
    cq = results["competency_query_accuracy"]
    assert cq["total"] == 6
    assert cq["accuracy"] == 1.0

    # Full chain / graph integrity: multiple snapshots, one per genuinely
    # normative clause.
    assert results["full_chain"]["snapshots_published"] > 1
    assert results["parser_transaction_success_rate"] == 1.0
    assert results["graph_integrity_provenance_pass_rate"] == 1.0

    # Complex fields F1 (condition/deadline/exception/reference): now genuinely
    # computed against real (regex-based) extraction. Two known, documented
    # extractor limitations (see labels.json's $complex_field_matching_note)
    # mean this is NOT expected to be a clean 1.0 — assert the shape and that
    # it's meaningfully below perfect, not a specific score.
    complex_fields = results["complex_fields_f1"]
    assert complex_fields["macro_f1"] is not None
    assert 0.0 < complex_fields["macro_f1"] < 1.0
    assert complex_fields["per_field_f1"]["exceptions"] == 1.0  # exception extraction has no known miss in this corpus
    assert complex_fields["per_field_f1"]["deadline"] < 1.0  # two known misses (truncation, trailing-condition pattern)

    assert results["_corpus_is_synthetic_not_real_regulation"] is True
    assert results["_not_computed"] == []  # every §9.2 measure now has a real number
