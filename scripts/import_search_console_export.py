#!/usr/bin/env python3
"""Import a Google Search Console Performance export into local history CSVs."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import zipfile
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACKER_DIR = ROOT / "data" / "search-console"
HISTORY_DIR = TRACKER_DIR / "history"
SNAPSHOT_DIR = TRACKER_DIR / "snapshots"


def parse_percent(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.endswith("%"):
        return f"{float(value[:-1]) / 100:.6f}".rstrip("0").rstrip(".")
    return value


def parse_export_date(path: Path) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if match:
        return match.group(1)
    return date.today().isoformat()


def read_csv_from_zip(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with zf.open(name) as handle:
        text = handle.read().decode("utf-8-sig").splitlines()
    return list(csv.DictReader(text))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def merge_rows(path: Path, rows: list[dict[str, str]], key_fields: tuple[str, ...], fieldnames: list[str]) -> None:
    existing: dict[tuple[str, ...], dict[str, str]] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                existing[tuple(row[field] for field in key_fields)] = row

    for row in rows:
        existing[tuple(row[field] for field in key_fields)] = row

    sorted_rows = sorted(existing.values(), key=lambda row: tuple(row[field] for field in key_fields))
    write_csv(path, sorted_rows, fieldnames)


def normalize_metric_rows(rows: list[dict[str, str]], dimension_name: str, export_date: str) -> list[dict[str, str]]:
    normalized = []
    metric_fields = {"Clicks", "Impressions", "CTR", "Position"}
    source_field = next((field for field in rows[0].keys() if field not in metric_fields), "") if rows else ""
    for row in rows:
        normalized.append(
            {
                "snapshot_date": export_date,
                dimension_name: row[source_field],
                "clicks": row["Clicks"],
                "impressions": row["Impressions"],
                "ctr": parse_percent(row["CTR"]),
                "position": row["Position"],
            }
        )
    return normalized


def import_export(zip_path: Path, export_date: str) -> None:
    snapshot_path = SNAPSHOT_DIR / export_date
    snapshot_path.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            target = snapshot_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)

        daily_rows = []
        for row in read_csv_from_zip(zf, "Chart.csv"):
            daily_rows.append(
                {
                    "date": row["Date"],
                    "snapshot_date": export_date,
                    "clicks": row["Clicks"],
                    "impressions": row["Impressions"],
                    "ctr": parse_percent(row["CTR"]),
                    "position": row["Position"],
                }
            )

        merge_rows(
            HISTORY_DIR / "daily.csv",
            daily_rows,
            ("date", "snapshot_date"),
            ["date", "snapshot_date", "clicks", "impressions", "ctr", "position"],
        )

        dimension_files = {
            "Queries.csv": ("query", HISTORY_DIR / "queries.csv"),
            "Pages.csv": ("page", HISTORY_DIR / "pages.csv"),
            "Countries.csv": ("country", HISTORY_DIR / "countries.csv"),
            "Devices.csv": ("device", HISTORY_DIR / "devices.csv"),
            "Search appearance.csv": ("search_appearance", HISTORY_DIR / "search_appearance.csv"),
        }
        for source_name, (dimension_name, output_path) in dimension_files.items():
            rows = normalize_metric_rows(read_csv_from_zip(zf, source_name), dimension_name, export_date)
            merge_rows(
                output_path,
                rows,
                ("snapshot_date", dimension_name),
                ["snapshot_date", dimension_name, "clicks", "impressions", "ctr", "position"],
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", type=Path, help="Google Search Console export ZIP")
    parser.add_argument("--snapshot-date", default=None, help="Date to assign to this export, YYYY-MM-DD")
    args = parser.parse_args()

    zip_path = args.zip_path.expanduser().resolve()
    export_date = args.snapshot_date or parse_export_date(zip_path)
    import_export(zip_path, export_date)
    print(f"Imported {zip_path.name} as snapshot {export_date}")


if __name__ == "__main__":
    main()
