from datetime import UTC, datetime

import httpx
import pytest

from unf_bridge.remote_errors import classify_remote_error, guarded_remote_cli, parse_retry_after


def status_error(status: int, *, retry_after: str | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.invalid/safe")
    headers = {"Retry-After": retry_after} if retry_after is not None else None
    response = httpx.Response(status, request=request, headers=headers)
    return httpx.HTTPStatusError("remote", request=request, response=response)


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 599])
def test_retryable_http_statuses_use_temp_failure_exit(status):
    failure = classify_remote_error(status_error(status, retry_after="120"))
    assert failure.retryable is True
    assert failure.exit_code == 75
    assert failure.retry_after_seconds == 120


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_manual_http_statuses_are_not_retried_automatically(status):
    failure = classify_remote_error(status_error(status))
    assert failure.retryable is False
    assert failure.exit_code == 2
    assert failure.retry_after_seconds is None


def test_transport_error_is_retryable_without_leaking_url():
    request = httpx.Request("GET", "https://secret.example/path?token=do-not-print")
    failure = classify_remote_error(httpx.ConnectError("connect failed", request=request))
    assert failure.retryable is True
    assert failure.exit_code == 75
    assert "secret.example" not in failure.message
    assert "do-not-print" not in failure.message


def test_retry_after_http_date_is_supported():
    now = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)
    assert parse_retry_after("Fri, 04 Sep 2026 10:01:30 GMT", now=now) == 90
    assert parse_retry_after("invalid", now=now) is None


def test_guarded_cli_converts_http_429_to_exit_75(capsys):
    @guarded_remote_cli
    def command():
        raise status_error(429, retry_after="15")

    with pytest.raises(SystemExit) as exc:
        command()
    assert exc.value.code == 75
    stderr = capsys.readouterr().err
    assert "HTTP 429" in stderr
    assert "Retry-After=15s" in stderr


def test_guarded_cli_converts_local_mapping_error_to_exit_2(capsys):
    @guarded_remote_cli
    def command():
        raise ValueError("Schema lock УНФ не совпадает")

    with pytest.raises(SystemExit) as exc:
        command()
    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert "CONFIG_ERROR" in stderr
    assert "Schema lock УНФ" in stderr
