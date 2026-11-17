#!/usr/bin/env python3
"""Build a Tamil Nadu retail food-price snapshot from Reclaim's DoCA mirror."""

from __future__ import annotations

import json
import statistics
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path


API = "https://cpi.reclaimchennai.city/api"
OUT = Path(__file__).resolve().parents[1] / "data" / "food-prices.json"
HEADERS = {"User-Agent": "WayToFortuneClubFoodPriceDashboard/1.0 (public data attribution)"}


def get_json(url: str):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def fetch_map(day: str):
    query = urllib.parse.urlencode({"date": day, "kind": "retail"})
    return get_json(f"{API}/map?{query}")


def main():
    meta = get_json(f"{API}/meta")
    dates = get_json(f"{API}/dates?limit=60&kind=retail")["dates"]
    if not dates:
        raise RuntimeError("The retail source returned no reporting dates")

    latest_date = max(date.fromisoformat(d) for d in dates)
    target = latest_date - timedelta(days=7)
    previous_candidates = [date.fromisoformat(d) for d in dates if date.fromisoformat(d) <= target]
    if not previous_candidates:
        raise RuntimeError("The source has no report from the previous week")
    previous_date = max(previous_candidates)
    if (target - previous_date).days > 10:
        raise RuntimeError("The source has a gap of more than 10 days before the comparison week")

    centres = [c for c in meta["centres"] if c.get("state") == "Tamil Nadu"]
    centre_ids = {str(c["id"]) for c in centres}
    if not centre_ids:
        raise RuntimeError("No Tamil Nadu reporting centres were found")

    current, previous = fetch_map(latest_date.isoformat()), fetch_map(previous_date.isoformat())
    commodities = meta["commodities"]
    selected = [
        c for c in commodities
        if c.get("category") == "Vegetables"
        or c.get("category") == "Pulses & Dals"
        or c.get("id") in {7, 8, 9}
    ]

    items = []
    for commodity in selected:
        key = str(commodity["id"])

        def values(snapshot):
            return [
                float(snapshot.get("centres", {}).get(cid, {}).get(key))
                for cid in centre_ids
                if snapshot.get("centres", {}).get(cid, {}).get(key) is not None
            ]

        current_values = values(current)
        previous_values = values(previous)
        if not current_values or not previous_values:
            continue
        current_avg = round(statistics.fmean(current_values), 2)
        previous_avg = round(statistics.fmean(previous_values), 2)
        delta = round(current_avg - previous_avg, 2)
        pct = round((delta / previous_avg) * 100, 1) if previous_avg else None
        items.append({
            "id": commodity["id"],
            "name": commodity["label"],
            "category": "Millets" if commodity["id"] in {7, 8, 9} else commodity["category"],
            "unit": commodity["unit"],
            "price": current_avg,
            "previousPrice": previous_avg,
            "change": delta,
            "changePercent": pct,
            "reportingCentres": len(current_values),
            "previousReportingCentres": len(previous_values),
        })

    if len(items) < 8:
        raise RuntimeError(f"Only {len(items)} items had both weeks of Tamil Nadu retail data")

    result = {
        "title": "Tamil Nadu retail food prices",
        "asOf": latest_date.isoformat(),
        "comparisonDate": previous_date.isoformat(),
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "state": "Tamil Nadu",
        "aggregation": "Unweighted mean of available Department of Consumer Affairs reporting-centre retail prices within Tamil Nadu.",
        "source": {
            "name": "Reclaim Chennai CPI API",
            "url": "https://cpi.reclaimchennai.city/",
            "originalName": "Department of Consumer Affairs, Government of India — Price Monitoring Division",
            "originalUrl": "https://fcainfoweb.nic.in/",
            "methodologyUrl": "https://cpi.reclaimchennai.city/api/docs",
            "attribution": "Daily retail prices mirrored from DoCA; Tamil Nadu values are calculated by Way to Fortune Club as the unweighted mean of available Tamil Nadu reporting-centre observations.",
        },
        "centresInState": len(centres),
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} items, {len(centres)} Tamil Nadu centres; {latest_date} vs {previous_date}")


if __name__ == "__main__":
    main()

