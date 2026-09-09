"""Process-isolated HTTP transport with bounded post-start lifetime."""

from __future__ import annotations

import multiprocessing
import json
import os
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_RESULT_BYTES = (6 * MAX_RESPONSE_BYTES) + 1024
_READ_CHUNK_BYTES = 64 * 1024
_TERMINATE_GRACE_SECONDS = 1.0
_KILL_GRACE_SECONDS = 1.0


class BoundedHttpTimeoutError(Exception):
    """The operation exceeded its post-start wall-clock budget."""


class BoundedHttpTransportError(Exception):
    """The isolated transport failed without a usable HTTP response."""


class BoundedHttpResponseTooLargeError(Exception):
    """A successful response exceeded the deterministic byte limit."""


class BoundedHttpCleanupRequiredError(BoundedHttpTransportError):
    """The previous child remains owned and requires another cleanup attempt."""


@dataclass(frozen=True, slots=True)
class BoundedHttpResponse:
    status_code: int
    text: str


@dataclass(slots=True)
class _OwnedTransport:
    process: multiprocessing.Process | None
    request_path: Path | None
    result_path: Path | None


class BoundedHttpTransport:
    """Own at most one spawned HTTP child and all of its temporary resources."""

    def __init__(self) -> None:
        self._owned: _OwnedTransport | None = None

    @property
    def cleanup_required(self) -> bool:
        """Whether resources from a prior call still require cleanup."""
        return self._owned is not None

    def post_json_with_deadline(
        self,
        endpoint: str,
        *,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any],
        timeout_seconds: float,
        allow_redirects: bool,
    ) -> BoundedHttpResponse:
        """Run one POST within a deadline that starts after child startup."""
        if self._owned is not None:
            raise BoundedHttpCleanupRequiredError

        try:
            request_path, result_path = _create_transport_files(
                {
                    "endpoint": endpoint,
                    "headers": dict(headers),
                    "json_body": dict(json_body),
                    "timeout_seconds": timeout_seconds,
                    "allow_redirects": allow_redirects,
                }
            )
        except (OSError, TypeError, ValueError):
            raise BoundedHttpTransportError from None
        owned = _OwnedTransport(None, request_path, result_path)
        self._owned = owned
        try:
            context = multiprocessing.get_context("spawn")
            start_gate = context.Event()
            process = context.Process(
                target=_post_json_child,
                args=(start_gate, str(request_path), str(result_path)),
                name="buzz-meeting-summary-http",
            )
        except BaseException as exc:
            cleanup_complete = self.shutdown()
            if not cleanup_complete:
                raise BoundedHttpCleanupRequiredError from None
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise BoundedHttpTransportError from None
        owned.process = process

        try:
            process.start()
        except BaseException as exc:
            cleanup_complete = self.shutdown()
            if not cleanup_complete:
                raise BoundedHttpCleanupRequiredError from None
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise BoundedHttpTransportError from None

        deadline = time.monotonic() + timeout_seconds

        try:
            start_gate.set()
            process.join(_remaining_seconds(deadline))
            if process.is_alive():
                cleanup_complete = self.shutdown()
                if not cleanup_complete:
                    raise BoundedHttpCleanupRequiredError
                raise BoundedHttpTimeoutError

            if time.monotonic() >= deadline:
                if not self.shutdown():
                    raise BoundedHttpCleanupRequiredError
                raise BoundedHttpTimeoutError

            message = _read_completed_result(result_path)
            if time.monotonic() >= deadline:
                if not self.shutdown():
                    raise BoundedHttpCleanupRequiredError
                raise BoundedHttpTimeoutError

            if not self.shutdown():
                raise BoundedHttpCleanupRequiredError
        except BoundedHttpCleanupRequiredError:
            raise
        except BaseException as exc:
            cleanup_complete = self.shutdown()
            if not cleanup_complete:
                raise BoundedHttpCleanupRequiredError from None
            if isinstance(
                exc,
                (
                    BoundedHttpResponseTooLargeError,
                    BoundedHttpTimeoutError,
                    BoundedHttpTransportError,
                ),
            ):
                raise
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise BoundedHttpTransportError from None

        kind = message[0]
        if kind == "response":
            return BoundedHttpResponse(status_code=message[1], text=message[2])
        if kind == "timeout":
            raise BoundedHttpTimeoutError
        if kind == "too_large":
            raise BoundedHttpResponseTooLargeError
        raise BoundedHttpTransportError

    def shutdown(self) -> bool:
        """Retry bounded cleanup, retaining ownership until it fully succeeds."""
        owned = self._owned
        if owned is None:
            return True

        process = owned.process
        if process is not None:
            if not _stop_and_reap(process):
                return False
            try:
                process.close()
            except (OSError, ValueError):
                return False
            owned.process = None

        for attribute in ("request_path", "result_path"):
            path = getattr(owned, attribute)
            if path is None:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                return False
            setattr(owned, attribute, None)

        self._owned = None
        return True


