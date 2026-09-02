"""FR-035: every agent call logs {model_version, prompt_version, input_hash,
output_hash, context_hash}."""

from llm_gateway.logging import AgentCallLog


def test_log_call_records_all_five_required_fields():
    log = AgentCallLog()
    record = log.log_call(
        agent_role="extraction_agent",
        model_version="fixture-rule-based-v1",
        prompt_version="extraction-v1",
        context_package={"span": "some text"},
        raw_output={"legal_semantics": {}},
    )
    assert record.model_version == "fixture-rule-based-v1"
    assert record.prompt_version == "extraction-v1"
    assert record.input_hash and isinstance(record.input_hash, str)
    assert record.output_hash and isinstance(record.output_hash, str)
    assert record.context_hash and isinstance(record.context_hash, str)


def test_different_inputs_produce_different_hashes():
    log = AgentCallLog()
    r1 = log.log_call(
        agent_role="extraction_agent",
        model_version="v1",
        prompt_version="v1",
        context_package={"span": "text A"},
        raw_output={"a": 1},
    )
    r2 = log.log_call(
        agent_role="extraction_agent",
        model_version="v1",
        prompt_version="v1",
        context_package={"span": "text B"},
        raw_output={"a": 2},
    )
    assert r1.input_hash != r2.input_hash
    assert r1.output_hash != r2.output_hash


def test_records_for_clause_filters_correctly():
    log = AgentCallLog()
    log.log_call(
        agent_role="extraction_agent",
        model_version="v1",
        prompt_version="v1",
        context_package={},
        raw_output={},
        clause_id="clause-1",
    )
    log.log_call(
        agent_role="extraction_agent",
        model_version="v1",
        prompt_version="v1",
        context_package={},
        raw_output={},
        clause_id="clause-2",
    )
    assert len(log.records_for_clause("clause-1")) == 1
    assert len(log.records_for_clause("clause-2")) == 1
    assert len(log.records_for_clause("clause-does-not-exist")) == 0


def test_extraction_agent_actually_logs_a_call(tmp_path):
    """End-to-end confirmation, not just a direct call to log_call: running the
    real Extraction Agent produces a queryable log entry for its clause_id."""
    from llm_gateway.logging import DEFAULT_AGENT_CALL_LOG
    from clause_parser.src.agents.extraction_agent import run_extraction

    before = len(DEFAULT_AGENT_CALL_LOG.records)
    run_extraction(
        span_text="1. The operator shall notify within 10 days.",
        anchor_id="doc_x:v1:article-1/paragraph-1",
        anchor_label="Article 1(1)",
        char_start=0,
        char_end=10,
        controlled_vocabulary=["operator"],
        clause_id="doc_x:v1:article-1/paragraph-1",
    )
    after = DEFAULT_AGENT_CALL_LOG.records
    assert len(after) == before + 1
    assert after[-1].agent_role == "extraction_agent"
    assert after[-1].clause_id == "doc_x:v1:article-1/paragraph-1"
