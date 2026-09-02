"""Prompt-injection boundary helper per rabbitqa_spec_v1.0.0.md §4.4:

"source document text passed to any agent MUST be wrapped as a clearly delimited
untrusted data block in the context package..., and the system/instruction prompt
MUST be assembled separately and never derived from or concatenated with document
content."
"""

from __future__ import annotations

from dataclasses import dataclass

UNTRUSTED_BLOCK_START = "<<<UNTRUSTED_DOCUMENT_CONTENT_START>>>"
UNTRUSTED_BLOCK_END = "<<<UNTRUSTED_DOCUMENT_CONTENT_END>>>"


@dataclass(frozen=True)
class ContextPackage:
    """system_prompt is authored/static instruction text, never built from document
    content. untrusted_document_text is wrapped in a clearly delimited block and MUST
    NOT be concatenated into system_prompt at any point in the call path."""

    system_prompt: str
    untrusted_document_text: str
    structured_context: dict

    def render_untrusted_block(self) -> str:
        return f"{UNTRUSTED_BLOCK_START}\n{self.untrusted_document_text}\n{UNTRUSTED_BLOCK_END}"

    def to_agent_payload(self) -> dict:
        """The only sanctioned way to assemble what actually gets sent to a model:
        system_prompt and the untrusted block remain distinct fields, never merged
        into a single free-text string that could blur the boundary."""
        return {
            "system_prompt": self.system_prompt,
            "untrusted_document_block": self.render_untrusted_block(),
            "structured_context": self.structured_context,
        }


def build_context_package(
    *, system_prompt: str, document_text: str, structured_context: dict
) -> ContextPackage:
    if UNTRUSTED_BLOCK_START in system_prompt or UNTRUSTED_BLOCK_END in system_prompt:
        raise ValueError(
            "system_prompt must not contain the untrusted-block delimiters; "
            "it must be assembled independently of document content."
        )
    return ContextPackage(
        system_prompt=system_prompt,
        untrusted_document_text=document_text,
        structured_context=structured_context,
    )
