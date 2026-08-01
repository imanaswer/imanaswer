#!/usr/bin/env python3
"""
Generate assets/languages.svg and assets/rhythm.svg from live GitHub data.

Self-contained dark cards (donut + commit heatmap), no third-party services.
Runs in GitHub Actions with GITHUB_TOKEN.

  languages.svg : donut of bytes-per-language + a stat column
  rhythm.svg    : 7x24 heatmap of recent pushes, in IST, with a busiest-hour line

Usage: GITHUB_TOKEN=... python3 scripts/generate_stats.py
"""

import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

USER = "imanaswer"
API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
IST = timezone(timedelta(hours=5, minutes=30))   # Anaswer is in India

# palette
BG_TOP, BG_BOT = "#14121c", "#0a0910"
BORDER = "#241f36"
HEAD = "#6e6a86"          # small-caps section header
MUTE = "#8b8798"          # labels / subtitles
BRIGHT = "#ece8ff"        # big numbers
ACCENT = "#9d71fa"
DONUT = ["#a78bfa", "#8b5cf6", "#7c3aed", "#6d28d9", "#5b21b6", "#4c1d95"]
OTHER = "#3f3d4d"

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


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
        for lang, n in langs.items():
            totals[lang] = totals.get(lang, 0) + n
    return totals


def get_pushes():
    """Recent PushEvents -> (7x24 grid, total pushes, span_days, tz label)."""
    grid = [[0] * 24 for _ in range(7)]
    total, earliest = 0, None
    for page in range(1, 4):                       # ~300 events, ~90 days
        try:
            _, events = gh(f"{API}/users/{USER}/events?per_page=100&page={page}")
        except Exception:
            break
        if not events:
            break
        for e in events:
            if e.get("type") != "PushEvent":
                continue
            dt = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).astimezone(IST)
            grid[dt.weekday()][dt.hour] += 1
            total += 1
            earliest = dt if earliest is None or dt < earliest else earliest
    span = (datetime.now(IST) - earliest).days + 1 if earliest else 0
    return grid, total, span


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def card(w, h):
    return [
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">',
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOT}"/>'
        f'</linearGradient></defs>',
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="16" '
        f'fill="url(#bg)" stroke="{BORDER}" stroke-width="1"/>',
    ]


def donut(cx, cy, segments, total):
    r, sw = 52, 22
    C = 2 * math.pi * r
    out, acc = [], 0.0
    for i, (label, val) in enumerate(segments):
        frac = val / total
        color = DONUT[i] if label != "Other" else OTHER
        dash = frac * C
        rot = -90 + acc * 360
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
            f'stroke-width="{sw}" stroke-dasharray="{dash:.2f} {C-dash:.2f}" '
            f'transform="rotate({rot:.2f} {cx} {cy})"/>'
        )
        acc += frac
    top_label, top_val = segments[0]
    out.append(f'<text x="{cx}" y="{cy-2}" font-size="20" font-weight="700" '
               f'fill="{BRIGHT}" text-anchor="middle">{100*top_val/total:.0f}%</text>')
    out.append(f'<text x="{cx}" y="{cy+16}" font-size="11" fill="{MUTE}" '
               f'text-anchor="middle">{esc(top_label)}</text>')
    return out


def languages_svg(totals, n_original, n_public, pushes):
    total = sum(totals.values()) or 1
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
    other = total - sum(v for _, v in top)
    segments = top + ([("Other", other)] if other > 0 else [])

    W, H = 840, 232
    p = card(W, H)
    p.append(f'<text x="34" y="46" font-size="13" font-weight="700" letter-spacing="4" '
             f'fill="{HEAD}">LANGUAGES</text>')
    p.append(f'<text x="34" y="68" font-size="12" fill="{MUTE}">'
             f'by bytes written across {n_original} original repositories</text>')

    p += donut(128, 148, segments, total)

    # legend
    lx, ly = 230, 108
    for i, (lang, val) in enumerate(segments):
        color = DONUT[i] if lang != "Other" else OTHER
        pct = 100 * val / total
        p.append(f'<rect x="{lx}" y="{ly-10}" width="11" height="11" rx="2" fill="{color}"/>')
        p.append(f'<text x="{lx+20}" y="{ly}" font-size="13" fill="{BRIGHT}">{esc(lang)}</text>')
        p.append(f'<text x="{lx+235}" y="{ly}" font-size="13" fill="{MUTE}" '
                 f'text-anchor="end">{pct:.1f}%</text>')
        ly += 22

    # stat column
    sx = 585
    stats = [(str(n_original), "original repos"),
             (str(n_public), "public repos"),
             (str(len(totals)), "languages"),
             (str(pushes), "pushes · 90d")]
    sy = 96
    for num, lab in stats:
        p.append(f'<text x="{sx}" y="{sy}" font-size="30" font-weight="700" fill="{BRIGHT}">{num}</text>')
        p.append(f'<text x="{sx+78}" y="{sy}" font-size="13" fill="{MUTE}">{lab}</text>')
        sy += 34
    p.append("</svg>")
    return "\n".join(p)


