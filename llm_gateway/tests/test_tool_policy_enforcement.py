"""FR-033: every agent client's tool allow-list is empty except read-only
document/vocabulary lookups — no DB write, graph write, shell, or unrestricted
network tool is reachable, enforced at the gateway level."""

import pytest

from llm_gateway.tool_policy import ToolCategory, ToolDefinition, ToolNotPermittedError, ToolPolicy, empty_policy


def test_empty_policy_has_zero_reachable_tools():
    policy = empty_policy()
    assert policy.allowed_tool_names() == []
    with pytest.raises(ToolNotPermittedError):
        policy.invoke("anything")


def test_only_read_only_categories_can_be_registered():
    policy = ToolPolicy()
    policy.register_read_only_tool(
        ToolDefinition(
            name="lookup_document",
            category=ToolCategory.READ_ONLY_DOCUMENT_LOOKUP,
            handler=lambda: "ok",
        )
    )
    assert policy.allowed_tool_names() == ["lookup_document"]
    assert policy.invoke("lookup_document") == "ok"


def test_no_write_capable_tool_category_exists_to_register():
    """There is no ToolCategory value representing a DB write, graph write, shell
    execution, or unrestricted network call — the enum itself is the enforcement
    mechanism, not a runtime check that could be bypassed."""
    category_names = {c.value for c in ToolCategory}
    assert category_names == {"read_only_document_lookup", "read_only_vocabulary_lookup"}
    forbidden_terms = {"write", "shell", "exec", "network", "delete", "graph_write", "db_write"}
    for name in category_names:
        assert not any(term in name for term in forbidden_terms)


def test_attempting_to_register_a_fabricated_write_category_is_rejected():
    """Even if a caller constructs a bogus 'category' value outside the enum,
    register_read_only_tool's allow-list check rejects anything not in
    _ALLOWED_CATEGORIES."""
    policy = ToolPolicy()

    class FakeCategory:
        value = "graph_write"

    with pytest.raises(ToolNotPermittedError):
        policy.register_read_only_tool(
            ToolDefinition(name="evil_write", category=FakeCategory(), handler=lambda: None)
        )


def test_extraction_and_reference_agents_use_empty_tool_policy():
    """Both fixture agent clients call llm_gateway.tool_policy.empty_policy() —
    confirmed by source inspection of the agent modules themselves, since the
    fixture implementations need no tools at all for this pass."""
    import inspect

    from clause_parser.src.agents import extraction_agent, reference_agent

    for module in (extraction_agent, reference_agent):
        source = inspect.getsource(module)
        assert "empty_policy()" in source
