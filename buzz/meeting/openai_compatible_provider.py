"""OpenAI-compatible Chat Completions meeting-summary provider."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from buzz.meeting._bounded_http_transport import (
    BoundedHttpCleanupRequiredError,
    BoundedHttpResponseTooLargeError,
    BoundedHttpTimeoutError,
    BoundedHttpTransport,
    BoundedHttpTransportError,
)
from buzz.meeting.meeting_summary_prompt import (
    MEETING_SUMMARY_PROMPT_INSTRUCTIONS,
    MEETING_SUMMARY_PROMPT_VERSION,
    MeetingSummaryPromptVersionError,
    render_meeting_summary_request_json,
)
from buzz.meeting.meeting_summary import (
    MeetingSummary,
    MeetingSummaryError,
    meeting_summary_from_json,
)
from buzz.meeting.meeting_summary_provenance import (
    MeetingSummaryTimestampProvenanceError,
    validate_meeting_summary_timestamp_provenance,
)
from buzz.meeting.summary_provider import (
    MeetingSummaryRequest,
    SummaryProviderConfigurationError,
    SummaryProviderRequestError,
    SummaryProviderResponseError,
    SummaryProviderTransportError,
    validate_summary_provider_result,
)

OPENAI_COMPATIBLE_SUMMARY_PROMPT_VERSION = MEETING_SUMMARY_PROMPT_VERSION
_INVALID_RESPONSE_JSON = object()
_INVALID_SUMMARY_CONTENT = object()


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProviderConfig:
    """Immutable connection configuration for an OpenAI-compatible API.

    ``timeout_seconds`` is the total network-operation budget after the
    transport child has successfully started. Forced process cleanup may follow
    deadline expiry.
    """

    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_base_url(self.base_url))
        _validate_untrimmed_text(self.model, "model")
        if self.api_key is not None:
            _validate_untrimmed_text(self.api_key, "api_key")
        timeout = self.timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise SummaryProviderConfigurationError(
                "timeout_seconds must be a finite positive number"
            )
        try:
            normalized_timeout = float(timeout)
        except (OverflowError, TypeError, ValueError) as exc:
            raise SummaryProviderConfigurationError(
                "timeout_seconds must be a finite positive number"
            ) from exc
        if not math.isfinite(normalized_timeout) or normalized_timeout <= 0:
            raise SummaryProviderConfigurationError(
                "timeout_seconds must be a finite positive number"
            )
        object.__setattr__(self, "timeout_seconds", normalized_timeout)


class OpenAICompatibleProvider:
    """Synchronous, single-attempt OpenAI-compatible summary provider."""

    def __init__(self, config: OpenAICompatibleProviderConfig) -> None:
        if not isinstance(config, OpenAICompatibleProviderConfig):
            raise SummaryProviderConfigurationError(
                "config must be OpenAICompatibleProviderConfig"
            )
        self._config = config
        self._transport = BoundedHttpTransport()

    @property
    def cleanup_required(self) -> bool:
        """Whether a prior transport child still requires bounded cleanup."""
        return self._transport.cleanup_required

    def shutdown(self) -> bool:
        """Retry bounded transport cleanup and report whether it completed."""
        return self._transport.shutdown()

    def summarize(self, request: MeetingSummaryRequest) -> MeetingSummary:
        try:
            rendered_request = render_meeting_summary_request_json(request)
        except MeetingSummaryPromptVersionError as exc:
            raise SummaryProviderRequestError(
                "Unsupported OpenAI-compatible summary prompt version"
            ) from exc

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._config.api_key is not None:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        body = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": MEETING_SUMMARY_PROMPT_INSTRUCTIONS},
                {"role": "user", "content": rendered_request},
            ],
        }
        endpoint = f"{self._config.base_url}/chat/completions"

        try:
            response = self._transport.post_json_with_deadline(
                endpoint,
                headers=headers,
                json_body=body,
                timeout_seconds=self._config.timeout_seconds,
                allow_redirects=False,
            )
        except BoundedHttpCleanupRequiredError as exc:
            raise SummaryProviderTransportError(
                "OpenAI-compatible summary transport cleanup is incomplete"
            ) from exc
        except BoundedHttpTimeoutError as exc:
            raise SummaryProviderTransportError(
                "OpenAI-compatible summary request timed out"
            ) from exc
        except BoundedHttpTransportError as exc:
            raise SummaryProviderTransportError(
                "OpenAI-compatible summary request failed before receiving "
                "an HTTP response"
            ) from exc
        except BoundedHttpResponseTooLargeError as exc:
            raise SummaryProviderResponseError(
                "OpenAI-compatible summary response exceeded the size limit"
            ) from exc

        if not 200 <= response.status_code < 300:
            raise SummaryProviderRequestError(
                "OpenAI-compatible summary request failed with HTTP status "
                f"{response.status_code}"
            )

        content = _extract_content(response.text)
        result = _parse_summary_content(content)
        if result is _INVALID_SUMMARY_CONTENT:
            raise SummaryProviderResponseError(
                "OpenAI-compatible summary response contained an invalid "
                "MeetingSummary"
            )

        result = validate_summary_provider_result(request, result)
        try:
            validate_meeting_summary_timestamp_provenance(request, result)
        except MeetingSummaryTimestampProvenanceError as exc:
            raise SummaryProviderResponseError(
                "OpenAI-compatible summary response used a timestamp outside "
                "the supplied transcript boundaries"
            ) from exc
        return result


def _validate_untrimmed_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise SummaryProviderConfigurationError(f"{name} must be str")
    if not value.strip():
        raise SummaryProviderConfigurationError(f"{name} must not be empty")
    if value != value.strip():
        raise SummaryProviderConfigurationError(
            f"{name} must not have leading or trailing whitespace"
        )
    return value


def _validate_base_url(value: object) -> str:
    base_url = _validate_untrimmed_text(value, "base_url")
    if "?" in base_url or "#" in base_url:
        raise SummaryProviderConfigurationError(
            "base_url must not contain a query or fragment marker"
        )
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise SummaryProviderConfigurationError("base_url is invalid") from exc
    if parsed.scheme not in {"http", "https"}:
        raise SummaryProviderConfigurationError("base_url scheme must be http or https")
    hostname = parsed.hostname
    if not hostname or any(char.isspace() for char in hostname):
        raise SummaryProviderConfigurationError("base_url must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise SummaryProviderConfigurationError(
            "base_url must not contain embedded credentials"
        )
    if port is None and parsed.netloc.endswith(":"):
        raise SummaryProviderConfigurationError("base_url contains an invalid port")

    normalized = base_url.rstrip("/")
    if urlsplit(normalized).path.endswith("/chat/completions"):
        raise SummaryProviderConfigurationError(
            "base_url must not include the chat completions endpoint"
        )
    return normalized


def _extract_content(response_text: str) -> str:
    envelope = _decode_response_json(response_text)
    if envelope is _INVALID_RESPONSE_JSON:
        raise SummaryProviderResponseError(
            "OpenAI-compatible summary response was not valid JSON"
        )
    if not isinstance(envelope, dict):
        raise SummaryProviderResponseError(
            "OpenAI-compatible summary response envelope was invalid"
        )
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SummaryProviderResponseError(
            "OpenAI-compatible summary response envelope was invalid"
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise SummaryProviderResponseError(
            "OpenAI-compatible summary response envelope was invalid"
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise SummaryProviderResponseError(
            "OpenAI-compatible summary response envelope was invalid"
        )
    content = message.get("content")
    if not isinstance(content, str):
        raise SummaryProviderResponseError(
            "OpenAI-compatible summary response envelope was invalid"
        )
    return content


def _decode_response_json(response_text: str) -> object:
    try:
        return json.loads(response_text)
    except (json.JSONDecodeError, TypeError):
        return _INVALID_RESPONSE_JSON


def _parse_summary_content(content: str) -> MeetingSummary | object:
    try:
        return meeting_summary_from_json(content)
    except MeetingSummaryError:
        return _INVALID_SUMMARY_CONTENT


__all__ = [
    "OPENAI_COMPATIBLE_SUMMARY_PROMPT_VERSION",
    "OpenAICompatibleProvider",
    "OpenAICompatibleProviderConfig",
]
