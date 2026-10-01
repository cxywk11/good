"""Build a Git-safe allowlisted manifest from local Raw and probe summaries."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from jc.research.contracts import ResearchRawArtifactInput, canonical_bytes, reject_secrets
from jc.research.official_evidence import OFFICIAL_HOSTS
from jc.research.providers.inspection import inspect_odds_history_payload, inspect_sporttery_history_payload
from jc.research.providers.probe import public_url
from jc.time import parse_time


def _relative(path: Path, root: Path) -> str:
    path = path.resolve()
    relative = path.relative_to(root.resolve())
    if not relative.parts or relative.parts[0] != "artifacts":
        raise ValueError("Probe artifacts must remain inside the repository artifacts directory")
    reject_secrets(relative.as_posix())
    return relative.as_posix()


def _digest(value) -> str | None:
    if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)):
        raise ValueError("Invalid probe digest")
    return value


def _inspect(raw: ResearchRawArtifactInput) -> tuple[str, str]:
    status = raw.metadata.get("http_status")
    if status is not None and not 200 <= status < 300:
        return "INVALID_EVIDENCE", "BLOCKED"
    if raw.metadata.get("retention") != "UNCHANGED":
        return "REDACTED_OR_WITHHELD", "BLOCKED"
    parts = urlsplit(raw.external_ref or "")
    if not isinstance(raw.payload, str):
        return "UNVERIFIED", "UNVERIFIED"
    if parts.hostname in OFFICIAL_HOSTS:
        if parts.path.endswith(".js"):
            return "EXPECTED_FROM_JS", "UNVERIFIED"
        report = inspect_sporttery_history_payload(raw.payload.lstrip("\ufeff"))
        return report["schema_status"], report["evidence_decision"]
    if parts.hostname == "api.the-odds-api.com" and parts.path.startswith("/v4/historical/"):
        requested = parse_qs(parts.query).get("date", [None])[0]
        report = inspect_odds_history_payload(
            raw.payload,
            requested_at=parse_time(requested) if requested else None,
            retrieved_at=raw.retrieved_at,
        )
        return report["schema_status"], report["evidence_decision"]
    if parts.hostname == "alpha.lottery.sina.com.cn" and parts.path == "/gateway/index/entry":
        query = parse_qs(parts.query)
        if query.get("cat1") in (
            ["footballMatchOddsEuroChange"],
            ["footballMatchOddsAsiaChange"],
            ["footballMatchOddsTotalsChange"],
        ) and all(len(query.get(key, [])) == 1 for key in ("matchId", "companyId", "offerId")):
            try:
                payload = json.loads(raw.payload)
            except ValueError:
                payload = None
            result = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(result, dict) and result.get("status") == {"code": 0, "msg": "success"}:
                rows = result.get("data")
                if isinstance(rows, list) and rows and all(
                    isinstance(row, dict) and {"o1", "o2", "o3", "oddsTime"} <= row.keys()
                    for row in rows
                ):
                    # Field presence only: no license, time semantics, official
                    # target, bookmaker mapping or replay eligibility is certified.
                    return "SINA_ODDS_HISTORY_OBSERVED_REVIEW_REQUIRED", "UNVERIFIED"
    # Documentation and alternative-source discovery cannot certify real data.
    return "UNVERIFIED", "UNVERIFIED"


def build_probe_manifest(summary_paths, *, root: Path) -> dict:
    records = []
    seen = set()
    for summary_path in sorted({Path(path).resolve() for path in summary_paths}):
        summary_rel = _relative(summary_path, root)
        document = json.loads(summary_path.read_text("utf-8"))
        if "source_probe" not in document:
            continue  # Raw files and aggregate reports are not additional probes.
        summary = document["source_probe"]
        reject_secrets(summary)
        source = summary["source"]
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", source):
            raise ValueError("Invalid probe source name")
        url = public_url(summary["url"])
        if url != summary["url"]:
            raise ValueError("Probe summary URL must already be sanitized")
        timestamp = parse_time(summary["timestamp"]).isoformat()
        status = summary.get("http_status")
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            raise ValueError("Invalid HTTP status")
        response_hash = _digest(summary.get("response_sha256"))
        raw_hash = _digest(summary.get("raw_content_hash"))
        retention, schema, decision = "NO_RESPONSE", "NO_RESPONSE", "BLOCKED"
        artifact_rel = summary_rel
        if raw_hash is not None:
            raw_path = Path(summary["raw_path"])
            if not raw_path.is_absolute():
                raw_path = root / raw_path
            artifact_rel = _relative(raw_path, root)
            stored = json.loads(raw_path.read_text("utf-8"))
            values = stored["raw"]
            raw = ResearchRawArtifactInput(**{**values, "retrieved_at": parse_time(values["retrieved_at"])})
            if (
                raw.content_hash != raw_hash
                or stored["raw_content_hash"] != raw_hash
                or raw.metadata["response_sha256"] != response_hash
                or raw.external_ref != url
                or raw.source_name != source
                or raw.retrieved_at.isoformat() != timestamp
                or raw.metadata.get("http_status") != status
            ):
                raise ValueError("Probe summary disagrees with preserved Raw")
            retention = raw.metadata["retention"]
            if retention not in ("UNCHANGED", "REDACTED", "WITHHELD"):
                raise ValueError("Invalid Raw retention")
            schema, decision = _inspect(raw)
            if retention == "UNCHANGED":
                encoding = raw.metadata.get("text_encoding")
                if encoding is None:
                    # Early D2B probes predate explicit decoding metadata. Their
                    # canonical payload is verifiable, original bytes are not.
                    if decision != "BLOCKED":
                        schema, decision = "LEGACY_BYTE_ENCODING_UNVERIFIED", "UNVERIFIED"
                elif hashlib.sha256(raw.payload.encode(encoding)).hexdigest() != response_hash:
                    raise ValueError("Response bytes do not match the original digest")
        elif response_hash is not None or status is not None:
            raise ValueError("HTTP response must have preserved Raw")
        record = {
            "source": source,
            "public_url": url,
            "probe_utc": timestamp,
            "http_status": status,
            "response_sha256": response_hash,
            "canonical_sanitized_raw_hash": raw_hash,
            "retention": retention,
            "schema_status": schema,
            "local_artifact_relative_path": artifact_rel,
            "evidence_decision": decision,
        }
        reject_secrets(record)
        # The literal required audit label is the sole exception to the D2A key
        # name guard; its value is constant, never caller-controlled metadata.
        record["secret_scan"] = "PASS"
        identity = canonical_bytes(record)
        if identity not in seen:
            seen.add(identity)
            records.append(record)
    records.sort(
        key=lambda r: (r["source"], r["public_url"], r["probe_utc"], r["local_artifact_relative_path"])
    )
    return {"records": records}


def manifest_counts(manifest: dict) -> dict:
    records = manifest["records"]
    return {
        "probe_count": len(records),
        "response_raw_count": sum(r["response_sha256"] is not None for r in records),
        "no_response_count": sum(r["response_sha256"] is None for r in records),
        "official_json_count": sum(
            urlsplit(r["public_url"]).hostname in OFFICIAL_HOSTS
            and r["schema_status"] == "JSON_OBSERVED_REVIEW_REQUIRED"
            for r in records
        ),
        "historical_envelope_count": sum(
            r["schema_status"] == "HISTORICAL_ENVELOPE_OBSERVED" for r in records
        ),
        "sina_odds_history_response_count": sum(
            r["schema_status"] == "SINA_ODDS_HISTORY_OBSERVED_REVIEW_REQUIRED" for r in records
        ),
        "accepted_source_count": len({r["source"] for r in records if r["evidence_decision"] == "ACCEPTED"}),
    }


def blocked_report_section(manifest: dict) -> str:
    counts = manifest_counts(manifest)
    if not any(urlsplit(r["public_url"]).hostname in OFFICIAL_HOSTS for r in manifest["records"]):
        raise ValueError("An actual official probe is required for a no-evidence report")
    # Refuse to overwrite a potentially successful intake with the no-evidence branch.
    if counts["official_json_count"] or counts["historical_envelope_count"]:
        raise ValueError("Observed data requires evidence review; do not publish a no-evidence report")
    lines = [
        "<!-- BEGIN MACHINE PROBE STATUS -->",
        "## P4-4D2B.1 机器核验",
        "",
        "由 `python -m jc.research.probe_manifest` 与 manifest 同次生成；仅报告尚无已核验官方 Target 或外部历史快照的分支。",
        "",
        "| 项目 | 数量 / 状态 |",
        "|---|---|",
        *[f"| {key} | {value} |" for key, value in counts.items()],
        "| VERIFIED Sporttery Target | 0 |",
        "| replay-qualified external historical odds | 0 |",
        "| T-30M / T-90M / T-360M coverage | 0 / 0 / 0 |",
        "| Market replay evaluable | 0 |",
        "| SEALED Pilot / Dataset hash | 无 / 无 |",
        "| Gate A：官方 Target | BLOCKED：没有已复核官方目标比赛 |",
        "| Gate B：外部历史赔率 | BLOCKED：没有匹配已核验官方目标且通过来源/时间准入的完整 1X2 |",
        "| Gate C：常规时间赛果 | BLOCKED：没有目标赛果证据 |",
        "| Gate D：稳定实体 | BLOCKED：没有已核验映射 |",
        "| Gate E：SEALED | BLOCKED：没有实际 ResearchImport |",
        "| Gate F：Replay | BLOCKED：没有真实 SEALED / Run |",
        "| 扩大三个赛季 | 不允许 |",
        "",
        "<!-- END MACHINE PROBE STATUS -->",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True, help="Probe directories")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("docs/research-probe-manifest.json"))
    parser.add_argument("--blocked-report", type=Path)
    args = parser.parse_args()
    manifest = build_probe_manifest(
        [p for folder in args.input for p in folder.rglob("*.json")],
        root=args.root,
    )
    report = None
    if args.blocked_report:
        original = args.blocked_report.read_text("utf-8")
        section = blocked_report_section(manifest)
        pattern = r"<!-- BEGIN MACHINE PROBE STATUS -->.*?<!-- END MACHINE PROBE STATUS -->"
        report = (
            re.sub(pattern, lambda _: section, original, flags=re.S)
            if re.search(pattern, original, re.S)
            else original + "\n" + section + "\n"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    if report is not None:
        args.blocked_report.write_text(report, "utf-8")
    print(json.dumps(manifest_counts(manifest)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
