#!/usr/bin/env python3
"""Refresh local Search Console history and load it into the remote Grafana stack."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TRACKER_DIR = ROOT / "data" / "search-console"
HISTORY_DIR = TRACKER_DIR / "history"

HISTORY_TABLES = {
    "daily.csv": ("date", ["date", "snapshot_date", "clicks", "impressions", "ctr", "position"]),
    "queries.csv": ("query", ["snapshot_date", "query", "clicks", "impressions", "ctr", "position"]),
    "pages.csv": ("page", ["snapshot_date", "page", "clicks", "impressions", "ctr", "position"]),
    "countries.csv": ("country", ["snapshot_date", "country", "clicks", "impressions", "ctr", "position"]),
    "devices.csv": ("device", ["snapshot_date", "device", "clicks", "impressions", "ctr", "position"]),
    "search_appearance.csv": (
        "search_appearance",
        ["snapshot_date", "search_appearance", "clicks", "impressions", "ctr", "position"],
    ),
}

REMOTE_HISTORY_FILES = tuple(HISTORY_TABLES.keys())


def default_dates() -> tuple[str, str, str]:
    today = date.today()
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    return today.isoformat(), start.isoformat(), end.isoformat()


def parse_args() -> argparse.Namespace:
    snapshot_date, start_date, end_date = default_dates()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auto-seo-root", type=Path, default=Path("/Users/osx/Documents/Projects/auto-seo"))
    parser.add_argument("--credentials-file", type=Path, default=Path("/Users/osx/Documents/Projects/auto-seo/config/client_secret.json"))
    parser.add_argument("--token-file", type=Path, default=Path("/Users/osx/Documents/Projects/auto-seo/config/token.json"))
    parser.add_argument("--site-url", default="sc-domain:bolderelectric.com")
    parser.add_argument("--snapshot-date", default=snapshot_date)
    parser.add_argument("--start-date", default=start_date)
    parser.add_argument("--end-date", default=end_date)
    parser.add_argument("--search-type", default="web")
    parser.add_argument("--row-limit", type=int, default=25000)
    parser.add_argument("--ssh-host", default="192.168.111.138")
    parser.add_argument("--ssh-user", default="root")
    parser.add_argument("--ssh-key", type=Path, default=Path("/Users/osx/.ssh/id_rsa"))
    parser.add_argument("--remote-root", default="/root/bolder-electric")
    parser.add_argument("--skip-remote-pull", action="store_true")
    parser.add_argument("--skip-remote-push", action="store_true")
    parser.add_argument("--skip-remote-load", action="store_true")
    return parser.parse_args()


def import_auto_seo_helpers(auto_seo_root: Path) -> tuple[Any, Any, Any]:
    if not auto_seo_root.exists():
        raise SystemExit(f"Missing auto-seo project: {auto_seo_root}")

    sys.path.insert(0, str(auto_seo_root))
    try:
        from auto_seo.search_console import SearchConsoleConfig, build_service, get_credentials
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing Google Search Console dependencies. Run this script with the "
            "auto-seo virtualenv Python, for example:\n"
            "  /Users/osx/Documents/Projects/auto-seo/.venv/bin/python "
            "scripts/update_search_console_grafana_remote.py"
        ) from exc
    return SearchConsoleConfig, get_credentials, build_service


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def merge_rows(path: Path, rows: list[dict[str, str]], key_fields: tuple[str, ...], fieldnames: list[str]) -> None:
    existing: dict[tuple[str, ...], dict[str, str]] = {}
    for row in read_csv(path):
        existing[tuple(row[field] for field in key_fields)] = row

    for row in rows:
        existing[tuple(row[field] for field in key_fields)] = row

    merged = sorted(existing.values(), key=lambda row: tuple(row[field] for field in key_fields))
    write_csv(path, merged, fieldnames)


def query_dimension(
    service: Any,
    *,
    site_url: str,
    start_date: str,
    end_date: str,
    dimensions: list[str],
    search_type: str,
    row_limit: int,
) -> list[dict[str, Any]]:
    api_page_size = 25_000
    start_row = 0
    rows: list[dict[str, Any]] = []

    while len(rows) < row_limit:
        request_body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "type": search_type,
            "aggregationType": "auto",
            "rowLimit": min(api_page_size, row_limit - len(rows)),
            "startRow": start_row,
        }
        response = service.searchanalytics().query(siteUrl=site_url, body=request_body).execute()
        batch = response.get("rows", [])
        rows.extend(batch)
        if len(batch) < request_body["rowLimit"]:
            break
        start_row += len(batch)
    return rows


def normalize_rows(rows: list[dict[str, Any]], *, dimension_name: str, snapshot_date: str) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row in rows:
        keys = row.get("keys", [])
        dimension_value = keys[0] if keys else ""
        normalized.append(
            {
                "snapshot_date": snapshot_date,
                dimension_name: dimension_value,
                "clicks": str(int(row.get("clicks", 0))),
                "impressions": str(int(row.get("impressions", 0))),
                "ctr": str(float(row.get("ctr", 0))),
                "position": str(float(row.get("position", 0))),
            }
        )
    return normalized


def normalize_daily(rows: list[dict[str, Any]], *, snapshot_date: str) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row in rows:
        keys = row.get("keys", [])
        day = keys[0] if keys else ""
        normalized.append(
            {
                "date": day,
                "snapshot_date": snapshot_date,
                "clicks": str(int(row.get("clicks", 0))),
                "impressions": str(int(row.get("impressions", 0))),
                "ctr": str(float(row.get("ctr", 0))),
                "position": str(float(row.get("position", 0))),
            }
        )
    return normalized


def pull_remote_history(*, ssh_key: Path, ssh_user: str, ssh_host: str, remote_root: str) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    for name in REMOTE_HISTORY_FILES:
        remote_path = f"{ssh_user}@{ssh_host}:{remote_root}/data/search-console/history/{name}"
        run(["scp", "-i", str(ssh_key), "-o", "StrictHostKeyChecking=accept-new", remote_path, str(HISTORY_DIR / name)])


def push_remote_history(*, ssh_key: Path, ssh_user: str, ssh_host: str, remote_root: str) -> None:
    for name in REMOTE_HISTORY_FILES:
        local_path = HISTORY_DIR / name
        if not local_path.exists():
            continue
        remote_path = f"{ssh_user}@{ssh_host}:{remote_root}/data/search-console/history/{name}"
        run(["scp", "-i", str(ssh_key), "-o", "StrictHostKeyChecking=accept-new", str(local_path), remote_path])


def load_remote_grafana(*, ssh_key: Path, ssh_user: str, ssh_host: str, remote_root: str) -> None:
    remote_cmd = f"cd {remote_root} && python3 scripts/sync_search_console_grafana.py --load"
    run(["ssh", "-i", str(ssh_key), "-o", "StrictHostKeyChecking=accept-new", f"{ssh_user}@{ssh_host}", remote_cmd])


def rebuild_local_report() -> None:
    run([sys.executable, str(ROOT / "scripts" / "build_search_console_report.py")])


def main() -> None:
    args = parse_args()
    SearchConsoleConfig, get_credentials, build_service = import_auto_seo_helpers(args.auto_seo_root)

    if not args.skip_remote_pull:
        pull_remote_history(
            ssh_key=args.ssh_key,
            ssh_user=args.ssh_user,
            ssh_host=args.ssh_host,
            remote_root=args.remote_root,
        )

    config = SearchConsoleConfig(
        credentials_file=args.credentials_file,
        token_file=args.token_file,
    )
    creds = get_credentials(config, interactive=False)
    service = build_service(creds)

    daily_rows = normalize_daily(
        query_dimension(
            service,
            site_url=args.site_url,
            start_date=args.start_date,
            end_date=args.end_date,
            dimensions=["date"],
            search_type=args.search_type,
            row_limit=args.row_limit,
        ),
        snapshot_date=args.snapshot_date,
    )
    merge_rows(
        HISTORY_DIR / "daily.csv",
        daily_rows,
        ("date", "snapshot_date"),
        HISTORY_TABLES["daily.csv"][1],
    )

    dimension_specs = {
        "queries.csv": "query",
        "pages.csv": "page",
        "countries.csv": "country",
        "devices.csv": "device",
        "search_appearance.csv": "searchAppearance",
    }
    output_names = {
        "query": "query",
        "page": "page",
        "country": "country",
        "device": "device",
        "searchAppearance": "search_appearance",
    }

    for filename, api_dimension in dimension_specs.items():
        rows = normalize_rows(
            query_dimension(
                service,
                site_url=args.site_url,
                start_date=args.start_date,
                end_date=args.end_date,
                dimensions=[api_dimension],
                search_type=args.search_type,
                row_limit=args.row_limit,
            ),
            dimension_name=output_names[api_dimension],
            snapshot_date=args.snapshot_date,
        )
        merge_rows(
            HISTORY_DIR / filename,
            rows,
            ("snapshot_date", output_names[api_dimension]),
            HISTORY_TABLES[filename][1],
        )

    rebuild_local_report()

    if not args.skip_remote_push:
        push_remote_history(
            ssh_key=args.ssh_key,
            ssh_user=args.ssh_user,
            ssh_host=args.ssh_host,
            remote_root=args.remote_root,
        )

    if not args.skip_remote_load:
        load_remote_grafana(
            ssh_key=args.ssh_key,
            ssh_user=args.ssh_user,
            ssh_host=args.ssh_host,
            remote_root=args.remote_root,
        )

    print(
        "Updated Search Console history and synced Grafana source data "
        f"for snapshot {args.snapshot_date} using {args.start_date} to {args.end_date}."
    )


if __name__ == "__main__":
    main()
