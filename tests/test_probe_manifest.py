"""Synthetic local artifacts exercise the Git-safe manifest boundary."""

import json
from pathlib import Path

import httpx
import pytest
from jc.research.contracts import canonical_bytes, reject_secrets
from jc.research.probe_manifest import blocked_report_section, build_probe_manifest, manifest_counts
from jc.research.providers.probe import probe_source, record_blocked


def probe(
    root, source="synthetic", body="PRIVATE-BODY-NOT-FOR-GIT", status=200, url="https://example.test/history"
):
    return probe_source(
        root / "artifacts" / "probes",
        source,
        url,
        transport=httpx.MockTransport(lambda request: httpx.Response(status, text=body)),
    )


def test_manifest_allowlist_no_body_credentials_or_absolute_path(tmp_path):
    result = probe(tmp_path, body='{"apiKey":"SYNTHETIC-PRIVATE", "message":"BODY-CANARY"}')
    manifest = build_probe_manifest([result["probe_path"]], root=tmp_path)
    record = manifest["records"][0]
    assert set(record) == {
        "source",
        "public_url",
        "probe_utc",
        "http_status",
        "response_sha256",
        "canonical_sanitized_raw_hash",
        "retention",
        "schema_status",
        "secret_scan",
        "local_artifact_relative_path",
        "evidence_decision",
    }
    text = json.dumps(manifest)
    assert "BODY-CANARY" not in text and "SYNTHETIC-PRIVATE" not in text
    assert str(tmp_path) not in text
    assert record["secret_scan"] == "PASS"
    assert record["retention"] == "REDACTED"
    assert record["evidence_decision"] == "BLOCKED"
    reject_secrets({k: v for k, v in record.items() if k != "secret_scan"})


def test_stable_sort_deduplication_and_no_double_count_of_aggregate_report(tmp_path):
    b = probe(tmp_path, "b")
    a = probe(tmp_path, "a")
    aggregate = tmp_path / "artifacts" / "report.json"
    aggregate.write_text(json.dumps({"probes": [a, b]}), "utf-8")
    first = build_probe_manifest(
        [b["probe_path"], aggregate, a["probe_path"], a["probe_path"]], root=tmp_path
    )
    second = build_probe_manifest([a["probe_path"], b["probe_path"]], root=tmp_path)
    assert canonical_bytes(first) == canonical_bytes(second)
    assert [r["source"] for r in first["records"]] == ["a", "b"]
    assert manifest_counts(first)["response_raw_count"] == 2


def test_missing_credential_has_no_invented_response_or_http(tmp_path):
    result = record_blocked(
        tmp_path / "artifacts", "synthetic", "https://example.test", "BLOCKED_MISSING_CREDENTIAL"
    )
    record = build_probe_manifest([result["probe_path"]], root=tmp_path)["records"][0]
    assert (
        record["http_status"] is record["response_sha256"] is record["canonical_sanitized_raw_hash"] is None
    )
    assert record["retention"] == record["schema_status"] == "NO_RESPONSE"


def test_legacy_raw_without_encoding_is_explicitly_unverified(tmp_path):
    result = probe(tmp_path)
    path = Path(result["raw_path"])
    doc = json.loads(path.read_text("utf-8"))
    del doc["raw"]["metadata"]["text_encoding"]
    path.write_text(json.dumps(doc), "utf-8")
    record = build_probe_manifest([result["probe_path"]], root=tmp_path)["records"][0]
    assert record["schema_status"] == "LEGACY_BYTE_ENCODING_UNVERIFIED"
    assert record["evidence_decision"] == "UNVERIFIED"


@pytest.mark.parametrize("mutation", ["body", "response_hash", "source", "http", "timestamp", "url"])
def test_manifest_rejects_summary_raw_disagreement(tmp_path, mutation):
    result = probe(tmp_path)
    path = Path(result["probe_path"])
    doc = json.loads(path.read_text("utf-8"))
    summary = doc["source_probe"]
    if mutation == "body":
        raw_path = Path(result["raw_path"])
        raw = json.loads(raw_path.read_text("utf-8"))
        raw["raw"]["payload"] = "CHANGED"
        raw_path.write_text(json.dumps(raw), "utf-8")
    else:
        key, value = {
            "response_hash": ("response_sha256", "0" * 64),
            "source": ("source", "wrong"),
            "http": ("http_status", 201),
            "timestamp": ("timestamp", "2000-01-01T00:00:00Z"),
            "url": ("url", "https://example.test/different"),
        }[mutation]
        summary[key] = value
        path.write_text(json.dumps(doc), "utf-8")
    with pytest.raises(ValueError, match="disagrees"):
        build_probe_manifest([path], root=tmp_path)


