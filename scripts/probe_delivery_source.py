"""
scripts/probe_delivery_source.py

Finds the real bulk delivery-data report URL, empirically. This can't be
resolved from Claude's sandbox (nseindia.com isn't reachable from there),
so run this somewhere that has normal internet access -- your own machine,
or `gh workflow run` as a one-off manual dispatch on this repo (GitHub's
runners have full internet access).

Usage:
    python scripts/probe_delivery_source.py [YYYY-MM-DD]
    (defaults to the most recent weekday if no date given)

What it does:
    1. Tries a short list of plausible candidate URLs for the bulk
       delivery report (informed by NSE's general archive conventions,
       but NOT independently confirmed -- that's the whole point of
       running this).
    2. Fetches NSE's public report-listing page and searches its HTML
       for any link whose text or href mentions "deliver", in case the
       real filename is sitting right there in plain markup.
    3. Prints a clear PASS/FAIL per candidate so the result is
       unambiguous -- update BASE_URL in nse_bhavcopy.py's delivery
       handling once one succeeds.

This script deliberately does NOT get wired into the daily pipeline --
it's a one-time (or occasional) diagnostic, not a scheduled job.
"""
import contextlib
import re
import sys
from datetime import date, datetime, timedelta

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def most_recent_weekday() -> date:
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def candidate_urls(target_date: date) -> list[str]:
    ddmmyyyy = target_date.strftime("%d%m%Y")
    yyyymmdd = target_date.strftime("%Y%m%d")
    return [
        # Legacy MTO-style delivery file -- pre-UDiFF convention, may or
        # may not still exist post-migration.
        f"https://nsearchives.nseindia.com/archives/equities/mto/MTO_{ddmmyyyy}.DAT",
        f"https://nsearchives.nseindia.com/content/equities/MTO_{ddmmyyyy}.DAT",
        # UDiFF-adjacent naming guesses, by analogy with the confirmed
        # BhavCopy_NSE_CM_... pattern.
        f"https://nsearchives.nseindia.com/content/cm/SecurityWiseDeliverablePosition_{yyyymmdd}.csv",
        f"https://nsearchives.nseindia.com/content/cm/CM_Deliverable_{yyyymmdd}.csv",
    ]


def check_url(session: requests.Session, url: str) -> tuple[bool, str]:
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200 and len(r.content) > 100:
            preview = r.content[:120].decode(errors="replace").replace("\n", " ")
            return True, f"200 OK, {len(r.content)} bytes -- preview: {preview!r}"
        return False, f"{r.status_code}"
    except requests.RequestException as e:
        return False, f"error: {e}"


def scan_report_page_html(session: requests.Session) -> list[str]:
    hits = []
    for url in (
        "https://www.nseindia.com/all-reports",
        "https://www.nseindia.com/resources/historical-reports-capital-market-daily-monthly-archives",
    ):
        try:
            r = session.get(url, timeout=15)
            for m in re.finditer(r'href="([^"]*)"[^>]*>([^<]*deliver[^<]*)', r.text, re.IGNORECASE):
                hits.append(f"{url} -> href={m.group(1)!r} text={m.group(2).strip()!r}")
        except requests.RequestException as e:
            hits.append(f"{url} -> fetch error: {e}")
    return hits


def main() -> None:
    target_date = (
        datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        if len(sys.argv) > 1
        else most_recent_weekday()
    )
    print(f"Probing for delivery-data source, target date {target_date}\n")

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    # NSE's www.nseindia.com endpoints need a warmed session cookie;
    # the nsearchives.nseindia.com static CDN does not.
    with contextlib.suppress(requests.RequestException):
        session.get("https://www.nseindia.com/", timeout=15)

    print("=== Candidate direct-download URLs ===")
    any_pass = False
    for url in candidate_urls(target_date):
        ok, detail = check_url(session, url)
        status = "PASS" if ok else "fail"
        print(f"[{status}] {url}\n       {detail}")
        any_pass = any_pass or ok

    print("\n=== Scanning NSE report-listing pages for delivery-related links ===")
    hits = scan_report_page_html(session)
    if hits:
        for h in hits:
            print(f"  {h}")
    else:
        print("  No delivery-related href/text found in static HTML "
              "(the report picker is likely JS-rendered -- open "
              "https://www.nseindia.com/all-reports in a browser, filter "
              "to 'Capital Market', find the delivery-position report, "
              "and copy its actual download link from the network tab).")

    print(f"\n{'A candidate PASSED' if any_pass else 'No candidate passed'} -- "
          "see nse_bhavcopy.py's module docstring for where to wire the result in.")


if __name__ == "__main__":
    main()
