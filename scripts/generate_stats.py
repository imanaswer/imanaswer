#!/usr/bin/env python3
"""
Generate three dark stat cards from live GitHub data — no third-party services.

  assets/languages.svg : donut of bytes-per-language + stat column
  assets/rhythm.svg    : 7x24 heatmap of recent pushes (IST) + busiest-hour line
  assets/activity.svg  : contribution-mix radar (commits/PRs/reviews/issues)

Runs in GitHub Actions with GITHUB_TOKEN.
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
IST = timezone(timedelta(hours=5, minutes=30))

# palette
BG_TOP, BG_BOT = "#14121c", "#0a0910"
BORDER = "#241f36"
GRID = "#2a2740"
HEAD = "#6e6a86"
MUTE = "#8b8798"
BRIGHT = "#ece8ff"
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


def graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(f"{API}/graphql", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


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
    grid = [[0] * 24 for _ in range(7)]
    total, earliest = 0, None
    for page in range(1, 4):
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


def get_contributions():
    q = """query($login:String!){user(login:$login){contributionsCollection{
        totalCommitContributions
        totalPullRequestContributions
        totalPullRequestReviewContributions
        totalIssueContributions}}}"""
    try:
        d = graphql(q, {"login": USER})
        c = d["data"]["user"]["contributionsCollection"]
        return {
            "commits": c["totalCommitContributions"],
            "prs": c["totalPullRequestContributions"],
            "reviews": c["totalPullRequestReviewContributions"],
            "issues": c["totalIssueContributions"],
        }
    except Exception as e:
        print(f"contrib fetch failed: {e}", file=sys.stderr)
        return {"commits": 0, "prs": 0, "reviews": 0, "issues": 0}


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


def stat_column(p, x, y, rows, width=250):
    """Big-number rows with faint divider lines, like the reference."""
    row_h = 44
    for i, (num, lab) in enumerate(rows):
        cy = y + i * row_h
        p.append(f'<text x="{x}" y="{cy}" font-size="30" font-weight="700" fill="{BRIGHT}">{num}</text>')
        p.append(f'<text x="{x+82}" y="{cy}" font-size="13" fill="{MUTE}">{lab}</text>')
        if i < len(rows) - 1:
            p.append(f'<line x1="{x}" y1="{cy+16}" x2="{x+width}" y2="{cy+16}" '
                     f'stroke="{GRID}" stroke-width="1"/>')


def donut(cx, cy, segments, total):
    r, sw = 52, 22
    C = 2 * math.pi * r
    out, acc = [], 0.0
    for i, (label, val) in enumerate(segments):
        frac = val / total
        color = DONUT[i] if label != "Other" else OTHER
        dash = frac * C
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
            f'stroke-width="{sw}" stroke-dasharray="{dash:.2f} {C-dash:.2f}" '
            f'transform="rotate({-90+acc*360:.2f} {cx} {cy})"/>'
        )
        acc += frac
    tl, tv = segments[0]
    out.append(f'<text x="{cx}" y="{cy-2}" font-size="20" font-weight="700" '
               f'fill="{BRIGHT}" text-anchor="middle">{100*tv/total:.0f}%</text>')
    out.append(f'<text x="{cx}" y="{cy+16}" font-size="11" fill="{MUTE}" '
               f'text-anchor="middle">{esc(tl)}</text>')
    return out


def languages_svg(totals, n_original, n_public, pushes):
    total = sum(totals.values()) or 1
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
    other = total - sum(v for _, v in top)
    segments = top + ([("Other", other)] if other > 0 else [])

    W, H = 840, 250
    p = card(W, H)
    p.append(f'<text x="34" y="46" font-size="13" font-weight="700" letter-spacing="4" fill="{HEAD}">LANGUAGES</text>')
    p.append(f'<text x="34" y="68" font-size="12" fill="{MUTE}">by bytes written across {n_original} original repositories</text>')
    p += donut(126, 156, segments, total)

    lx, ly = 228, 116
    for i, (lang, val) in enumerate(segments):
        color = DONUT[i] if lang != "Other" else OTHER
        p.append(f'<rect x="{lx}" y="{ly-10}" width="11" height="11" rx="2" fill="{color}"/>')
        p.append(f'<text x="{lx+20}" y="{ly}" font-size="13" fill="{BRIGHT}">{esc(lang)}</text>')
        p.append(f'<text x="{lx+225}" y="{ly}" font-size="13" fill="{MUTE}" text-anchor="end">{100*val/total:.1f}%</text>')
        ly += 21

    stat_column(p, 585, 110, [
        (str(n_original), "original repos"),
        (str(n_public), "public repos"),
        (str(len(totals)), "languages"),
        (str(pushes), "pushes · 90d"),
    ], width=220)
    p.append("</svg>")
    return "\n".join(p)


def rhythm_svg(grid, pushes, span):
    total = sum(sum(r) for r in grid) or 1
    peak = max(max(r) for r in grid) or 1
    hour_totals = [sum(grid[d][h] for d in range(7)) for h in range(24)]
    busiest = hour_totals.index(max(hour_totals)) if any(hour_totals) else 0
    late = sum(hour_totals[h] for h in (22, 23, 0, 1, 2)) / total * 100

    def hl(h):
        return "12a" if h == 0 else f"{h}a" if h < 12 else "12p" if h == 12 else f"{h-12}p"

    cell, gap, top, W = 27, 4, 96, 840
    grid_w = 24 * (cell + gap) - gap
    left = (W - grid_w) // 2 + 14
    H = top + 7 * (cell + gap) + 52

    p = card(W, H)
    p.append(f'<text x="34" y="46" font-size="13" font-weight="700" letter-spacing="4" fill="{HEAD}">WHEN I COMMIT</text>')
    lab = f'{pushes} pushes · last {span} days · Asia/Kolkata' if span else 'no recent pushes'
    p.append(f'<text x="34" y="68" font-size="12" fill="{MUTE}">{lab}</text>')

    bx = left + busiest * (cell + gap) + cell / 2
    p.append(f'<line x1="{bx:.1f}" y1="{top-8}" x2="{bx:.1f}" y2="{top+7*(cell+gap)-gap+4}" '
             f'stroke="{ACCENT}" stroke-width="1" stroke-dasharray="2 4" opacity="0.5"/>')

    for d in range(7):
        y = top + d * (cell + gap)
        p.append(f'<text x="{left-12}" y="{y+cell/2+4}" font-size="10" letter-spacing="1" fill="{MUTE}" text-anchor="end">{DAYS[d].upper()}</text>')
        for h in range(24):
            x = left + h * (cell + gap)
            v = grid[d][h]
            if v == 0:
                p.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="5" fill="none" stroke="{BORDER}" stroke-width="1"/>')
            else:
                op = 0.28 + 0.72 * (v / peak)
                p.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="5" fill="{ACCENT}" opacity="{op:.2f}"/>')

    ly = top + 7 * (cell + gap) + 12
    for h in (0, 6, 12, 18, 23):
        x = left + h * (cell + gap)
        p.append(f'<text x="{x}" y="{ly}" font-size="10" fill="{MUTE}">{hl(h)}</text>')

    fy = H - 20
    p.append(f'<text x="34" y="{fy}" font-size="12" fill="{MUTE}">{late:.0f}% of my pushes land between 10pm and 3am.</text>')
    bl = hl(busiest).replace("a", "am").replace("p", "pm")
    p.append(f'<text x="{W-34}" y="{fy}" font-size="12" fill="{MUTE}" text-anchor="end">busiest hour · {bl}</text>')
    p.append("</svg>")
    return "\n".join(p)


def activity_svg(c):
    commits, prs, reviews, issues = c["commits"], c["prs"], c["reviews"], c["issues"]
    total = commits + prs + reviews + issues or 1
    fr = {"commits": commits/total, "reviews": reviews/total,
          "issues": issues/total, "prs": prs/total}

    W, H = 840, 300
    cx, cy, R = 210, 168, 96
    p = card(W, H)
    p.append(f'<text x="34" y="46" font-size="13" font-weight="700" letter-spacing="4" fill="{HEAD}">ACTIVITY</text>')
    p.append(f'<text x="34" y="68" font-size="12" fill="{MUTE}">contribution mix · last 12 months</text>')

    # guide rings + axes
    for k in (0.33, 0.66, 1.0):
        p.append(f'<circle cx="{cx}" cy="{cy}" r="{R*k:.0f}" fill="none" stroke="{GRID}" '
                 f'stroke-width="1" stroke-dasharray="2 4" opacity="0.6"/>')
    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        p.append(f'<line x1="{cx}" y1="{cy}" x2="{cx+dx*R}" y2="{cy+dy*R}" stroke="{GRID}" stroke-width="1" opacity="0.6"/>')

    # data polygon: top=reviews, right=issues, bottom=prs, left=commits
    top_pt = (cx, cy - R*fr["reviews"])
    right_pt = (cx + R*fr["issues"], cy)
    bot_pt = (cx, cy + R*fr["prs"])
    left_pt = (cx - R*fr["commits"], cy)
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (top_pt, right_pt, bot_pt, left_pt))
    p.append(f'<polygon points="{pts}" fill="{ACCENT}" fill-opacity="0.22" stroke="{ACCENT}" stroke-width="1.5"/>')
    for x, y in (top_pt, right_pt, bot_pt, left_pt):
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{ACCENT}"/>')
    p.append(f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{MUTE}"/>')

    # axis labels
    def axis(x, y, name, frac, anchor="middle"):
        p.append(f'<text x="{x}" y="{y}" font-size="11" fill="{MUTE}" text-anchor="{anchor}">{name}</text>')
        p.append(f'<text x="{x}" y="{y+15}" font-size="11" font-weight="700" fill="{BRIGHT}" text-anchor="{anchor}">{100*frac:.0f}%</text>')
    axis(cx, cy - R - 16, "Code review", fr["reviews"])
    axis(cx + R + 14, cy - 2, "Issues", fr["issues"], "start")
    axis(cx, cy + R + 22, "Pull requests", fr["prs"])
    axis(cx - R - 14, cy - 2, "Commits", fr["commits"], "end")

    stat_column(p, 585, 118, [
        (str(commits), "commits"),
        (str(prs), "pull requests"),
        (str(reviews), "reviews"),
        (str(issues), "issues"),
    ], width=220)
    p.append("</svg>")
    return "\n".join(p)


def main():
    repos = get_repos()
    originals = [r for r in repos if not r["fork"]]
    totals = get_languages(repos)
    grid, pushes, span = get_pushes()
    contrib = get_contributions()

    os.makedirs("assets", exist_ok=True)
    open("assets/languages.svg", "w").write(languages_svg(totals, len(originals), len(repos), pushes))
    open("assets/rhythm.svg", "w").write(rhythm_svg(grid, pushes, span))
    open("assets/activity.svg", "w").write(activity_svg(contrib))
    print(f"Wrote 3 cards — {len(totals)} langs, {pushes} pushes, {contrib['commits']} commits", file=sys.stderr)


if __name__ == "__main__":
    main()
