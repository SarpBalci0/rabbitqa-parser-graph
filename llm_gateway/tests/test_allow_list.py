"""§7 LLM gateway zone: "Model provider is selected from an explicit allow-list
(no arbitrary endpoint)." Found untested during the T100 security review pass."""

import pytest

from llm_gateway.allow_list import AllowList, ProviderConfig, ProviderNotAllowedError


def test_unregistered_provider_is_rejected():
    allow_list = AllowList(providers={})
    with pytest.raises(ProviderNotAllowedError):
        allow_list.get("some-arbitrary-provider")


def test_registered_provider_is_reachable():
    config = ProviderConfig(name="acme", endpoint="https://acme.example/v1", model_version="acme-1.0")
    allow_list = AllowList(providers={"acme": config})
    assert allow_list.get("acme") == config


def test_arbitrary_endpoint_string_cannot_bypass_the_allow_list():
    """There is no method that accepts a raw endpoint string and returns a usable
    config without it first being registered — get() only ever returns configs
    that were explicitly placed in the allow-list."""
    allow_list = AllowList(providers={})
    with pytest.raises(ProviderNotAllowedError):
        allow_list.get("https://totally-arbitrary-endpoint.evil/v1")


def test_names_lists_only_registered_providers():
    allow_list = AllowList(
        providers={
            "a": ProviderConfig(name="a", endpoint="https://a", model_version="1"),
            "b": ProviderConfig(name="b", endpoint="https://b", model_version="1"),
        }
    )
    assert allow_list.names() == ["a", "b"]
