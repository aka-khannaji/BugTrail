from bugtrail.ai.cost import estimate_cost_usd, format_cost
from bugtrail.ai.provider import AIProvider
from bugtrail.config import AIConfig


def test_provider_unavailable_without_key_or_local_endpoint():
    provider = AIProvider(AIConfig(base_url="https://api.openai.com/v1"), api_key=None)
    assert not provider.available


def test_provider_available_with_key():
    provider = AIProvider(AIConfig(base_url="https://api.openai.com/v1"), api_key="sk-test")
    assert provider.available


def test_provider_available_keyless_local_endpoint():
    provider = AIProvider(AIConfig(base_url="http://127.0.0.1:8000/v1"), api_key=None)
    assert provider.available
    assert provider.is_local


def test_chat_url_auto_appends_v1_when_missing():
    assert (
        AIProvider(AIConfig(base_url="http://127.0.0.1:8765"), api_key=None)._chat_url()
        == "http://127.0.0.1:8765/v1/chat/completions"
    )


def test_chat_url_preserves_explicit_v1():
    provider = AIProvider(AIConfig(base_url="https://api.openai.com/v1"), api_key="sk-test")
    assert provider._chat_url() == "https://api.openai.com/v1/chat/completions"
    provider = AIProvider(AIConfig(base_url="http://127.0.0.1:8765/v1/"), api_key=None)
    assert provider._chat_url() == "http://127.0.0.1:8765/v1/chat/completions"


def test_local_result_is_free():
    from bugtrail.ai.provider import AIResult

    result = AIResult(
        task="evidence ranking",
        provider="openai-compatible",
        model="qwen2.5-0.5b-instruct",
        content="ok",
        input_tokens=100,
        output_tokens=50,
        latency_ms=10,
        local=True,
    )
    assert result.is_local
    assert result.cost_usd == 0.0
    assert format_cost(result.cost_usd) == "$0.000"


def test_unknown_model_uses_default_pricing():
    assert estimate_cost_usd("gpt-4o-mini", 1_000_000, 0) == 0.15
    assert estimate_cost_usd("some-local-model", 1_000_000, 0) > 0.0
