"""Synthetic HTTP responses test mechanics only; none are real provider fixtures."""

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from jc.research.contracts import content_hash, reject_secrets
from jc.research.providers import probe


@pytest.mark.parametrize("status", [200, 401, 403, 429, 567])
def test_raw_first_even_for_failure_or_malformed_response(tmp_path, monkeypatch, status):
    calls = []
    body = b"<html>SYNTHETIC transport response, not actual source evidence</html>"

    def respond(request):
        calls.append(request)
        return httpx.Response(status, content=body, headers={"content-type": "text/html"})

    def parse_after_persistence(text):
        saved = list(tmp_path.glob("*.json"))
        assert len(saved) == 1
        assert json.loads(saved[0].read_text("utf-8"))["raw"]["payload"] == text
        return json.loads(text)

    monkeypatch.setattr(probe, "json", SimpleNamespace(loads=parse_after_persistence))
    result = probe.probe_source(
        tmp_path, "synthetic", "https://example.test/history", transport=httpx.MockTransport(respond)
    )
    assert len(calls) == 1
    assert result["response_sha256"] == hashlib.sha256(body).hexdigest()
    assert result["raw_content_hash"] == content_hash(body.decode())
    assert result["status"] == ("FETCHED" if status == 200 else "BLOCKED")
    assert result["sporttery_verification_status"] == "UNVERIFIED"
    raw = json.loads(Path(result["raw_path"]).read_text("utf-8"))["raw"]
    assert raw["metadata"]["replay_available_at"] is None
    assert raw["metadata"]["availability_basis"] is None


def test_credentials_and_request_headers_never_persist(tmp_path):
    credential = "SYNTHETIC-private-value/42"
    body = json.dumps({"echo": credential, "Authorization": "Bearer test-value", "Cookie": "session=value"})
    result = probe.probe_source(
        tmp_path,
        "synthetic",
        "https://example.test/history?date=2026-09-26",
        params={"apiKey": credential, "date": "2026-09-26"},
        transport=httpx.MockTransport(lambda request: httpx.Response(401, text=body)),
    )
    for file in tmp_path.glob("*.json"):
        text = file.read_text("utf-8")
        assert credential not in text
        assert "test-value" not in text
        assert "session=value" not in text
        assert "apiKey" not in text
        reject_secrets(json.loads(text))
    assert "date=2026-09-26" in result["url"]
    assert result["retention"] == "REDACTED"


def test_d2a_guard_withholds_unrecognized_credential_text(tmp_path):
    result = probe.probe_source(
        tmp_path,
        "synthetic",
        "https://example.test/history",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="Bearer synthetic-value")),
    )
    assert result["status"] == "BLOCKED"
    assert result["retention"] == "WITHHELD"
    assert all("synthetic-value" not in f.read_text("utf-8") for f in tmp_path.glob("*.json"))


def test_network_requires_explicit_switch_even_with_real_transport(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_NETWORK_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="RESEARCH_NETWORK_ENABLED"):
        probe.probe_source(
            tmp_path, "synthetic", "https://example.test/history", transport=httpx.HTTPTransport()
        )
    assert not list(tmp_path.iterdir())


def test_storage_failure_does_not_decode_response(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("synthetic disk failure")

    def no_parse(*args):
        pytest.fail("Normalization attempted before successful persistence")

    monkeypatch.setattr(probe, "_save", fail)
    monkeypatch.setattr(probe, "json", SimpleNamespace(loads=no_parse))
    with pytest.raises(OSError, match="disk failure"):
        probe.probe_source(
            tmp_path,
            "synthetic",
            "https://example.test/history",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        )


def test_timeout_keeps_safe_probe_without_inventing_response_hash(tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout("URL with apiKey=SYNTHETIC-SECRET", request=request)

    result = probe.probe_source(
        tmp_path, "synthetic", "https://example.test/history", transport=httpx.MockTransport(timeout)
    )
    assert result["http_status"] is None
    assert result["response_sha256"] is None
    assert result["raw_content_hash"] is None
    assert result["reason"] == "ReadTimeout"
    assert "SYNTHETIC-SECRET" not in Path(result["probe_path"]).read_text("utf-8")


def test_unicode_and_append_only_probes(tmp_path):
    body = "合成中文脚本，仅供测试".encode("gb18030")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    first = probe.probe_source(tmp_path, "synthetic", "https://example.test/history", transport=transport)
    second = probe.probe_source(tmp_path, "synthetic", "https://example.test/history", transport=transport)
    assert first["raw_path"] != second["raw_path"]
    raw = json.loads(Path(first["raw_path"]).read_text("utf-8"))["raw"]
    assert raw["payload"].encode(raw["metadata"]["text_encoding"]) == body


def test_redirect_is_preserved_but_never_followed(tmp_path):
    calls = []

    def redirect(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "/login?token=synthetic-private"})

    result = probe.probe_source(
        tmp_path, "synthetic", "https://example.test/history", transport=httpx.MockTransport(redirect)
    )
    assert len(calls) == 1
    raw = json.loads(Path(result["raw_path"]).read_text("utf-8"))["raw"]
    assert raw["metadata"]["redirect_location"] == "https://example.test/login"


@pytest.mark.network
@pytest.mark.skipif(os.getenv("RESEARCH_NETWORK_ENABLED") != "1", reason="Explicit network opt-in required")
def test_real_history_probe_opt_in(tmp_path):
    from jc.research.pilot import SPORTTERY_HISTORY

    result = probe.probe_source(
        tmp_path,
        "sporttery_history",
        SPORTTERY_HISTORY,
        params={
            "matchBeginDate": "2026-09-26",
            "matchEndDate": "2026-09-28",
            "pageSize": "30",
            "pageNo": "1",
            "isFix": "0",
            "matchPage": "1",
            "pcOrWap": "1",
        },
    )
    assert Path(result["probe_path"]).exists()
    assert result["sporttery_verification_status"] == "UNVERIFIED"
