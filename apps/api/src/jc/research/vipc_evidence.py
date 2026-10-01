"""Offline, single-match VIPC 1X2 evidence inspection; never a Replay importer.

The observed API has naive wall times. Detail's +08 alignment and the UI's direct
updateTime display support Asia/Shanghai only as a candidate cutoff assumption;
the provider timezone and availability semantics remain unconfirmed.
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from jc.providers.parsing import decimal_odds
from jc.research.contracts import canonical_bytes, reject_secrets
from jc.research.probe_manifest import build_probe_manifest
from jc.research.providers.probe import _save
from jc.time import BEIJING, parse_time

MATCH_ID = "498257749"
COMPANY_ID = "432"
BASE_URL = f"https://www.vipc.cn/i/match/football/{MATCH_ID}"
KICKOFF = parse_time("2026-09-30T14:00:00+08:00")
SELECTIONS = ("HOME", "DRAW", "AWAY")


def inspect_vipc_history(detail: dict, companies: dict, history: dict) -> dict:
    """Inspect the observed schema, keeping all observations and refusing identity drift."""
    model = detail.get("model", {})
    company_rows = companies.get("odds")
    if (
        not isinstance(model, dict)
        or not isinstance(company_rows, list)
        or not all(isinstance(r, dict) for r in company_rows)
    ):
        raise ValueError("VIPC detail/company schema invalid")
    listed = [r for r in company_rows if r.get("companyId") == COMPANY_ID]
    if (
        detail.get("type") != "football"
        or model.get("matchId") != MATCH_ID
        or history.get("companyId") != COMPANY_ID
        or len(listed) != 1
        or not model.get("issue")
        or model["issue"] != history.get("issue")
        or model.get("matchTime") != "2026-09-30 14:00:00"
    ):
        raise ValueError("VIPC match/company identity or kickoff mismatch")
    # These fields were absent in both real responses. A new schema needs review,
    # not an invented offerId or silently ignored additional identity dimension.
    if any(r.get(key) is not None for r in (listed[0], history) for key in ("offerId", "companyCode")):
        raise ValueError("Unreviewed VIPC offerId/companyCode")
    raw_rows = history.get("list")
    if not isinstance(raw_rows, list) or not all(isinstance(r, dict) for r in raw_rows):
        raise ValueError("VIPC history list required")
    rows: list[dict] = []
    groups: dict[str, list[dict]] = defaultdict(list)
    for index, raw in enumerate(raw_rows):
        row: dict = {
            "row_index": index,
            "raw_time_field": "updateTime",
            "raw_time_value": raw.get("updateTime"),
            "parsed_utc": None,
            "classification": "UNVERIFIED",
            "odds": None,
            "errors": [],
            "return_rate": None,
            "return_rate_matches": False,
            "flags": [],
            "replay_available_at": None,
        }
        try:
            stamp = raw.get("updateTime")
            if not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", stamp):
                raise ValueError("Full raw wall time required")
            parsed = parse_time(stamp, "Asia/Shanghai")
            row["parsed_utc"] = parsed.isoformat()
            row["ui_time"] = stamp[5:-3]  # Exact observed template operation, never parsing UI.
            row["classification"] = "PREMATCH" if parsed < KICKOFF else "INPLAY_OR_POST_KICKOFF"
            groups[row["parsed_utc"]].append(row)
        except ValueError:
            row["errors"].append("INVALID_RAW_TIME")
        try:
            values = raw.get("odds")
            if (
                not isinstance(values, list)
                or len(values) != 3
                or not all(isinstance(v, str) for v in values)
            ):
                raise ValueError("Three Decimal strings required")
            prices = [decimal_odds(v) for v in values]
            row["odds"] = dict(zip(SELECTIONS, prices, strict=True))
            row["return_rate"] = Decimal(1) / sum((Decimal(1) / p for p in prices), Decimal(0))
        except ValueError:
            row["errors"].append("INVALID_1X2")
        try:
            shown = raw.get("returnRatio")
            if not isinstance(shown, str) or not re.fullmatch(r"\d+(?:\.\d+)?%", shown):
                raise ValueError("Percentage required")
            if row["return_rate"] is not None:
                percent = row["return_rate"] * 100
                row["return_rate_difference_pp"] = abs(percent - Decimal(shown[:-1]))
                row["return_rate_matches"] = percent.quantize(
                    Decimal(".01"), rounding=ROUND_HALF_UP
                ) == Decimal(shown[:-1])
                if not row["return_rate_matches"]:
                    row["errors"].append("RETURN_RATE_MISMATCH")
        except (ValueError, InvalidOperation):
            row["errors"].append("INVALID_RETURN_RATE")
        rows.append(row)

    for group in groups.values():
        if len(group) < 2:
            continue
        signatures = {canonical_bytes(raw_rows[r["row_index"]]) for r in group}
        price_signatures = {tuple(r["odds"].values()) if r["odds"] else None for r in group}
        if len(price_signatures) > 1:
            flag = "TIMESTAMP_CONFLICT"
        elif len(signatures) == 1:
            flag = "duplicate_observation_candidate"
        else:
            flag = "TIMESTAMP_METADATA_CONFLICT"
        for row in group:
            row["flags"].append(flag)

    candidates = {}
    for minutes in (30, 90, 360):
        cutoff = KICKOFF - timedelta(minutes=minutes)
        times = [
            t for t, group in groups.items() if parse_time(t) <= cutoff and any(r["odds"] for r in group)
        ]
        candidate = None
        reason = "NO_COMPLETE_1X2_BEFORE_CUTOFF"
        if times:
            group = groups[max(times)]
            if any(
                "TIMESTAMP_CONFLICT" in r["flags"] or "TIMESTAMP_METADATA_CONFLICT" in r["flags"]
                for r in group
            ):
                reason = "TIMESTAMP_CONFLICT"
            elif any(r["errors"] for r in group):
                reason = "INVALID_OBSERVATION"
            else:
                row = group[0]  # Only identical observations can share this time.
                candidate = {
                    "raw_time_value": row["raw_time_value"],
                    "parsed_utc": row["parsed_utc"],
                    "odds": row["odds"],
                    "observation_indexes": [r["row_index"] for r in group],
                    "cutoff_utc": cutoff.isoformat(),
                    "replay_available_at": None,
                }
                reason = "CANDIDATE_ONLY"
        candidates[f"candidate_T{minutes}"] = {"value": candidate, "status": reason}

    times = [r["parsed_utc"] for r in rows if r["parsed_utc"]]
    prematch_times = [r["parsed_utc"] for r in rows if r["classification"] == "PREMATCH"]
    report = {
        "provider": "vipc",
        "match_id": MATCH_ID,
        "company_id": COMPANY_ID,
        "offer_id": None,
        "company_code": None,
        "bookmaker_identity": f"vipc:{COMPANY_ID}",
        "display_name": history.get("companyName"),
        "market": "1X2",
        "official_mapping_candidate": history["issue"],
        "verified_targets": [],
        "field_mapping": dict(zip(SELECTIONS, ("odds[0]", "odds[1]", "odds[2]"), strict=True)),
        "raw_time_field": "updateTime",
        "time_unit": "WALL_CLOCK_STRING_SECONDS",
        "timezone": None,
        "candidate_timezone": "Asia/Shanghai",
        "timezone_status": "ASSUMED_FOR_CANDIDATE_ONLY",
        "time_semantics": "E_UNCONFIRMED",
        "availability_status": "AVAILABILITY_SEMANTICS_UNVERIFIED",
        "replay_available_at": None,
        "availability_basis": None,
        "kickoff_utc": KICKOFF.isoformat(),
        "total_rows": len(rows),
        "prematch_rows": len(prematch_times),
        "post_kickoff_rows": sum(r["classification"] == "INPLAY_OR_POST_KICKOFF" for r in rows),
        "invalid_time_rows": len(rows) - len(times),
        "earliest_time": min(times, default=None),
        "latest_prematch_time": max(prematch_times, default=None),
        "latest_overall_time": max(times, default=None),
        "return_rate_pass_rows": sum(r["return_rate_matches"] for r in rows),
        "duplicate_timestamp_groups": sum(len(g) > 1 for g in groups.values()),
        "timestamp_conflict_groups": sum(
            any("TIMESTAMP_CONFLICT" in r["flags"] for r in g) for g in groups.values()
        ),
        "history_completeness": "ALL_ROWS_RETURNED_NO_PAGINATION_OBSERVED_NOT_ARCHIVE_COMPLETENESS",
        "source_decision": "UNVERIFIED",
        "license_status": "RESTRICTED",
        "gate_a": "BLOCKED",
        "gate_b": "BLOCKED",
        "rows": rows,
        **candidates,
    }
    reject_secrets(report)
    return report


def inspect_saved_probes(folder: Path, root: Path) -> dict:
    """Use the existing hash/secret/provenance verifier before parsing saved JSON."""
    manifest = build_probe_manifest(folder.rglob("*.json"), root=root)
    payloads = []
    evidence = []
    for url in (BASE_URL, BASE_URL + "/odds/euro", BASE_URL + f"/odds/euro/{COMPANY_ID}"):
        matches = [r for r in manifest["records"] if r["public_url"] == url]
        if len(matches) != 1 or matches[0]["retention"] != "UNCHANGED" or matches[0]["http_status"] != 200:
            raise ValueError("One unchanged successful Raw per VIPC endpoint required")
        record = matches[0]
        stored = json.loads((root / record["local_artifact_relative_path"]).read_text("utf-8"))
        payload = json.loads(stored["raw"]["payload"])
        if not isinstance(payload, dict):
            raise ValueError("VIPC JSON object required")
        payloads.append(payload)
        evidence.append(
            {
                k: record[k]
                for k in (
                    "public_url",
                    "probe_utc",
                    "canonical_sanitized_raw_hash",
                    "local_artifact_relative_path",
                )
            }
        )
    report = inspect_vipc_history(*payloads)
    report["evidence"] = evidence
    return report


def report_section(report: dict) -> str:
    lines = [
        "<!-- BEGIN VIPC CANDIDATES -->",
        "",
        "以下由已保存 Raw 离线计算；依据 detail 的 +08 对齐关系及页面直显 updateTime，"
        "暂以 Asia/Shanghai 作为仅用于 candidate cutoff 的解析假设；正式时区及 availability 语义未确认。",
        "",
        "| 检查项 | 结果 |",
        "|---|---|",
    ]
    for key in (
        "bookmaker_identity",
        "total_rows",
        "prematch_rows",
        "post_kickoff_rows",
        "invalid_time_rows",
        "earliest_time",
        "latest_prematch_time",
        "latest_overall_time",
        "return_rate_pass_rows",
        "duplicate_timestamp_groups",
        "timestamp_conflict_groups",
        "license_status",
        "source_decision",
        "gate_a",
        "gate_b",
    ):
        lines.append(f"| {key} | {report[key]} |")
    lines += [
        "",
        "| candidate | 截点（北京时间） | 原始 updateTime | parsed_utc（候选） | HOME / DRAW / AWAY |",
        "|---|---|---|---|---|",
    ]
    for minutes in (30, 90, 360):
        item = report[f"candidate_T{minutes}"]
        value = item["value"]
        cutoff = (KICKOFF - timedelta(minutes=minutes)).astimezone(BEIJING).strftime("%H:%M")
        if value:
            prices = " / ".join(str(value["odds"][k]) for k in SELECTIONS)
            lines.append(
                f"| candidate_T{minutes} | {cutoff} | {value['raw_time_value']} | {value['parsed_utc']} | {prices} |"
            )
        else:
            lines.append(f"| candidate_T{minutes} | {cutoff} | {item['status']} | — | — |")
    return "\n".join([*lines, "", "<!-- END VIPC CANDIDATES -->"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Saved probe directory; no network")
    parser.add_argument("--report", type=Path, help="Update the bounded Markdown results section")
    args = parser.parse_args()
    report = inspect_saved_probes(args.input, Path.cwd())
    path = _save(args.input, {"vipc_inspection": report})
    if args.report:
        text = args.report.read_text("utf-8")
        section = report_section(report)
        pattern = r"<!-- BEGIN VIPC CANDIDATES -->.*?<!-- END VIPC CANDIDATES -->"
        text = (
            re.sub(pattern, lambda _: section, text, flags=re.S)
            if re.search(pattern, text, re.S)
            else text + "\n" + section + "\n"
        )
        args.report.write_text(text, "utf-8")
    print(
        json.dumps(
            {
                "report_path": str(path),
                "source_decision": report["source_decision"],
                "total_rows": report["total_rows"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
