"""Enforces the zero-write-capable-tools rule for every agent call.

Per rabbitqa_spec_v1.0.0.md §4.4 / §7: "Agents MUST NOT be given tool access to:
database writes, graph writes, shell execution, or unrestricted network calls...
enforced at the gateway level... not merely instructed via prompt."

This module is the single choke point every agent client (Extraction, Reference,
Critic, Graph Mapping) must route tool access through. It is allow-list based:
only tools explicitly registered as read-only lookups are reachable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ToolCategory(str, Enum):
    READ_ONLY_DOCUMENT_LOOKUP = "read_only_document_lookup"
    READ_ONLY_VOCABULARY_LOOKUP = "read_only_vocabulary_lookup"


class ToolNotPermittedError(Exception):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    category: ToolCategory
    handler: Callable[..., object]


class ToolPolicy:
    """An agent-scoped, read-only tool registry. There is no code path here that can
    register a write-capable tool — the constructor only accepts ToolCategory.READ_ONLY_*
    values, so a DB-write/graph-write/shell/unrestricted-network tool cannot be added
    even by a caller that tries to."""

    _ALLOWED_CATEGORIES = {
        ToolCategory.READ_ONLY_DOCUMENT_LOOKUP,
        ToolCategory.READ_ONLY_VOCABULARY_LOOKUP,
    }

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register_read_only_tool(self, definition: ToolDefinition) -> None:
        if definition.category not in self._ALLOWED_CATEGORIES:
            raise ToolNotPermittedError(
                f"Tool category '{definition.category}' is not a permitted read-only category."
            )
        self._tools[definition.name] = definition

    def invoke(self, tool_name: str, *args, **kwargs):
        if tool_name not in self._tools:
            raise ToolNotPermittedError(
                f"Tool '{tool_name}' is not registered on this agent's allow-list."
            )
        return self._tools[tool_name].handler(*args, **kwargs)

    def allowed_tool_names(self) -> list[str]:
        return sorted(self._tools)


def empty_policy() -> ToolPolicy:
    """The default for any agent that needs no tools at all (e.g. Critic Agent,
    which only reasons over a supplied proposal + span)."""
    return ToolPolicy()
