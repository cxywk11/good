"""Regenerate explicitly synthetic fixtures; never fetch or claim live data."""

import json
from pathlib import Path

folder = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
links = {"mock": True, "teams": [], "competitions": []}
for i, (provider, bookmaker) in enumerate(
    [("pinnacle", "Pinnacle"), ("bet365", "Bet365"), ("macau", "Macau"), ("williamhill", "WilliamHill")]
):
    matches = []
    odds = []
    for j, (home, away, hid, aid, league, kickoff) in enumerate(
        [
            ("Arsenal", "Bayern Munich", "ars", "bay", "ucl", "19:00"),
            ("Real Madrid", "Inter", "rma", "int", "ucl", "19:00"),
            ("Leeds United", "Sunderland", "lee", "sun", "eng", "19:45"),
            ("Unlisted Club A", "Unlisted Club B", "new-a", "new-b", "other", "20:00"),
        ]
    ):
        external = f"mock-{provider}-{j + 1:03d}"
        matches.append(
            {
                "external_id": external,
                "home_name": home,
                "away_name": away,
                "home_external_id": f"mock-{provider}-{hid}",
                "away_external_id": f"mock-{provider}-{aid}",
                "competition": league,
                "competition_external_id": f"mock-{provider}-{league}",
                "kickoff_at": f"2026-09-30T{kickoff}:00Z",
            }
        )
        if j < 3:
            for tid in (hid, aid):
                links["teams"].append(
                    {
                        "provider": provider,
                        "external_id": f"mock-{provider}-{tid}",
                        "sporttery_external_id": f"mock-{tid}",
                    }
                )
            entry = {
                "provider": provider,
                "external_id": f"mock-{provider}-{league}",
                "sporttery_external_id": f"mock-{league}",
            }
            if entry not in links["competitions"]:
                links["competitions"].append(entry)
        for market, selections in {
            "1X2": [("HOME", None, 2.12), ("DRAW", None, 3.65), ("AWAY", None, 3.25)],
            "ASIAN_HANDICAP": [("HOME", "-0.75", 1.91), ("AWAY", "0.75", 1.97)],
            "TOTALS": [("OVER", "2.5", 1.85), ("UNDER", "2.5", 2.03)],
            "CORRECT_SCORE": [("1:0", None, 8.5), ("1:1", None, 6.8), ("0:1", None, 9.2)],
        }.items():
            for selection, line, price in selections:
                odds.append(
                    {
                        "external_match_id": external,
                        "bookmaker": bookmaker,
                        "market_type": market,
                        "selection": selection,
                        "line": line,
                        "decimal_odds": f"{price + i * 0.03 + j * 0.02:.2f}",
                        "effective_at": "2026-09-30T00:00:00Z",
                    }
                )
    (folder / f"{provider}.json").write_text(
        json.dumps(
            {
                "mock": True,
                "fixture_note": "Synthetic SDK contract, NOT a real bookmaker API response",
                "matches": matches,
                "odds": odds,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
(folder / "entity_links.json").write_text(json.dumps(links, indent=2), encoding="utf-8")
