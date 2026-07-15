#!/usr/bin/env python3
"""Generate GitHub profile SVG cards from public GitHub data."""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import textwrap
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
USER = "Kalsaria-C"
NOW = dt.date.today()
CURRENT_YEAR = NOW.year
BASE_URL = "https://api.github.com"
OUTPUT_FILES = {
    "overview": ROOT / "github-profile-overview.svg",
    "stats": ROOT / "github-profile-stats.svg",
    "languages": ROOT / "github-profile-languages.svg",
}

COLORS = {
    "bg": "#0d1117",
    "panel": "#111827",
    "border": "#1f2937",
    "title": "#58a6ff",
    "text": "#e5edf5",
    "muted": "#94a3b8",
    "accent": "#1f6feb",
    "accent_soft": "#8b5cf6",
    "success": "#3fb950",
    "heat_0": "#161b22",
    "heat_1": "#0e4429",
    "heat_2": "#006d32",
    "heat_3": "#26a641",
    "heat_4": "#39d353",
}

LANGUAGE_COLORS = {
    "Go": "#00ADD8",
    "Java": "#f89820",
    "Python": "#3572A5",
    "C++": "#f34b7d",
    "C": "#555555",
    "HTML": "#e34c26",
    "HCL": "#844FBA",
    "Shell": "#89e051",
    "Markdown": "#0f172a",
    "Other": "#6b7280",
}

SVG_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'


def request(url: str) -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Kalsaria-C-profile-stats",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def fetch_json(url: str) -> Any:
    with urllib.request.urlopen(request(url)) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(request(url)) as response:
        return response.read().decode("utf-8")


def fetch_bytes(url: str) -> bytes:
    req = request(url)
    req.add_header("Accept", "*/*")
    with urllib.request.urlopen(req) as response:
        return response.read()


def fmt_number(value: int) -> str:
    return f"{value:,}"


def wrap_lines(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)


def month_label(month: int) -> str:
    return dt.date(CURRENT_YEAR, month, 1).strftime("%b")


def extract_contribution_count(html: str) -> int:
    match = re.search(r">\s*([\d,]+)\s+contributions\s+in\s+(\d{4})\s*<", html)
    if not match:
        raise RuntimeError("Could not parse contribution count")
    year = int(match.group(2))
    if year != CURRENT_YEAR:
        raise RuntimeError(f"Expected contribution year {CURRENT_YEAR}, got {year}")
    return int(match.group(1).replace(",", ""))


def extract_contribution_days(html: str) -> list[tuple[dt.date, int]]:
    matches = re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d)"', html)
    days: list[tuple[dt.date, int]] = []
    for date_str, level_str in matches:
        days.append((dt.date.fromisoformat(date_str), int(level_str)))
    return days


def repo_index(repos: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {repo["full_name"]: repo for repo in repos}


def fetch_public_repos() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = fetch_json(f"{BASE_URL}/users/{USER}/repos?per_page=100&page={page}&sort=updated")
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos


def fetch_public_events(limit_pages: int = 3) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for page in range(1, limit_pages + 1):
        batch = fetch_json(f"{BASE_URL}/users/{USER}/events/public?per_page=100&page={page}")
        if not batch:
            break
        events.extend(batch)
        if len(batch) < 100:
            break
    return events


def safe_repo_language(full_name: str, repo_cache: dict[str, dict[str, Any]]) -> str | None:
    repo = repo_cache.get(full_name)
    if repo is None:
        try:
            repo = fetch_json(f"{BASE_URL}/repos/{full_name}")
            repo_cache[full_name] = repo
        except urllib.error.HTTPError:
            return None
    return repo.get("language")


def recent_language_weights(events: list[dict[str, Any]], repo_cache: dict[str, dict[str, Any]]) -> Counter[str]:
    weights = {
        "PushEvent": 1.0,
        "PullRequestEvent": 1.0,
        "PullRequestReviewEvent": 0.8,
        "CreateEvent": 0.4,
    }
    by_language: Counter[str] = Counter()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365)
    for event in events:
        event_type = event.get("type")
        weight = weights.get(event_type)
        if not weight:
            continue
        created_at = dt.datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        if created_at < cutoff:
            continue
        full_name = event["repo"]["name"]
        language = safe_repo_language(full_name, repo_cache)
        if not language:
            continue
        by_language[language] += weight
    return by_language


