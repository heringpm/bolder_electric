#!/usr/bin/env python3
"""Migrate data from local SQLite DB into PostgreSQL.

Usage:
  DATABASE_URL=postgresql://... python3 scripts/migrate_sqlite_to_postgres.py
  python3 scripts/migrate_sqlite_to_postgres.py --sqlite bolder_electric.db --postgres postgresql://...
"""

import argparse
import os
import sqlite3

try:
    import psycopg2
except Exception as exc:
    raise SystemExit(f"psycopg2 is required: {exc}")


def table_exists_sqlite(conn, table):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def fetch_rows(sqlite_conn, table):
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    if not rows:
        return [], []
    cols = list(rows[0].keys())
    vals = [tuple(row[col] for col in cols) for row in rows]
    return cols, vals


def reset_postgres_table(pg_cur, table):
    pg_cur.execute(f'TRUNCATE TABLE {table} RESTART IDENTITY CASCADE')


def insert_rows(pg_cur, table, cols, rows):
    if not rows:
        return
    placeholders = ', '.join(['%s'] * len(cols))
    col_list = ', '.join(cols)
    query = f'INSERT INTO {table} ({col_list}) VALUES ({placeholders})'
    pg_cur.executemany(query, rows)


def reset_sequence(pg_cur, table):
    pg_cur.execute(
        """
        SELECT pg_get_serial_sequence(%s, 'id')
        """,
        (table,)
    )
    seq = pg_cur.fetchone()[0]
    if seq:
        pg_cur.execute(
            f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sqlite', default='bolder_electric.db')
    parser.add_argument('--postgres', default=os.environ.get('DATABASE_URL', ''))
    args = parser.parse_args()

    if not args.postgres:
        raise SystemExit('PostgreSQL connection string is required via --postgres or DATABASE_URL.')

    tables = [
        'admin_users',
        'access_logs',
        'contact_info',
        'contact_submissions',
        'services',
        'time_slots',
        'availability',
        'bookings',
        'gallery_photos',
    ]

    sqlite_conn = sqlite3.connect(args.sqlite)
    pg_conn = psycopg2.connect(args.postgres)

    try:
        pg_cur = pg_conn.cursor()
        for table in tables:
            if not table_exists_sqlite(sqlite_conn, table):
                print(f'Skipping {table}: not found in SQLite.')
                continue

            cols, rows = fetch_rows(sqlite_conn, table)
            reset_postgres_table(pg_cur, table)
            insert_rows(pg_cur, table, cols, rows)
            reset_sequence(pg_cur, table)
            print(f'Migrated {table}: {len(rows)} row(s)')

        pg_conn.commit()
        print('Migration complete.')
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == '__main__':
    main()
