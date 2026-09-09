#!/usr/bin/env python3
"""
Weekly refresh for Oil Gauge's static data files.

Pulls the Consumer Council NI's public heating oil price archive and the
current council-area breakdown, merges any new weeks into data/weekly.json,
and attaches the area breakdown to the latest week in data/clubs-adjacent
data/weekly.json.

Design choices, on purpose:
  - This UPSERTS new dates only. It never overwrites a date already stored,
    even if the source value has since changed slightly, so a source
    correction can't silently rewrite history we've already published.
    (If the Council ever republishes a corrected figure and you want that
    picked up, that's a manual edit, not something this script should do
    on its own.)
  - Sanity bounds and an "anomaly" cap guard against a page redesign
    breaking the parser silently. If either trips, the script exits
    non-zero WITHOUT writing anything, and the GitHub Action step that
    runs it will show as failed rather than commit bad data.
  - Verified against the live source data on 2026-09-09: parsing all 279
    then-current historical rows this way reproduced the already-published
    weekly.json exactly, including the one known source duplicate
    (17 Nov 2021, two different 900L figures — this script keeps the
    first-listed one, £464.96, matching the original manual backfill).
"""
import datetime
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ARCHIVE_URL = "https://www.consumercouncil.org.uk/home-heating/price-checker/archive"
CHECKER_URL = "https://www.consumercouncil.org.uk/home-heating/price-checker"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OilGaugeBot/1.0; +weekly public price sync)"}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WEEKLY_PATH = DATA_DIR / "weekly.json"

# Sanity bounds (£), generous around observed 2021-2026 range, to catch a
# broken parse rather than write garbage.
BOUNDS = {
    "niAvg300": (50, 600),
    "niAvg500": (80, 900),
    "niAvg900": (150, 1700),
}
MAX_NEW_ROWS_PER_RUN = 4  # more than this in one run smells like a parser break, not real new weeks


def gbp(text):
    return round(float(text.replace("£", "").replace(",", "").strip()), 2)


def parse_date(text):
    return datetime.datetime.strptime(text.strip(), "%d %B %Y").date().isoformat()


def fetch_archive():
    resp = requests.get(ARCHIVE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = None
    for t in soup.find_all("table"):
        if t.find("th", id=re.compile(r"^view-field-overall-500-average")):
            table = t
            break
    if table is None:
        raise RuntimeError("Couldn't find the weekly archive table on the page — site structure may have changed.")

    rows_out = {}
    body_rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]
    for tr in body_rows:
        date_cell = tr.find("td", class_=re.compile(r"views-field-title"))
        p300_cell = tr.find("td", class_=re.compile(r"views-field-field-overall-300-average"))
        p500_cell = tr.find("td", class_=re.compile(r"views-field-field-overall-500-average"))
        p900_cell = tr.find("td", class_=re.compile(r"views-field-field-overall-900-average"))
        if not (date_cell and p300_cell and p500_cell and p900_cell):
            continue
        link = date_cell.find("a")
        date_text = (link.text if link else date_cell.text).strip()
        iso = parse_date(date_text)
        row = {
            "date": iso,
            "niAvg300": gbp(p300_cell.text),
            "niAvg500": gbp(p500_cell.text),
            "niAvg900": gbp(p900_cell.text),
            "source": "weekly-task",
        }
        if iso not in rows_out:  # keep first-seen (source lists newest-first; ties resolve to the first listing)
            rows_out[iso] = row
    return rows_out


def fetch_council_breakdown():
    resp = requests.get(CHECKER_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = None
    for t in soup.find_all("table", class_=re.compile(r"\bcols-4\b")):
        table = t
        break
    if table is None:
        return None  # non-fatal — the weekly price update can still proceed without this

    out = []
    body_rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]
    for tr in body_rows:
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue
        area_link = cells[0].find("a")
        area = (area_link.text if area_link else cells[0].text).strip()
        try:
            p300 = gbp(cells[1].find("strong").text)
            p500 = gbp(cells[2].find("strong").text)
            p900 = gbp(cells[3].find("strong").text)
        except (AttributeError, ValueError):
            continue
        out.append({"area": area, "p300": p300, "p500": p500, "p900": p900})
    return out or None


def load_existing():
    if WEEKLY_PATH.exists():
        return {r["date"]: r for r in json.loads(WEEKLY_PATH.read_text())}
    return {}


def validate(row):
    for field, (lo, hi) in BOUNDS.items():
        v = row[field]
        if not (lo <= v <= hi):
            raise ValueError(f"{row['date']} {field}={v} is outside sane bounds [{lo}, {hi}] — refusing to write.")


def main():
    existing = load_existing()
    scraped = fetch_archive()

    new_dates = sorted(set(scraped) - set(existing))
    if len(new_dates) > MAX_NEW_ROWS_PER_RUN:
        print(f"Refusing to proceed: {len(new_dates)} new dates found in one run "
              f"(cap is {MAX_NEW_ROWS_PER_RUN}) — this looks like a parsing problem, not real new data.",
              file=sys.stderr)
        sys.exit(1)

    for d in new_dates:
        validate(scraped[d])
        existing[d] = scraped[d]

    if not new_dates:
        print("No new weeks found — nothing to do.")
    else:
        print(f"Added {len(new_dates)} new week(s): {', '.join(new_dates)}")

    # Attach the current council-area breakdown to the latest known week.
    latest_date = max(existing)
    council = fetch_council_breakdown()
    if council:
        existing[latest_date]["byCouncil"] = council
        print(f"Attached council-area breakdown to {latest_date} ({len(council)} areas).")
    else:
        print("Council-area breakdown not found this run — leaving weekly prices as-is.", file=sys.stderr)

    ordered = [existing[d] for d in sorted(existing)]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEEKLY_PATH.write_text(json.dumps(ordered, indent=2) + "\n")
    # Whether this run actually changed anything is decided by git diffing
    # the file afterward (see the workflow), not by an exit code here —
    # exit 0 means "ran cleanly", non-zero (via the guard above, or an
    # uncaught ValueError from validate()) means "refused to write, don't commit."


if __name__ == "__main__":
    main()