def _create_transport_files(payload: dict[str, object]) -> tuple[Path, Path]:
    request_descriptor: int | None = None
    result_descriptor: int | None = None
    request_path: Path | None = None
    result_path: Path | None = None
    try:
        request_descriptor, request_name = tempfile.mkstemp(
            prefix="buzz-summary-request-", suffix=".bin"
        )
        request_path = Path(request_name)
        result_descriptor, result_name = tempfile.mkstemp(
            prefix="buzz-summary-result-", suffix=".bin"
        )
        result_path = Path(result_name)
        with os.fdopen(
            request_descriptor, "w", encoding="utf-8", newline="\n"
        ) as request_file:
            json.dump(payload, request_file, ensure_ascii=False, separators=(",", ":"))
        request_descriptor = None
        os.close(result_descriptor)
        result_descriptor = None
    except BaseException:
        for descriptor in (request_descriptor, result_descriptor):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        for path in (request_path, result_path):
            if path is not None:
                path.unlink(missing_ok=True)
        raise
    assert request_path is not None
    assert result_path is not None
    return request_path, result_path


def _remaining_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _stop_and_reap(process: multiprocessing.Process) -> bool:
    """Attempt finite terminate/kill escalation and confirm child exit."""
    try:
        pid = process.pid
    except (OSError, RuntimeError, ValueError):
        return False
    if pid is None:
        return True

    alive = _process_is_alive(process)
    if alive is None:
        return False
    if alive:
        try:
            process.terminate()
        except (OSError, RuntimeError, ValueError):
            pass
        _timed_process_join(process, _TERMINATE_GRACE_SECONDS)

    alive = _process_is_alive(process)
    if alive is None:
        return False
    if alive:
        try:
            process.kill()
        except (OSError, RuntimeError, ValueError):
            pass
        _timed_process_join(process, _KILL_GRACE_SECONDS)

    alive = _process_is_alive(process)
    return alive is False


def _process_is_alive(process: multiprocessing.Process) -> bool | None:
    try:
        return process.is_alive()
    except (OSError, RuntimeError, ValueError):
        return None


def _timed_process_join(process: multiprocessing.Process, timeout: float) -> None:
    try:
        process.join(timeout)
    except (OSError, RuntimeError, ValueError):
        pass


def _read_completed_result(result_path: Path) -> tuple[str, int, str] | tuple[str]:
    try:
        with result_path.open("rb") as result_file:
            serialized = result_file.read(_MAX_RESULT_BYTES + 1)
    except OSError as exc:
        raise BoundedHttpTransportError from exc
    if len(serialized) > _MAX_RESULT_BYTES:
        raise BoundedHttpTransportError
    try:
        decoded = json.loads(serialized)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundedHttpTransportError from exc
    if not isinstance(decoded, dict) or set(decoded) - {"kind", "status_code", "text"}:
        raise BoundedHttpTransportError
    kind = decoded.get("kind")
    if kind == "response":
        if (
            set(decoded) != {"kind", "status_code", "text"}
            or isinstance(decoded["status_code"], bool)
            or not isinstance(decoded["status_code"], int)
            or not isinstance(decoded["text"], str)
        ):
            raise BoundedHttpTransportError
        return kind, decoded["status_code"], decoded["text"]
    if set(decoded) != {"kind"} or kind not in {"timeout", "transport", "too_large"}:
        raise BoundedHttpTransportError
    return (kind,)


def _write_child_result(result_path: str, message: tuple[object, ...]) -> None:
    payload: dict[str, object] = {"kind": message[0]}
    if message[0] == "response":
        payload.update(status_code=message[1], text=message[2])
    with open(result_path, "w", encoding="utf-8", newline="\n") as result_file:
        json.dump(payload, result_file, ensure_ascii=False, separators=(",", ":"))


def _retain_response_chunk(retained: bytearray, chunk: bytes) -> bool:
    """Append a successful-response chunk only when it fits the byte limit."""
    if len(chunk) > MAX_RESPONSE_BYTES - len(retained):
        return False
    retained.extend(chunk)
    return True


def _post_json_child(start_gate: Any, request_path: str, result_path: str) -> None:
    """Execute and fully consume one request inside the disposable process."""
    response: requests.Response | None = None
    message: tuple[object, ...] = ("transport",)
    try:
        start_gate.wait()
        with open(request_path, encoding="utf-8") as request_file:
            payload = json.load(request_file)
        endpoint = payload["endpoint"]
        headers = payload["headers"]
        json_body = payload["json_body"]
        timeout_seconds = payload["timeout_seconds"]
        allow_redirects = payload["allow_redirects"]
        response = requests.post(
            endpoint,
            headers=headers,
            json=json_body,
            timeout=timeout_seconds,
            allow_redirects=allow_redirects,
            stream=True,
        )
        if not 200 <= response.status_code < 300:
            message = ("response", response.status_code, "")
        else:
            content = bytearray()
            for chunk in response.iter_content(chunk_size=_READ_CHUNK_BYTES):
                if not chunk:
                    continue
                if not _retain_response_chunk(content, chunk):
                    message = ("too_large",)
                    break
            else:
                response._content = bytes(content)
                message = ("response", response.status_code, response.text)
    except requests.Timeout:
        message = ("timeout",)
    except Exception:
        message = ("transport",)
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                message = ("transport",)
        try:
            _write_child_result(result_path, message)
        except Exception:
            pass


__all__ = [
    "BoundedHttpCleanupRequiredError",
    "BoundedHttpResponse",
    "BoundedHttpResponseTooLargeError",
    "BoundedHttpTimeoutError",
    "BoundedHttpTransport",
    "BoundedHttpTransportError",
    "MAX_RESPONSE_BYTES",
]