def test_manifest_fails_closed_for_secret_url_and_path_escape(tmp_path):
    result = probe(tmp_path)
    path = Path(result["probe_path"])
    doc = json.loads(path.read_text("utf-8"))
    doc["source_probe"]["url"] += "?key=PRIVATE"
    path.write_text(json.dumps(doc), "utf-8")
    with pytest.raises(ValueError):
        build_probe_manifest([path], root=tmp_path)
    with pytest.raises(ValueError):
        build_probe_manifest([path], root=tmp_path / "elsewhere")


def test_js_expected_schema_not_observed_json_and_waf_never_data(tmp_path):
    js = probe(tmp_path, "js", '{"matchId":"FAKE"}', url="https://static.sporttery.cn/history.js")
    waf = probe(
        tmp_path, "waf", "<html>captcha</html>", status=567, url="https://webapi.sporttery.cn/history"
    )
    records = build_probe_manifest([js["probe_path"], waf["probe_path"]], root=tmp_path)["records"]
    assert [r["schema_status"] for r in records] == ["EXPECTED_FROM_JS", "INVALID_EVIDENCE"]
    assert all(r["evidence_decision"] != "ACCEPTED" for r in records)


def test_do_not_publish_blocked_no_data_report_over_observed_json(tmp_path):
    result = probe(
        tmp_path, body='{"errorCode":0,"value":{"matchResult":[]}}', url="https://webapi.sporttery.cn/history"
    )
    manifest = build_probe_manifest([result["probe_path"]], root=tmp_path)
    with pytest.raises(ValueError, match="requires evidence review"):
        blocked_report_section(manifest)


def test_empty_manifest_cannot_claim_a_pilot_attempt():
    with pytest.raises(ValueError, match="official probe"):
        blocked_report_section({"records": []})


@pytest.mark.parametrize("has_time", [True, False])
def test_sina_observed_history_is_not_accepted_or_replay_qualified(tmp_path, has_time):
    row = {"o1": "1.2", "o2": "5.5", "o3": "12"}
    if has_time:
        row["oddsTime"] = "1790577999"
    result = probe(
        tmp_path,
        body=json.dumps({"result": {"status": {"code": 0, "msg": "success"}, "data": [row]}}),
        url="https://alpha.lottery.sina.com.cn/gateway/index/entry"
        "?cat1=footballMatchOddsEuroChange&matchId=synthetic&companyId=2&offerId=1",
    )
    official = probe(tmp_path, "official", "captcha", 567, "https://webapi.sporttery.cn/history")
    manifest = build_probe_manifest([result["probe_path"], official["probe_path"]], root=tmp_path)
    counts = manifest_counts(manifest)
    assert counts["sina_odds_history_response_count"] == int(has_time)
    assert counts["accepted_source_count"] == counts["official_json_count"] == 0
    section = blocked_report_section(manifest)
    assert "| replay-qualified external historical odds | 0 |" in section
    assert "| Market replay evaluable | 0 |" in section


def test_committed_manifest_and_pilot_report_numbers_match():
    # No local Raw and no network needed on CI. The bounded section is reproducible
    # from the committed allowlisted manifest alone, including all zero/pass claims.
    manifest = json.loads(Path("docs/research-probe-manifest.json").read_text("utf-8"))
    report = Path("docs/PILOT_DATASET_REPORT.md").read_text("utf-8")
    assert blocked_report_section(manifest) in report
    records = manifest["records"]
    assert records == sorted(
        records,
        key=lambda r: (r["source"], r["public_url"], r["probe_utc"], r["local_artifact_relative_path"]),
    )
    for record in records:
        assert record["secret_scan"] == "PASS"
        reject_secrets({k: v for k, v in record.items() if k != "secret_scan"})
        assert not Path(record["local_artifact_relative_path"]).is_absolute()
