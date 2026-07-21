#!/usr/bin/env python3
"""Generate and optionally load Search Console history into Grafana Postgres."""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACKER_DIR = ROOT / "data" / "search-console"
HISTORY_DIR = TRACKER_DIR / "history"
GRAFANA_DIR = TRACKER_DIR / "grafana"
LOAD_SQL = GRAFANA_DIR / "load_history.sql"
COMPOSE_FILE = ROOT / "docker-compose.grafana.yml"


TABLES = {
    "daily.csv": (
        "search_console_daily",
        ["date", "snapshot_date", "clicks", "impressions", "ctr", "position"],
    ),
    "queries.csv": (
        "search_console_queries",
        ["snapshot_date", "query", "clicks", "impressions", "ctr", "position"],
    ),
    "pages.csv": (
        "search_console_pages",
        ["snapshot_date", "page", "clicks", "impressions", "ctr", "position"],
    ),
    "countries.csv": (
        "search_console_countries",
        ["snapshot_date", "country", "clicks", "impressions", "ctr", "position"],
    ),
    "devices.csv": (
        "search_console_devices",
        ["snapshot_date", "device", "clicks", "impressions", "ctr", "position"],
    ),
    "search_appearance.csv": (
        "search_console_search_appearance",
        ["snapshot_date", "search_appearance", "clicks", "impressions", "ctr", "position"],
    ),
}


def quote_sql(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_value(value: str) -> str:
    if value == "":
        return "NULL"
    return quote_sql(value)


def build_insert(table: str, columns: list[str], row: dict[str, str]) -> str:
    values = ", ".join(sql_value(row[column]) for column in columns)
    column_list = ", ".join(columns)
    return f"INSERT INTO {table} ({column_list}) VALUES ({values});"


def generate_sql() -> int:
    lines = [
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
    ]
    for table, _columns in TABLES.values():
        lines.append(f"TRUNCATE TABLE {table};")

    row_count = 0
    for csv_name, (table, columns) in TABLES.items():
        path = HISTORY_DIR / csv_name
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                lines.append(build_insert(table, columns, row))
                row_count += 1

    lines.extend(["COMMIT;", ""])
    LOAD_SQL.write_text("\n".join(lines), encoding="utf-8")
    return row_count


def load_into_postgres() -> None:
    docker_bin = shutil.which("docker")
    if not docker_bin:
        raise RuntimeError(
            "Docker is not installed or not on PATH. "
            "Install Docker Desktop and make sure `docker` works in your shell, "
            "then rerun: python3 scripts/sync_search_console_grafana.py --load"
        )

    subprocess.run(
        [
            docker_bin,
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "search_console",
            "-d",
            "search_console",
            "-f",
            "/search-console/grafana/load_history.sql",
        ],
        cwd=ROOT,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load", action="store_true", help="Load generated SQL into the running Docker Postgres service")
    args = parser.parse_args()

    row_count = generate_sql()
    print(f"Wrote {LOAD_SQL} with {row_count} rows")
    if args.load:
        try:
            load_into_postgres()
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            raise SystemExit(2)
        except subprocess.CalledProcessError as exc:
            print(
                "ERROR: Docker compose command failed. "
                "Make sure Docker Desktop is running and containers are up:\n"
                "  docker compose -f docker-compose.grafana.yml up -d",
                file=sys.stderr,
            )
            raise SystemExit(exc.returncode)
        print("Loaded Search Console history into Grafana Postgres")


if __name__ == "__main__":
    main()
