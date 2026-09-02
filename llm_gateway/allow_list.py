"""Explicit, configuration-driven model-provider allow-list.

Per rabbitqa_spec_v1.1.0.md §7 LLM gateway zone: "Model provider is selected from an
explicit allow-list (no arbitrary endpoint)". The concrete provider identity is an open
item (spec §10 Q2, research.md §5) left to Engineering — this module only enforces that
whatever is configured must be on the allow-list; it never accepts an arbitrary endpoint
string from a caller.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ProviderNotAllowedError(Exception):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    endpoint: str
    model_version: str


def _default_allow_list() -> dict[str, ProviderConfig]:
    """Reads RABBITQA_LLM_ALLOW_LIST env var (comma-separated name:endpoint:model_version)
    if present; otherwise returns an empty allow-list (fixture/offline mode)."""
    raw = os.environ.get("RABBITQA_LLM_ALLOW_LIST", "")
    entries: dict[str, ProviderConfig] = {}
    for item in filter(None, raw.split(",")):
        parts = item.split(":")
        if len(parts) != 3:
            continue
        name, endpoint, model_version = parts
        entries[name] = ProviderConfig(name=name, endpoint=endpoint, model_version=model_version)
    return entries


class AllowList:
    def __init__(self, providers: dict[str, ProviderConfig] | None = None):
        self._providers = providers if providers is not None else _default_allow_list()

    def get(self, provider_name: str) -> ProviderConfig:
        if provider_name not in self._providers:
            raise ProviderNotAllowedError(
                f"Provider '{provider_name}' is not on the configured allow-list."
            )
        return self._providers[provider_name]

    def register(self, config: ProviderConfig) -> None:
        """Test/fixture-only registration hook — production configuration comes from
        RABBITQA_LLM_ALLOW_LIST, never from an arbitrary runtime caller."""
        self._providers[config.name] = config

    def names(self) -> list[str]:
        return sorted(self._providers)


DEFAULT_ALLOW_LIST = AllowList()
