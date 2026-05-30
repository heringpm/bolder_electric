# Search Console Tracker

This folder keeps Google Search Console Performance exports for Bolder Electric.

## Current Workflow

1. Export Performance data from Google Search Console as a ZIP.
2. Save the ZIP in `data/search-console/exports/`.
3. Import it:

```bash
python3 scripts/import_search_console_export.py data/search-console/exports/YOUR_EXPORT.zip
```

If the filename does not include the export date, pass one explicitly:

```bash
python3 scripts/import_search_console_export.py data/search-console/exports/YOUR_EXPORT.zip --snapshot-date 2026-05-05
```

4. Rebuild the chart report:

```bash
python3 scripts/build_search_console_report.py
```

## Automated Grafana Sync

To refresh local Search Console history from the API, push it to the Grafana server, and reload the remote Postgres datasource in one run:

```bash
/Users/osx/Documents/Projects/auto-seo/.venv/bin/python scripts/update_search_console_grafana_remote.py
```

The script will:

1. Pull the current server-side history CSVs first so newer remote snapshots are not overwritten.
2. Append a fresh Search Console snapshot for the latest complete 7-day window.
3. Rebuild `report.html`.
4. Push the merged history CSVs back to the server.
5. Run the existing remote Grafana loader to repopulate Postgres.

Defaults are set for the current Bolder Electric stack:

- Search Console property: `sc-domain:bolderelectric.com`
- SSH target: `root@192.168.111.138`
- Remote app root: `/root/bolder-electric`

## Files

- `exports/`: raw Google Search Console ZIP exports.
- `snapshots/YYYY-MM-DD/`: the original CSV files extracted from each export.
- `history/daily.csv`: daily clicks, impressions, CTR, and average position.
- `history/queries.csv`: query-level snapshot history.
- `history/pages.csv`: page-level snapshot history.
- `history/countries.csv`: country snapshot history.
- `history/devices.csv`: device snapshot history.
- `history/search_appearance.csv`: search appearance snapshot history.
- `report.html`: static visual report with trend and query charts.

CTR is stored as a decimal value, so `0.0769` means `7.69%`.
