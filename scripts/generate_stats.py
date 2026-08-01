#!/usr/bin/env python3
"""
Generate assets/languages.svg and assets/rhythm.svg from live GitHub data.

Runs inside GitHub Actions (uses GITHUB_TOKEN). No third-party services.
- languages.svg : stacked bar of bytes written per language across original repos
- rhythm.svg    : 7x24 heatmap of commit activity (from the punch-card API)

Usage: GITHUB_TOKEN=... python3 scripts/generate_stats.py
"""

import json
import os
import sys
import time
import urllib.request

USER = "imanaswer"
API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Brand palette (legible on both light and dark GitHub themes)
ACCENT = "#9d71fa"
TEXT = "#8b949e"        # neutral gray, readable on both themes
BRIGHT = "#a78bfa"
LANG_COLORS = [
    "#9d71fa", "#7c3aed", "#c4b5fd", "#6d28d9",
    "#b45aff", "#8b5cf6", "#5b21b6", "#d8b4fe",
]

DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def gh(url):
    req = urllib.request.Request(url)
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read().decode())


def get_repos():
    repos, page = [], 1
    while True:
        _, batch = gh(f"{API}/users/{USER}/repos?per_page=100&page={page}")
        if not batch:
            break
        repos += batch
        page += 1
    return repos


def get_languages(repos):
    totals = {}
    for r in repos:
        if r["fork"]:
            continue
        try:
            _, langs = gh(r["languages_url"])
        except Exception:
            continue
        for lang, byte_count in langs.items():
            totals[lang] = totals.get(lang, 0) + byte_count
    return totals


def get_punchcard(repos):
    """Aggregate 7x24 commit counts across original repos."""
    grid = [[0] * 24 for _ in range(7)]
    for r in repos:
        if r["fork"]:
            continue
        url = f"{API}/repos/{USER}/{r['name']}/stats/punch_card"
        for attempt in range(3):
            try:
                status, data = gh(url)
            except Exception:
                break
            if status == 202 or not isinstance(data, list):
                time.sleep(2)  # GitHub is computing stats; retry
                continue
            for day, hour, count in data:
                grid[day][hour] += count
            break
    return grid


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def languages_svg(totals, n_original, n_public):
    total_bytes = sum(totals.values()) or 1
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
    other = total_bytes - sum(v for _, v in top)

    W, H = 840, 130
    bar_x, bar_y, bar_w, bar_h, radius = 20, 58, W - 40, 14, 7

    parts = [
        f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace,SFMono-Regular,Menlo,monospace">',
        f'<text x="20" y="28" font-size="15" font-weight="700" fill="{BRIGHT}">Languages by bytes written</text>',
        f'<text x="{W-20}" y="28" font-size="11" fill="{TEXT}" text-anchor="end">'
        f'{n_original} original repos · {n_public} public · {len(totals)} languages</text>',
        f'<clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{radius}"/></clipPath>',
        f'<g clip-path="url(#bar)">',
    ]

    x = bar_x
    segments = top + ([("Other", other)] if other > 0 else [])
    for i, (lang, byte_count) in enumerate(segments):
        w = bar_w * byte_count / total_bytes
        color = LANG_COLORS[i % len(LANG_COLORS)] if lang != "Other" else "#4b5563"
        parts.append(f'<rect x="{x:.1f}" y="{bar_y}" width="{max(w,1):.1f}" height="{bar_h}" fill="{color}"/>')
        x += w
    parts.append("</g>")

    # legend
    lx, ly = 20.0, 96
    for i, (lang, byte_count) in enumerate(segments):
        pct = 100 * byte_count / total_bytes
        color = LANG_COLORS[i % len(LANG_COLORS)] if lang != "Other" else "#4b5563"
        label = f"{esc(lang)} {pct:.0f}%"
        parts.append(f'<circle cx="{lx+5:.1f}" cy="{ly-4}" r="5" fill="{color}"/>')
        parts.append(f'<text x="{lx+16:.1f}" y="{ly}" font-size="12" fill="{TEXT}">{label}</text>')
        lx += 16 + 7.5 * len(label) + 22

    parts.append("</svg>")
    return "\n".join(parts)


def rhythm_svg(grid):
    total = sum(sum(row) for row in grid) or 1
    peak = max(max(row) for row in grid) or 1

    # headline numbers
    hour_totals = [sum(grid[d][h] for d in range(7)) for h in range(24)]
    busiest_hour = hour_totals.index(max(hour_totals))
    late = sum(hour_totals[h] for h in [22, 23, 0, 1, 2]) / total * 100

    def hour_label(h):
        if h == 0:
            return "12am"
        if h < 12:
            return f"{h}am"
        if h == 12:
            return "12pm"
        return f"{h-12}pm"

    cell, gap = 26, 4
    left, top = 62, 56
    W = left + 24 * (cell + gap) + 20
    H = top + 7 * (cell + gap) + 44

    parts = [
        f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace,SFMono-Regular,Menlo,monospace">',
        f'<text x="20" y="28" font-size="15" font-weight="700" fill="{BRIGHT}">When I commit</text>',
        f'<text x="{W-20}" y="28" font-size="11" fill="{TEXT}" text-anchor="end">'
        f'busiest hour {hour_label(busiest_hour)} · {late:.0f}% of commits land 10pm–3am</text>',
    ]

    for d in range(7):
        y = top + d * (cell + gap)
        parts.append(f'<text x="{left-10}" y="{y+cell/2+4}" font-size="11" fill="{TEXT}" text-anchor="end">{DAYS[d]}</text>')
        for h in range(24):
            x = left + h * (cell + gap)
            v = grid[d][h]
            if v == 0:
                parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="5" fill="{TEXT}" opacity="0.12"/>')
            else:
                opacity = 0.25 + 0.75 * (v / peak)
                parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="5" fill="{ACCENT}" opacity="{opacity:.2f}"/>')

    ly = top + 7 * (cell + gap) + 18
    for h in [0, 6, 12, 18, 23]:
        x = left + h * (cell + gap)
        parts.append(f'<text x="{x}" y="{ly}" font-size="11" fill="{TEXT}">{hour_label(h)}</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    repos = get_repos()
    originals = [r for r in repos if not r["fork"]]

    totals = get_languages(repos)
    grid = get_punchcard(repos)

    os.makedirs("assets", exist_ok=True)
    with open("assets/languages.svg", "w") as f:
        f.write(languages_svg(totals, len(originals), len(repos)))
    with open("assets/rhythm.svg", "w") as f:
        f.write(rhythm_svg(grid))
    print(f"Wrote assets/languages.svg ({len(totals)} languages) and assets/rhythm.svg", file=sys.stderr)


if __name__ == "__main__":
    main()