def render_svg(width: int, height: int, body: str) -> str:
    return (
        SVG_HEADER
        + f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" role="img">'
        + "<defs>"
        + f'<linearGradient id="frame" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{COLORS["accent"]}"/><stop offset="100%" stop-color="{COLORS["accent_soft"]}"/></linearGradient>'
        + f'<linearGradient id="chip" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#12233d"/><stop offset="100%" stop-color="#111827"/></linearGradient>'
        + "</defs>"
        + body
        + "</svg>\n"
    )


def render_overview_card(user: dict[str, Any], contribution_count: int, contribution_days: list[tuple[dt.date, int]], avatar_data_uri: str) -> str:
    width, height = 1200, 360
    start = dt.date(CURRENT_YEAR, 1, 1)
    calendar_start = start - dt.timedelta(days=(start.weekday() + 1) % 7)
    heat_x = 730
    heat_y = 86
    cell = 12
    gap = 4
    heat_colors = {
        0: COLORS["heat_0"],
        1: COLORS["heat_1"],
        2: COLORS["heat_2"],
        3: COLORS["heat_3"],
        4: COLORS["heat_4"],
    }

    heatmap_cells: list[str] = []
    for day, level in contribution_days:
        week = (day - calendar_start).days // 7
        dow = (day.weekday() + 1) % 7
        x = heat_x + week * (cell + gap)
        y = heat_y + dow * (cell + gap)
        heatmap_cells.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{heat_colors.get(level, COLORS["heat_0"])}" />'
        )

    month_labels = []
    for month in range(1, 13):
        month_start = dt.date(CURRENT_YEAR, month, 1)
        week = (month_start - calendar_start).days // 7
        x = heat_x + week * (cell + gap)
        month_labels.append(
            f'<text x="{x}" y="{heat_y - 16}" fill="{COLORS["muted"]}" font-size="12">{month_label(month)}</text>'
        )

    overview_items = [
        ("Contributions", f"{fmt_number(contribution_count)} in {CURRENT_YEAR}"),
        ("Public repos", fmt_number(user["public_repos"])),
        ("Followers", fmt_number(user["followers"])),
        ("Joined", dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")).strftime("%b %Y")),
    ]

    chips = ["Go", "Java", "OCI", "Distributed Systems"]
    chip_svg = []
    chip_x = 220
    for chip in chips:
        chip_width = 24 + len(chip) * 9
        chip_svg.append(
            f'<g transform="translate({chip_x},182)"><rect width="{chip_width}" height="34" rx="17" fill="url(#chip)" stroke="{COLORS["border"]}"/><text x="{chip_width / 2}" y="22" text-anchor="middle" fill="{COLORS["text"]}" font-size="15" font-weight="600">{escape(chip)}</text></g>'
        )
        chip_x += chip_width + 12

    stat_svg = []
    stat_x = 220
    for label, value in overview_items:
        stat_svg.append(
            f'<text x="{stat_x}" y="260" fill="{COLORS["muted"]}" font-size="14">{escape(label)}</text>'
            f'<text x="{stat_x}" y="288" fill="{COLORS["text"]}" font-size="22" font-weight="700">{escape(value)}</text>'
        )
        stat_x += 120 if label == "Followers" else 170

    bio_lines = wrap_lines("Backend engineer building reliable observability and ingestion systems with Go, Java, and OCI.", 46)
    bio_svg = []
    for idx, line in enumerate(bio_lines):
        bio_svg.append(
            f'<text x="220" y="{142 + idx * 24}" fill="{COLORS["muted"]}" font-size="18">{escape(line)}</text>'
        )

    body = f"""
<rect width="{width}" height="{height}" rx="28" fill="{COLORS["bg"]}" />
<rect x="1.5" y="1.5" width="{width - 3}" height="{height - 3}" rx="26.5" stroke="url(#frame)" stroke-opacity="0.85" stroke-width="3" />
<rect x="26" y="26" width="{width - 52}" height="{height - 52}" rx="24" fill="{COLORS["panel"]}" stroke="{COLORS["border"]}" />
<circle cx="130" cy="118" r="62" fill="{COLORS["bg"]}" stroke="{COLORS["accent"]}" stroke-width="4" />
<image href="{avatar_data_uri}" x="68" y="56" width="124" height="124" clip-path="inset(0 round 62px)" />
<text x="220" y="86" fill="{COLORS["title"]}" font-size="38" font-weight="700">{escape(user["name"] or USER)}</text>
<text x="220" y="116" fill="{COLORS["text"]}" font-size="18">@{escape(USER)} • Bengaluru, India</text>
{''.join(bio_svg)}
{''.join(chip_svg)}
{''.join(stat_svg)}
<text x="{heat_x}" y="44" fill="{COLORS["title"]}" font-size="24" font-weight="700">Contribution Heatmap</text>
<text x="{heat_x}" y="66" fill="{COLORS["muted"]}" font-size="14">Public GitHub activity in {CURRENT_YEAR}</text>
{''.join(month_labels)}
{''.join(heatmap_cells)}
<text x="{heat_x}" y="318" fill="{COLORS["muted"]}" font-size="12">Less</text>
<rect x="{heat_x + 38}" y="306" width="12" height="12" rx="3" fill="{COLORS["heat_0"]}" />
<rect x="{heat_x + 56}" y="306" width="12" height="12" rx="3" fill="{COLORS["heat_1"]}" />
<rect x="{heat_x + 74}" y="306" width="12" height="12" rx="3" fill="{COLORS["heat_2"]}" />
<rect x="{heat_x + 92}" y="306" width="12" height="12" rx="3" fill="{COLORS["heat_3"]}" />
<rect x="{heat_x + 110}" y="306" width="12" height="12" rx="3" fill="{COLORS["heat_4"]}" />
<text x="{heat_x + 130}" y="318" fill="{COLORS["muted"]}" font-size="12">More</text>
"""
    return render_svg(width, height, body)


def render_stats_card(user: dict[str, Any], repos: list[dict[str, Any]], contribution_count: int) -> str:
    width, height = 590, 300
    total_stars = sum(repo.get("stargazers_count", 0) for repo in repos)
    total_forks = sum(repo.get("forks_count", 0) for repo in repos)
    latest_repo = max(repos, key=lambda repo: repo.get("pushed_at") or "")
    latest_repo_name = latest_repo["name"]
    latest_repo_date = dt.datetime.fromisoformat(latest_repo["pushed_at"].replace("Z", "+00:00")).strftime("%d %b %Y")

    rows = [
        ("Contributions", f"{fmt_number(contribution_count)} in {CURRENT_YEAR}"),
        ("Public repositories", fmt_number(user["public_repos"])),
        ("Followers / Following", f'{fmt_number(user["followers"])} / {fmt_number(user["following"])}'),
        ("Total stars / Forks", f"{fmt_number(total_stars)} / {fmt_number(total_forks)}"),
        ("Latest active repo", latest_repo_name),
        ("Last public push", latest_repo_date),
    ]

    row_svg = []
    for idx, (label, value) in enumerate(rows):
        y = 84 + idx * 34
        row_svg.append(
            f'<text x="36" y="{y}" fill="{COLORS["muted"]}" font-size="15">{escape(label)}</text>'
            f'<text x="554" y="{y}" text-anchor="end" fill="{COLORS["text"]}" font-size="16" font-weight="700">{escape(value)}</text>'
        )

    body = f"""
<rect width="{width}" height="{height}" rx="24" fill="{COLORS["bg"]}" />
<rect x="1.5" y="1.5" width="{width - 3}" height="{height - 3}" rx="22.5" stroke="url(#frame)" stroke-width="3" stroke-opacity="0.85" />
<rect x="22" y="22" width="{width - 44}" height="{height - 44}" rx="18" fill="{COLORS["panel"]}" stroke="{COLORS["border"]}" />
<text x="36" y="56" fill="{COLORS["title"]}" font-size="28" font-weight="700">GitHub Snapshot</text>
<text x="36" y="74" fill="{COLORS["muted"]}" font-size="13">Current public profile data</text>
{''.join(row_svg)}
"""
    return render_svg(width, height, body)


def render_languages_card(language_weights: Counter[str], events: list[dict[str, Any]]) -> str:
    width, height = 590, 300
    top_languages = language_weights.most_common(4) or [("Go", 1.0)]
    max_value = top_languages[0][1]

    recent_repos: list[str] = []
    seen = set()
    for event in events:
        name = event["repo"]["name"]
        if name in seen:
            continue
        seen.add(name)
        recent_repos.append(name)
        if len(recent_repos) == 3:
            break

    bars = []
    for idx, (language, value) in enumerate(top_languages):
        y = 88 + idx * 44
        color = LANGUAGE_COLORS.get(language, LANGUAGE_COLORS["Other"])
        bar_width = max(70, int((value / max_value) * 280))
        bars.append(
            f'<text x="36" y="{y}" fill="{COLORS["text"]}" font-size="16" font-weight="700">{escape(language)}</text>'
            f'<rect x="210" y="{y - 14}" width="300" height="14" rx="7" fill="{COLORS["border"]}" />'
            f'<rect x="210" y="{y - 14}" width="{bar_width}" height="14" rx="7" fill="{color}" />'
            f'<text x="528" y="{y}" text-anchor="end" fill="{COLORS["muted"]}" font-size="14">{value:.1f}</text>'
        )

    repo_lines = []
    for idx, repo in enumerate(recent_repos):
        repo_lines.append(
            f'<text x="36" y="{252 + idx * 16}" fill="{COLORS["muted"]}" font-size="12">{escape(repo)}</text>'
        )

    body = f"""
<rect width="{width}" height="{height}" rx="24" fill="{COLORS["bg"]}" />
<rect x="1.5" y="1.5" width="{width - 3}" height="{height - 3}" rx="22.5" stroke="url(#frame)" stroke-width="3" stroke-opacity="0.85" />
<rect x="22" y="22" width="{width - 44}" height="{height - 44}" rx="18" fill="{COLORS["panel"]}" stroke="{COLORS["border"]}" />
<text x="36" y="56" fill="{COLORS["title"]}" font-size="28" font-weight="700">Recent Contribution Languages</text>
<text x="36" y="74" fill="{COLORS["muted"]}" font-size="13">Weighted from recent public push and pull request activity</text>
{''.join(bars)}
<text x="36" y="232" fill="{COLORS["muted"]}" font-size="12">Recent public repos</text>
{''.join(repo_lines)}
"""
    return render_svg(width, height, body)


def main() -> None:
    user = fetch_json(f"{BASE_URL}/users/{USER}")
    repos = fetch_public_repos()
    events = fetch_public_events()
    contribution_html = fetch_text(
        f"https://github.com/users/{USER}/contributions?from={CURRENT_YEAR}-01-01&to={CURRENT_YEAR}-12-31"
    )
    contribution_count = extract_contribution_count(contribution_html)
    contribution_days = extract_contribution_days(contribution_html)
    avatar_bytes = fetch_bytes(user["avatar_url"])
    avatar_data_uri = "data:image/png;base64," + base64.b64encode(avatar_bytes).decode("ascii")

    repo_cache = repo_index(repos)
    language_weights = recent_language_weights(events, repo_cache)

    OUTPUT_FILES["overview"].write_text(
        render_overview_card(user, contribution_count, contribution_days, avatar_data_uri),
        encoding="utf-8",
    )
    OUTPUT_FILES["stats"].write_text(
        render_stats_card(user, repos, contribution_count),
        encoding="utf-8",
    )
    OUTPUT_FILES["languages"].write_text(
        render_languages_card(language_weights, events),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
