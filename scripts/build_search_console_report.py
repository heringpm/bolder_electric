#!/usr/bin/env python3
"""Build a static HTML report from Search Console history CSVs."""

from __future__ import annotations

import csv
import html
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACKER_DIR = ROOT / "data" / "search-console"
HISTORY_DIR = TRACKER_DIR / "history"
REPORT_PATH = TRACKER_DIR / "report.html"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_int(value: str) -> int:
    return int(float(value or 0))


def as_float(value: str) -> float:
    return float(value or 0)


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def fmt_num(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def scale(value: float, min_value: float, max_value: float, low: float, high: float) -> float:
    if max_value == min_value:
        return (low + high) / 2
    return low + ((value - min_value) / (max_value - min_value)) * (high - low)


def points(values: list[float], width: int, height: int, padding: int, invert: bool = False) -> str:
    if not values:
        return ""
    min_value = min(values)
    max_value = max(values)
    coords = []
    for index, value in enumerate(values):
        x = scale(index, 0, max(len(values) - 1, 1), padding, width - padding)
        y = scale(value, min_value, max_value, padding, height - padding)
        if not invert:
            y = height - y
        coords.append(f"{x:.1f},{y:.1f}")
    return " ".join(coords)


def daily_chart(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No daily data yet.</p>"

    width = 920
    height = 320
    padding = 44
    impressions = [as_int(row["impressions"]) for row in rows]
    clicks = [as_int(row["clicks"]) for row in rows]
    positions = [as_float(row["position"]) for row in rows]
    max_impressions = max(max(impressions), 1)
    bar_width = max(18, (width - padding * 2) / len(rows) * 0.58)
    bars = []
    labels = []
    for index, row in enumerate(rows):
        x = scale(index, 0, max(len(rows) - 1, 1), padding, width - padding)
        bar_height = scale(as_int(row["impressions"]), 0, max_impressions, 0, height - padding * 2)
        y = height - padding - bar_height
        bars.append(
            f'<rect x="{x - bar_width / 2:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
            f'height="{bar_height:.1f}" rx="3"><title>{html.escape(row["date"])}: '
            f'{row["impressions"]} impressions, {row["clicks"]} clicks, position {row["position"]}</title></rect>'
        )
        labels.append(f'<text x="{x:.1f}" y="{height - 14}" text-anchor="middle">{html.escape(row["date"][5:])}</text>')

    click_line = points(clicks, width, height, padding)
    position_line = points(positions, width, height, padding, invert=True)
    return f"""
    <svg class="chart daily-chart" viewBox="0 0 {width} {height}" role="img" aria-label="Daily impressions, clicks, and position">
      <line class="axis" x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" />
      <line class="axis" x1="{padding}" y1="{padding}" x2="{padding}" y2="{height - padding}" />
      <g class="bars">{''.join(bars)}</g>
      <polyline class="click-line" points="{click_line}" />
      <polyline class="position-line" points="{position_line}" />
      <g class="x-labels">{''.join(labels)}</g>
    </svg>
    """


def query_chart(rows: list[dict[str, str]], limit: int = 10) -> str:
    if not rows:
        return "<p>No query data yet.</p>"

    top_rows = sorted(rows, key=lambda row: (as_int(row["impressions"]), as_int(row["clicks"])), reverse=True)[:limit]
    max_impressions = max(as_int(row["impressions"]) for row in top_rows) or 1
    items = []
    for row in top_rows:
        width = as_int(row["impressions"]) / max_impressions * 100
        items.append(
            f"""
            <div class="query-row">
              <div class="query-label">{html.escape(row["query"])}</div>
              <div class="query-track"><span style="width: {width:.1f}%"></span></div>
              <div class="query-metric">{row["impressions"]} impr</div>
              <div class="query-metric">{row["clicks"]} clicks</div>
              <div class="query-metric">pos {fmt_num(as_float(row["position"]))}</div>
            </div>
            """
        )
    return "".join(items)


def latest_snapshot(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    return max(row["snapshot_date"] for row in rows)


def rows_for_snapshot(rows: list[dict[str, str]], snapshot_date: str) -> list[dict[str, str]]:
    return [row for row in rows if row.get("snapshot_date") == snapshot_date]


def previous_snapshot(rows: list[dict[str, str]], snapshot_date: str) -> str:
    snapshots = sorted({row["snapshot_date"] for row in rows if row.get("snapshot_date")})
    try:
        index = snapshots.index(snapshot_date)
    except ValueError:
        return ""
    return snapshots[index - 1] if index > 0 else ""


def snapshot_summary(rows: list[dict[str, str]]) -> dict[str, float]:
    clicks = sum(as_int(row["clicks"]) for row in rows)
    impressions = sum(as_int(row["impressions"]) for row in rows)
    ctr = clicks / impressions if impressions else 0
    position = sum(as_float(row["position"]) for row in rows) / len(rows) if rows else 0
    return {"clicks": clicks, "impressions": impressions, "ctr": ctr, "position": position}


def delta_text(current: float, previous: float, suffix: str = "", lower_is_better: bool = False) -> str:
    if previous == 0 and current == 0:
        return "no change"
    if previous == 0:
        return "new"
    delta = current - previous
    direction = "better" if (delta < 0 and lower_is_better) or (delta > 0 and not lower_is_better) else "worse"
    sign = "+" if delta > 0 else ""
    return f"{sign}{fmt_num(delta)}{suffix} {direction}"


def point_delta_text(current: float, previous: float) -> str:
    delta = (current - previous) * 100
    sign = "+" if delta > 0 else ""
    direction = "better" if delta > 0 else "worse" if delta < 0 else "no change"
    return f"{sign}{fmt_num(delta)} pts {direction}" if delta else direction


def comparison_panel(current: dict[str, float], previous: dict[str, float], previous_date: str) -> str:
    if not previous_date:
        return ""
    return f"""
    <section>
      <h2>Compared With Previous Snapshot</h2>
      <div class="comparison-grid">
        <div><span>Clicks</span><strong>{fmt_num(current["clicks"])} vs {fmt_num(previous["clicks"])}</strong><em>{delta_text(current["clicks"], previous["clicks"])}</em></div>
        <div><span>Impressions</span><strong>{fmt_num(current["impressions"])} vs {fmt_num(previous["impressions"])}</strong><em>{delta_text(current["impressions"], previous["impressions"])}</em></div>
        <div><span>CTR</span><strong>{fmt_pct(current["ctr"])} vs {fmt_pct(previous["ctr"])}</strong><em>{point_delta_text(current["ctr"], previous["ctr"])}</em></div>
        <div><span>Avg position</span><strong>{fmt_num(current["position"])} vs {fmt_num(previous["position"])}</strong><em>{delta_text(current["position"], previous["position"], lower_is_better=True)}</em></div>
      </div>
      <p class="page-note">Previous snapshot: {html.escape(previous_date)}</p>
    </section>
    """


def build_report() -> str:
    daily = read_csv(HISTORY_DIR / "daily.csv")
    queries = read_csv(HISTORY_DIR / "queries.csv")
    pages = read_csv(HISTORY_DIR / "pages.csv")

    latest_date = latest_snapshot(daily)
    previous_date = previous_snapshot(daily, latest_date)
    latest_daily = rows_for_snapshot(daily, latest_date)
    previous_daily = rows_for_snapshot(daily, previous_date)
    latest_queries = rows_for_snapshot(queries, latest_date)
    latest_pages = rows_for_snapshot(pages, latest_date)
    latest_summary = snapshot_summary(latest_daily)
    previous_summary = snapshot_summary(previous_daily)
    best_page = max(latest_pages, key=lambda row: as_int(row["impressions"]), default={})

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bolder Electric Search Console Report</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #202124;
      --muted: #5f6368;
      --line: #dadce0;
      --panel: #ffffff;
      --bg: #f8fafd;
      --blue: #1a73e8;
      --green: #188038;
      --amber: #f9ab00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }}
    header {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 18px;
    }}
    h1, h2 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 18px; margin-bottom: 14px; }}
    .subhead {{ color: var(--muted); margin-top: 4px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .metric, section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .metric {{ padding: 14px; }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .metric strong {{ font-size: 24px; }}
    section {{ padding: 18px; margin-top: 16px; }}
    .comparison-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .comparison-grid div {{
      border: 1px solid #eef1f4;
      border-radius: 8px;
      padding: 12px;
    }}
    .comparison-grid span, .comparison-grid em {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-style: normal;
    }}
    .comparison-grid strong {{
      display: block;
      font-size: 18px;
      margin: 4px 0;
    }}
    .legend {{
      display: flex;
      gap: 18px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .legend span::before {{
      content: "";
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 2px;
      margin-right: 6px;
      vertical-align: -1px;
      background: var(--blue);
    }}
    .legend .clicks::before {{ background: var(--green); }}
    .legend .position::before {{ background: var(--amber); }}
    .chart {{ width: 100%; height: auto; display: block; }}
    .axis {{ stroke: var(--line); stroke-width: 1; }}
    .bars rect {{ fill: rgba(26, 115, 232, 0.22); stroke: rgba(26, 115, 232, 0.45); }}
    .click-line, .position-line {{
      fill: none;
      stroke-width: 3;
      stroke-linecap: round;
      stroke-linejoin: round;
    }}
    .click-line {{ stroke: var(--green); }}
    .position-line {{ stroke: var(--amber); }}
    .x-labels text {{ fill: var(--muted); font-size: 12px; }}
    .query-row {{
      display: grid;
      grid-template-columns: minmax(190px, 1.4fr) minmax(120px, 2fr) 78px 70px 68px;
      align-items: center;
      gap: 10px;
      min-height: 34px;
      border-top: 1px solid #eef1f4;
    }}
    .query-row:first-child {{ border-top: 0; }}
    .query-label {{ overflow-wrap: anywhere; }}
    .query-track {{
      height: 10px;
      background: #edf2f7;
      border-radius: 999px;
      overflow: hidden;
    }}
    .query-track span {{
      display: block;
      height: 100%;
      background: var(--blue);
    }}
    .query-metric {{ color: var(--muted); font-size: 13px; text-align: right; }}
    .page-note {{ color: var(--muted); margin: 0; }}
    @media (max-width: 760px) {{
      header {{ display: block; }}
      .grid, .comparison-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .query-row {{
        grid-template-columns: 1fr;
        gap: 4px;
        padding: 10px 0;
      }}
      .query-metric {{ text-align: left; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Bolder Electric Search Console Report</h1>
        <div class="subhead">Latest snapshot: {html.escape(latest_date or "none")}</div>
      </div>
      <div class="subhead">{len(daily)} daily data points</div>
    </header>

    <div class="grid">
      <div class="metric"><span>Latest clicks</span><strong>{fmt_num(latest_summary["clicks"])}</strong></div>
      <div class="metric"><span>Latest impressions</span><strong>{fmt_num(latest_summary["impressions"])}</strong></div>
      <div class="metric"><span>Latest CTR</span><strong>{fmt_pct(latest_summary["ctr"])}</strong></div>
      <div class="metric"><span>Latest avg position</span><strong>{fmt_num(latest_summary["position"])}</strong></div>
    </div>

    {comparison_panel(latest_summary, previous_summary, previous_date)}

    <section>
      <h2>Daily Trend</h2>
      <div class="legend">
        <span>Impressions</span>
        <span class="clicks">Clicks</span>
        <span class="position">Position, lower is better</span>
      </div>
      {daily_chart(daily)}
    </section>

    <section>
      <h2>Latest Top Queries By Impressions</h2>
      {query_chart(latest_queries)}
    </section>

    <section>
      <h2>Highest-Impression Page</h2>
      <p class="page-note">{html.escape(best_page.get("page", "No page data yet"))}</p>
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    REPORT_PATH.write_text(build_report(), encoding="utf-8")
    print(f"Built {REPORT_PATH}")


if __name__ == "__main__":
    main()
