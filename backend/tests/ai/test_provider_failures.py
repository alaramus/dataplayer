"""A provider failure becomes one safe sentence, billing included (D2c).

An empty balance used to read as a generic "could not answer" — or worse,
as "try again in a moment" — and a run that streamed half an answer before
failing showed no error at all. These tests pin the classification; the
transcript side is covered by the conversation tests.
"""

import httpx
import openai

from app.ai.catalog import ModelInfo
from app.ai.providers import ProviderChatModels
from app.ai.providers.failures import (
    SENTENCES,
    UNKNOWN_FAILURE,
    classify,
    from_parts,
)


def _model() -> ModelInfo:
    return ModelInfo(
        provider="openai",
        id="gpt-test",
        name="GPT test",
        context_window=8000,
        max_output_tokens=1024,
        reasoning=False,
        image_input=False,
    )


def _openai_error(status: int, body: object | None) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.openai.test/v1/responses")
    response = httpx.Response(status, request=request)
    return openai.APIStatusError("provider said no", response=response, body=body)


def test_every_kind_has_a_sentence_without_provider_text() -> None:
    assert set(SENTENCES) == {"key_refused", "no_credits", "rate_limited", "not_found", "unavailable"}
    assert UNKNOWN_FAILURE
    for sentence in (*SENTENCES.values(), UNKNOWN_FAILURE):
        assert "sk-" not in sentence


def test_status_only_mapping_is_unchanged() -> None:
    assert classify(401) == "key_refused"
    assert classify(403) == "key_refused"
    assert classify(404) == "not_found"
    assert classify(429) == "rate_limited"
    assert classify(500) == "unavailable"
    assert classify(503) == "unavailable"
    assert classify(400) is None
    assert classify(None) is None


def test_billing_hints_beat_throttling() -> None:
    assert classify(429, "insufficient_quota") == "no_credits"
    assert classify(429, None, "insufficient_quota") == "no_credits"
    assert classify(400, None, None, "Your credit balance is too low") == "no_credits"
    assert classify(403, "billing_hard_limit_reached") == "no_credits"
    assert classify(429, None, None, "Quota exceeded for this plan") == "no_credits"
    assert classify(402) == "no_credits"


def test_plain_throttling_stays_throttling() -> None:
    assert classify(429, "rate_limit_exceeded") == "rate_limited"
    assert classify(429, None, None, "Rate limit reached, try again later") == "rate_limited"


def test_from_parts_reads_openai_shaped_bodies() -> None:
    nested = {"error": {"code": "insufficient_quota", "type": "insufficient_quota"}}
    assert from_parts(429, nested) == "no_credits"
    flat = {"code": "invalid_api_key", "type": "invalid_request_error"}
    assert from_parts(401, flat) == "key_refused"
    assert from_parts(401, None) == "key_refused"
    assert from_parts(418, {"error": "teapot"}) is None
    assert from_parts(400, "not a dict") is None


def test_openai_insufficient_quota_is_a_billing_sentence() -> None:
    models = ProviderChatModels()
    marker = "quota-marker-9f3a"
    error = _openai_error(
        429, {"error": {"code": "insufficient_quota", "message": f"You exceeded your {marker}"}}
    )
    sentence = models.sentence(_model(), error)
    assert sentence == SENTENCES["no_credits"]
    assert marker not in sentence
    assert models.sentence(_model(), RuntimeError("boom")) == UNKNOWN_FAILURE
