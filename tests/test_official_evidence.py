"""All payloads in this module are synthetic; never real source evidence."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jc.research import official_evidence as intake
from jc.research.providers.inspection import inspect_odds_history_payload, inspect_sporttery_history_payload

T = datetime(2026, 9, 29, tzinfo=UTC)
URL = "https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry"


def save_input(tmp_path, body, *, url=URL, encoding="utf-8"):
    path = tmp_path / "sporttery.json"
    path.write_bytes(body.encode(encoding))
    return intake.intake_official_evidence(path, url, T, tmp_path / "artifacts")


def test_offline_json_original_bytes_provenance_and_missing_fields(tmp_path):
    body = ' { "errorCode":0, "value":{"matchResult":[{"matchId": "SYNTHETIC-ID", "matchDate":"2026-09-26"}]}}\r\n'
    result = save_input(tmp_path, body)
    raw = json.loads(Path(result["raw_path"]).read_text("utf-8"))["raw"]
    assert raw["payload"].encode(raw["metadata"]["text_encoding"]) == body.encode()
    assert raw["external_ref"] == URL and raw["retrieved_at"] == T.isoformat()
    assert result["response_sha256"] == hashlib.sha256(body.encode()).hexdigest()
    observed = result["inspection"]["OBSERVED_IN_REAL_RESPONSE"]
    assert observed["top_level_fields"] == ["errorCode", "value"]
    assert observed["matches"][0]["fields"] == {"matchId": "SYNTHETIC-ID", "matchDate": "2026-09-26"}
    assert "homeTeamId" in observed["matches"][0]["missing"]
    assert result["inspection"]["sale_date_status"] == "SALE_DATE_UNVERIFIED"
    assert result["inspection"]["verified_targets"] == []
    assert result["sporttery_verification_status"] == "UNVERIFIED"


def test_offline_html_kept_for_review_without_inventing_matches(tmp_path):
    body = "<html><title>官方赛果</title><table><tr><td>合成测试</td></tr></table></html>"
    result = save_input(tmp_path, body, encoding="gb18030")
    assert result["schema_status"] == "HTML_REVIEW_REQUIRED"
    assert result["inspection"]["match_count"] == 0
    assert result["inspection"]["verified_targets"] == []
    raw = json.loads(Path(result["raw_path"]).read_text("utf-8"))["raw"]
    assert raw["payload"].encode("gb18030") == body.encode("gb18030")


@pytest.mark.parametrize(
    "body",
    [
        '<html><title>安全验证</title><script type="application/json">{"matchId": "FAKE"}</script></html>',
        "<html>WAF captcha challenge</html>",
        "<html><title>Login</title></html>",
        "<html><title>Error 500</title></html>",
        "",
        "   ",
        '{"errorCode":567,"value":{"matchId":"FAKE"}}',
    ],
)
def test_waf_login_error_and_empty_are_invalid_evidence(tmp_path, body):
    result = save_input(tmp_path, body)
    assert result["schema_status"] == "INVALID_EVIDENCE"
    assert result["status"] == "BLOCKED"
    assert result["inspection"]["match_count"] == 0
    assert result["inspection"]["verified_targets"] == []


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/sporttery.json",
        "https://sporttery.cn.example.com/history",
        "http://sporttery.cn/history",
        "https://user:password@www.sporttery.cn/history",
        "https://sporttery.cn/history?apiKey=PRIVATE",
        "https://sporttery.cn/history?key=PRIVATE",
        "https://sporttery.cn/history?token=PRIVATE",
        "https://sporttery.cn:8080/history",
        "https://sporttery.cn/history#PRIVATE",
        "https://evil@sporttery.cn/history",
        "https://lottery.gov.cn.example.com/history",
        "https://www.lottery.gov.cn@evil.example/history",
        "http://www.lottery.gov.cn/jc/zqsgkj/",
        "https://unreviewed.lottery.gov.cn/history",
        "https://appgw.sporttery.cn/history",
    ],
)
def test_untrusted_domain_http_and_credential_urls_rejected_before_raw(tmp_path, url):
    with pytest.raises(ValueError):
        save_input(tmp_path, "{}", url=url)
    assert not (tmp_path / "artifacts").exists()


@pytest.mark.parametrize("host", sorted(intake.OFFICIAL_HOSTS))
def test_https_official_allowlist_is_not_automatic_verification(tmp_path, host):
    result = save_input(tmp_path, "{}", url=f"https://{host}/history")
    assert result["sporttery_verification_status"] == "UNVERIFIED"


@pytest.mark.parametrize("host", ["lottery.gov.cn", "www.lottery.gov.cn"])
@pytest.mark.parametrize("body", [
    "<html><title>足球赛果开奖</title><table><tr><th>全场比分（90分钟）</th></tr></table></html>",
    "<html><title>足球对阵详情</title><th>发布时间</th><td>{{obj.updateTime}}</td></html>",
    '{"errorCode":0,"value":{"matchResult":[{"matchId":"SYNTHETIC",'
    '"matchNumStr":"周三001","matchDate":"2026-09-30"}]}}',
    '{"errorCode":0,"value":{"oddsHistory":{"hadList":[{"updateDate":"2026-09-30",'
    '"updateTime":"11:02:17","h":"2.10","d":"3.20","a":"3.40"}]}}}',
    "<html><title>访问验证</title>captcha</html>",
])
def test_lottery_page_or_expected_fields_cannot_certify_target_or_time(tmp_path, host, body):
    # Synthetic boundary examples, NOT captured successful provider responses.
    result = save_input(tmp_path, body, url=f"https://{host}/jc/zqsgkj/")
    assert result["sporttery_verification_status"] == "UNVERIFIED"
    assert result["inspection"]["verified_targets"] == []
    assert result["inspection"]["replay_available_at"] is None
    assert result["inspection"]["availability_basis"] is None
    raw = json.loads(Path(result["raw_path"]).read_text("utf-8"))["raw"]
    assert raw["payload"] == body
    assert raw["metadata"]["response_sha256"] == hashlib.sha256(body.encode()).hexdigest()


def test_lottery_qualification_manifest_keeps_official_source_unverified():
    from jc.research.probe_manifest import manifest_counts

    saved = json.loads(Path("docs/lottery-official-probe-manifest.json").read_text("utf-8"))
    source = saved["source_registration"]
    assert source["source"]["source_type"] == "OFFICIAL_SPORTTERY_HISTORY"
    assert source["provider_name"] == "sporttery"
    assert source["verification_status"] == "UNVERIFIED"
    assert {r["source"] for r in saved["records"]} == {source["source"]["source_name"]}
    assert manifest_counts(saved)["accepted_source_count"] == 0
    assert all(r["evidence_decision"] != "ACCEPTED" for r in saved["records"])


@pytest.mark.parametrize(
    "body",
    [
        '{"apiKey":"PRIVATE"}',
        '{"client_secret_value":"PRIVATE"}',
        "<html>Cookie: PRIVATE</html>",
        r'{"\u0061piKey":"PRIVATE"}',
        "<html>apiKey&#61;PRIVATE</html>",
        '{"log":{"entries":[{"request":{"headers":[{"name":"Cookie","value":"PRIVATE"}]}}]}}',
    ],
)
def test_secret_scan_and_whole_har_rejection_precede_copy(tmp_path, body):
    with pytest.raises(ValueError):
        save_input(tmp_path, body)
    assert not (tmp_path / "artifacts").exists()


def test_explicit_single_har_body_is_ordinary_response_input(tmp_path):
    result = save_input(tmp_path, '{"errorCode":0,"value":{"matchResult":[]}}')
    assert result["schema_status"] == "JSON_OBSERVED_REVIEW_REQUIRED"
    assert result["inspection"]["match_count"] == 0


def test_offline_url_preserves_blank_query_and_original_provenance(tmp_path):
    from jc.research.probe_manifest import build_probe_manifest

    result = save_input(tmp_path, "{}", url=URL + "?leagueId=&label=a%20b")
    raw = json.loads(Path(result["raw_path"]).read_text("utf-8"))["raw"]
    assert raw["metadata"]["provided_source_url"] == URL + "?leagueId=&label=a%20b"
    manifest = build_probe_manifest([result["probe_path"]], root=tmp_path)
    assert manifest["records"][0]["public_url"].endswith("?leagueId=&label=a+b")


def test_raw_first_and_disk_failure_never_inspects(tmp_path, monkeypatch):
    calls = []
    inspect = intake.inspect_sporttery_history_payload

    def after_save(body):
        raw_files = list((tmp_path / "artifacts").glob("*.json"))
        assert len(raw_files) == 1
        assert json.loads(raw_files[0].read_text("utf-8"))["raw"]["payload"] == body
        calls.append("inspect")
        return inspect(body)

    monkeypatch.setattr(intake, "inspect_sporttery_history_payload", after_save)
    save_input(tmp_path, "{}")
    assert calls == ["inspect"]

    def fail(*args):
        raise OSError("synthetic full disk")

    monkeypatch.setattr(intake, "_save", fail)
    with pytest.raises(OSError):
        save_input(tmp_path, "{}")
    assert calls == ["inspect"]


def test_expected_and_observed_are_separate():
    report = inspect_sporttery_history_payload('{"unknownRealField":42}')
    assert "homeTeamId" in report["EXPECTED_FROM_JS"]["results"]
    assert report["OBSERVED_IN_REAL_RESPONSE"]["top_level_fields"] == ["unknownRealField"]
    assert report["OBSERVED_IN_REAL_RESPONSE"]["matches"] == []
    assert report["verified_targets"] == []


@pytest.mark.parametrize(
    "fields",
    [
        {"updateDate": "2026-09-26"},
        {"updateTime": "12:30:00"},
        {"updateDate": "2026-09-26", "updateTime": "12:30:00"},
        {},
    ],
)
def test_official_odds_original_times_never_imply_replay_semantics(fields):
    report = inspect_sporttery_history_payload(
        json.dumps({"errorCode": 0, "value": {"oddsHistory": [fields]}})
    )
    stamps = report["OBSERVED_IN_REAL_RESPONSE"]["timestamps"]
    if fields:
        assert {k: stamps[0][k] for k in ("updateDate", "updateTime")} == {
            "updateDate": fields.get("updateDate"),
            "updateTime": fields.get("updateTime"),
        }
    else:
        assert stamps == []
    assert report["timestamp_status"] == "TIMESTAMP_SEMANTICS_UNVERIFIED"
    assert report["replay_available_at"] is report["availability_basis"] is None


def test_historical_envelope_uses_actual_snapshot_not_request_time():
    envelope = {
        "timestamp": "2026-09-26T12:00:00Z",
        "previous_timestamp": "2026-09-26T11:55:00Z",
        "next_timestamp": "2026-09-26T12:05:00Z",
        "data": [{"id": "SYNTHETIC"}],
    }
    result = inspect_odds_history_payload(
        json.dumps(envelope),
        requested_at=datetime(2026, 9, 26, 12, 3, tzinfo=UTC),
        retrieved_at=T,
    )
    assert result["schema_status"] == "HISTORICAL_ENVELOPE_OBSERVED"
    assert result["timestamp"] == envelope["timestamp"]
    assert result["previous_timestamp"] == envelope["previous_timestamp"]
    assert result["next_timestamp"] == envelope["next_timestamp"]
    assert result["replay_available_at"] == "2026-09-26T12:00:00+00:00"
    assert result["availability_basis"] == "SOURCE_SNAPSHOT_AT"
    assert result["evidence_decision"] != "ACCEPTED"


@pytest.mark.parametrize(
    "envelope",
    [
        {"data": []},
        {"data": [], "last_update": "2026-09-26T12:00:00Z"},
        {"data": [], "timestamp": "2026-09-26T12:00:00"},
        {"data": {}, "timestamp": "2026-09-26T12:00:00Z"},
        {"data": [], "timestamp": "closing"},
        {"data": [], "timestamp": "opening"},
        {"data": [], "timestamp": "2026-09-26T12:00:00Z", "previous_timestamp": "2026-09-27T12:00:00Z"},
    ],
)
def test_missing_or_invalid_envelope_timestamp_cannot_generate_replay(envelope):
    result = inspect_odds_history_payload(json.dumps(envelope))
    assert result["replay_available_at"] is result["availability_basis"] is None


def test_snapshot_after_request_or_retrieval_is_rejected():
    body = json.dumps({"timestamp": T.isoformat(), "data": []})
    for kw in ({"requested_at": T - timedelta(seconds=1)}, {"retrieved_at": T - timedelta(seconds=1)}):
        assert inspect_odds_history_payload(body, **kw)["replay_available_at"] is None