def rhythm_svg(grid, pushes, span):
    total = sum(sum(r) for r in grid) or 1
    peak = max(max(r) for r in grid) or 1
    hour_totals = [sum(grid[d][h] for d in range(7)) for h in range(24)]
    busiest = hour_totals.index(max(hour_totals)) if any(hour_totals) else 0
    late = sum(hour_totals[h] for h in (22, 23, 0, 1, 2)) / total * 100

    def hlabel(h):
        if h == 0: return "12a"
        if h < 12: return f"{h}a"
        if h == 12: return "12p"
        return f"{h-12}p"

    cell, gap, left = 27, 4, 70
    top = 96
    W = 840
    grid_w = 24 * (cell + gap) - gap
    left = (W - grid_w) // 2 + 14
    H = top + 7 * (cell + gap) + 52

    p = card(W, H)
    p.append(f'<text x="34" y="46" font-size="13" font-weight="700" letter-spacing="4" '
             f'fill="{HEAD}">WHEN I COMMIT</text>')
    label = f'{pushes} pushes · last {span} days · Asia/Kolkata' if span else 'no recent pushes'
    p.append(f'<text x="34" y="68" font-size="12" fill="{MUTE}">{label}</text>')

    # busiest-hour guide line
    bx = left + busiest * (cell + gap) + cell / 2
    p.append(f'<line x1="{bx:.1f}" y1="{top-8}" x2="{bx:.1f}" y2="{top+7*(cell+gap)-gap+4}" '
             f'stroke="{ACCENT}" stroke-width="1" stroke-dasharray="2 4" opacity="0.5"/>')

    for d in range(7):
        y = top + d * (cell + gap)
        p.append(f'<text x="{left-12}" y="{y+cell/2+4}" font-size="10" letter-spacing="1" '
                 f'fill="{MUTE}" text-anchor="end">{DAYS[d].upper()}</text>')
        for h in range(24):
            x = left + h * (cell + gap)
            v = grid[d][h]
            if v == 0:
                p.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="5" '
                         f'fill="none" stroke="{BORDER}" stroke-width="1"/>')
            else:
                op = 0.28 + 0.72 * (v / peak)
                p.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="5" '
                         f'fill="{ACCENT}" opacity="{op:.2f}"/>')

    ly = top + 7 * (cell + gap) + 12
    for h in (0, 6, 12, 18, 23):
        x = left + h * (cell + gap)
        p.append(f'<text x="{x}" y="{ly}" font-size="10" fill="{MUTE}">{hlabel(h)}</text>')

    fy = H - 20
    p.append(f'<text x="34" y="{fy}" font-size="12" fill="{MUTE}">'
             f'{late:.0f}% of my pushes land between 10pm and 3am.</text>')
    p.append(f'<text x="{W-34}" y="{fy}" font-size="12" fill="{MUTE}" text-anchor="end">'
             f'busiest hour · {hlabel(busiest).replace("a","am").replace("p","pm")}</text>')
    p.append("</svg>")
    return "\n".join(p)


def main():
    repos = get_repos()
    originals = [r for r in repos if not r["fork"]]
    totals = get_languages(repos)
    grid, pushes, span = get_pushes()

    os.makedirs("assets", exist_ok=True)
    with open("assets/languages.svg", "w") as f:
        f.write(languages_svg(totals, len(originals), len(repos), pushes))
    with open("assets/rhythm.svg", "w") as f:
        f.write(rhythm_svg(grid, pushes, span))
    print(f"Wrote assets/ — {len(totals)} languages, {pushes} pushes over {span}d", file=sys.stderr)


if __name__ == "__main__":
    main()
