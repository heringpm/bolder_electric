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
