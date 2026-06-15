#!/usr/bin/env python3
"""
build_logos.py — fetch latest official team logos and generate standardized variants.

Sources logos from ESPN's public sports API (no API key required):
  https://site.api.espn.com/apis/site/v2/sports/<path>/teams
Each team logo is a transparent PNG served from a.espncdn.com.

For every team it produces 6 PNG variants (background transparent unless noted):
  <slug>_big_square.png          512px  logo fit to a square frame
  <slug>_big_circle.png          512px  logo inset to fit inside a circle (transparent)
  <slug>_big_circle_badge.png    512px  logo on a solid white circular disc
  <slug>_small_square.png        128px
  <slug>_small_circle.png        128px
  <slug>_small_circle_badge.png  128px

Layout:
  MSI2026/<League>/<Team>/<6 files>
  MLB/<American League|National League>/<Team>/<6 files>
  NBA/<Eastern Conference|Western Conference>/<Team>/<6 files>

Usage:
  python3 scripts/build_logos.py report   # match all teams to logos, print confidence, download nothing
  python3 scripts/build_logos.py build     # download masters + generate all variants + manifest
"""
import sys, os, re, json, time, io, unicodedata, urllib.request, urllib.error
from difflib import SequenceMatcher
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTERS = os.path.join(ROOT, "_masters")
UA = {"User-Agent": "Mozilla/5.0 (logo-fetch)"}
BIG, SMALL = 512, 128
SQUARE_PAD = 0.06   # fraction of frame as padding for square fit
CIRCLE_PAD = 0.10   # padding for circle fits

# ---------------------------------------------------------------- team lists
# MSI2026: 100 canonical clubs, faithful to public.teams.league_at_creation
MSI = [
    # Bundesliga (18)
    ("1. FC Heidenheim", "Bundesliga"), ("1. FC Köln", "Bundesliga"),
    ("1899 Hoffenheim", "Bundesliga"), ("Bayer Leverkusen", "Bundesliga"),
    ("Bayern München", "Bundesliga"), ("Borussia Dortmund", "Bundesliga"),
    ("Borussia Mönchengladbach", "Bundesliga"), ("Eintracht Frankfurt", "Bundesliga"),
    ("FC Augsburg", "Bundesliga"), ("FC St. Pauli", "Bundesliga"),
    ("FSV Mainz 05", "Bundesliga"), ("Hamburger SV", "Bundesliga"),
    ("RB Leipzig", "Bundesliga"), ("SC Freiburg", "Bundesliga"),
    ("Union Berlin", "Bundesliga"), ("VfB Stuttgart", "Bundesliga"),
    ("VfL Wolfsburg", "Bundesliga"), ("Werder Bremen", "Bundesliga"),
    # Champions League (2) — domestic feed used to source logo
    ("Bodo/Glimt", "Champions League"), ("Galatasaray", "Champions League"),
    # La Liga (20)
    ("Alaves", "La Liga"), ("Athletic Club", "La Liga"), ("Atletico Madrid", "La Liga"),
    ("Barcelona", "La Liga"), ("Celta Vigo", "La Liga"), ("Elche", "La Liga"),
    ("Espanyol", "La Liga"), ("Getafe", "La Liga"), ("Girona", "La Liga"),
    ("Levante", "La Liga"), ("Mallorca", "La Liga"), ("Osasuna", "La Liga"),
    ("Oviedo", "La Liga"), ("Rayo Vallecano", "La Liga"), ("Real Betis", "La Liga"),
    ("Real Madrid", "La Liga"), ("Real Sociedad", "La Liga"), ("Sevilla", "La Liga"),
    ("Valencia", "La Liga"), ("Villarreal", "La Liga"),
    # Liga Portugal (1)
    ("Sporting CP", "Liga Portugal"),
    # Ligue 1 (18)
    ("Angers", "Ligue 1"), ("Auxerre", "Ligue 1"), ("Le Havre", "Ligue 1"),
    ("Lens", "Ligue 1"), ("Lille", "Ligue 1"), ("Lorient", "Ligue 1"),
    ("Lyon", "Ligue 1"), ("Marseille", "Ligue 1"), ("Metz", "Ligue 1"),
    ("Monaco", "Ligue 1"), ("Nantes", "Ligue 1"), ("Nice", "Ligue 1"),
    ("Paris FC", "Ligue 1"), ("Paris Saint Germain", "Ligue 1"), ("Rennes", "Ligue 1"),
    ("Stade Brestois 29", "Ligue 1"), ("Strasbourg", "Ligue 1"), ("Toulouse", "Ligue 1"),
    # Premier League (21)
    ("Arsenal", "Premier League"), ("Aston Villa", "Premier League"),
    ("Bournemouth", "Premier League"), ("Brentford", "Premier League"),
    ("Brighton", "Premier League"), ("Burnley", "Premier League"),
    ("Chelsea", "Premier League"), ("Crystal Palace", "Premier League"),
    ("Everton", "Premier League"), ("Fulham", "Premier League"),
    ("Leeds", "Premier League"), ("Liverpool", "Premier League"),
    ("Manchester City", "Premier League"), ("Manchester United", "Premier League"),
    ("Newcastle", "Premier League"), ("Nottingham Forest", "Premier League"),
    ("Southampton", "Premier League"), ("Sunderland", "Premier League"),
    ("Tottenham", "Premier League"), ("West Ham", "Premier League"),
    ("Wolves", "Premier League"),
    # Serie A (20)
    ("AC Milan", "Serie A"), ("AS Roma", "Serie A"), ("Atalanta", "Serie A"),
    ("Bologna", "Serie A"), ("Cagliari", "Serie A"), ("Como", "Serie A"),
    ("Cremonese", "Serie A"), ("Fiorentina", "Serie A"), ("Genoa", "Serie A"),
    ("Hellas Verona", "Serie A"), ("Inter", "Serie A"), ("Juventus", "Serie A"),
    ("Lazio", "Serie A"), ("Lecce", "Serie A"), ("Napoli", "Serie A"),
    ("Parma", "Serie A"), ("Pisa", "Serie A"), ("Sassuolo", "Serie A"),
    ("Torino", "Serie A"), ("Udinese", "Serie A"),
]

# Explicit overrides for clubs whose ESPN name won't fuzzy-match the DB name.
# value = exact ESPN displayName to look for in the pool (matched via normalize).
ALIAS = {
    "1. FC Köln": "Cologne",
    "Wolves": "Wolverhampton Wanderers",
    "Inter": "Internazionale",
}

# Hard exact-displayName pins (case/accent-insensitive, NO stopword stripping) for
# names that otherwise collide — e.g. "Sporting CP" vs "Sporting Gijón" both reduce
# to "sporting" once "CP" is stripped.
PIN = {
    "Sporting CP": "Sporting CP",       # Lisbon, NOT Gijón
    "Lyon": "Lyon",
    "Stade Brestois 29": "Brest",
}

# Clubs absent from every ESPN league feed (ESPN's Serie A list omits the promoted
# sides). Pinned to their ESPN soccer team id -> logo CDN, verified by hand.
SOCCER_LOGO_BY_ID = "https://a.espncdn.com/i/teamlogos/soccer/500/{}.png"
DIRECT = {
    "Hellas Verona": "119",
    "Cremonese": "4050",
    "Pisa": "3956",
}

# Soccer feeds to build the matching pool from (slug, [seasons]).
SOCCER_FEEDS = [
    ("eng.1", [2024, 2025, 2026]), ("eng.2", [2025, 2026]),
    ("esp.1", [2024, 2025, 2026]), ("esp.2", [2025, 2026]),
    ("ger.1", [2024, 2025, 2026]), ("ger.2", [2025, 2026]),
    ("ita.1", [2024, 2025, 2026]), ("ita.2", [2025, 2026]),
    ("fra.1", [2024, 2025, 2026]), ("fra.2", [2025, 2026]),
    ("por.1", [2025, 2026]), ("nor.1", [2025, 2026]),
    ("tur.1", [2025, 2026]), ("uefa.champions", [2025, 2026]),
]

# US leagues: take all teams straight from the feed.
NBA_EAST = {"Celtics","Nets","Knicks","76ers","Raptors","Bulls","Cavaliers","Pistons",
            "Pacers","Bucks","Hawks","Hornets","Heat","Magic","Wizards"}
NBA_WEST = {"Nuggets","Timberwolves","Thunder","Trail Blazers","Jazz","Warriors",
            "Clippers","Lakers","Suns","Kings","Mavericks","Rockets","Grizzlies",
            "Pelicans","Spurs"}
MLB_AL = {"Orioles","Red Sox","Yankees","Rays","Blue Jays","White Sox","Guardians",
          "Tigers","Royals","Twins","Astros","Angels","Athletics","Mariners","Rangers"}
MLB_NL = {"Braves","Marlins","Mets","Phillies","Nationals","Cubs","Reds","Brewers",
          "Pirates","Cardinals","Diamondbacks","Rockies","Dodgers","Padres","Giants"}

# ---------------------------------------------------------------- helpers
STOP = {"fc","cf","afc","ac","as","sc","ssc","rc","cd","ud","ss","sv","vfb","vfl",
        "tsg","fsv","bsc","sl","cp","sad","club","calcio","de","der","og","ogc",
        "rcd","ca","1846","1899","1909","1907","05","04","96","29","1.","aj"}

def strip_accents(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()

def norm(s):
    s = strip_accents(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t and t not in STOP]
    return " ".join(toks)

def toks(s):
    return set(norm(s).split())

def ratio(a, b):
    return SequenceMatcher(None, a, b).ratio()

def fetch_json(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as f:
                return json.loads(f.read())
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(0.5)

def pick_logo(team):
    """Choose the primary (light) full logo href from an ESPN team object."""
    logos = team.get("logos") or []
    if not logos:
        return None
    # prefer one whose rel does NOT include 'dark' and does include 'full'/'default'
    def score(l):
        rel = set(l.get("rel") or [])
        return ( ("dark" in rel), -("full" in rel or "default" in rel) )
    return sorted(logos, key=score)[0]["href"]

def espn_teams(path, season=None):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams"
    if season:
        url += f"?season={season}"
    try:
        data = fetch_json(url)
        return data["sports"][0]["leagues"][0]["teams"]
    except Exception:
        return []

# ---------------------------------------------------------------- pool / match
def build_soccer_pool():
    pool = {}  # espn id -> {name, logo, names:set}
    for slug, seasons in SOCCER_FEEDS:
        for season in seasons:
            for t in espn_teams(f"soccer/{slug}", season):
                team = t["team"]
                tid = team.get("id")
                logo = pick_logo(team)
                if not tid or not logo:
                    continue
                names = {team.get("displayName",""), team.get("shortDisplayName",""),
                         team.get("name",""), team.get("location","")}
                names = {n for n in names if n}
                if tid in pool:
                    pool[tid]["names"] |= names
                else:
                    pool[tid] = {"id": tid, "name": team.get("displayName",""),
                                 "logo": logo, "names": names}
    return list(pool.values())

def match_team(db_name, pool):
    """Return (entry, score, how)."""
    if db_name in PIN:
        want = strip_accents(PIN[db_name]).lower().strip()
        for e in pool:
            if any(strip_accents(n).lower().strip() == want for n in e["names"]):
                return e, 1.0, "pin"
    alias = ALIAS.get(db_name)
    targets = [alias] if alias else [db_name]
    best, best_s, how = None, 0.0, ""
    for tgt in targets:
        tnorm, ttok = norm(tgt), toks(tgt)
        for e in pool:
            cand_norms = {norm(n) for n in e["names"]}
            cand_toks = set()
            for n in e["names"]:
                cand_toks |= toks(n)
            # 1 exact normalized
            if tnorm in cand_norms:
                return e, 1.0, ("alias-exact" if alias else "exact")
            # 2 token subset (db tokens fully contained)
            if ttok and ttok <= cand_toks:
                s = 0.95
                if s > best_s:
                    best, best_s, how = e, s, "token-subset"
            # 3 fuzzy on best name
            for cn in cand_norms:
                s = ratio(tnorm, cn)
                if s > best_s:
                    best, best_s, how = e, s, ("alias-fuzzy" if alias else "fuzzy")
    return best, best_s, how

# ---------------------------------------------------------------- imaging
def autocrop(im):
    im = im.convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    return im.crop(bbox) if bbox else im

def circle_mask(size):
    ss = size * 4
    m = Image.new("L", (ss, ss), 0)
    ImageDraw.Draw(m).ellipse((0, 0, ss - 1, ss - 1), fill=255)
    return m.resize((size, size), Image.Resampling.LANCZOS)

def scaled(logo, target_w, target_h):
    w, h = logo.size
    r = min(target_w / w, target_h / h)
    return logo.resize((max(1, round(w * r)), max(1, round(h * r))), Image.Resampling.LANCZOS)

def make_square(logo, size):
    inner = size * (1 - 2 * SQUARE_PAD)
    s = scaled(logo, inner, inner)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(s, ((size - s.width) // 2, (size - s.height) // 2))
    return canvas

def make_circle_transparent(logo, size):
    # inset so the bounding box fits inside the inscribed circle (diagonal fit)
    import math
    diam = size * (1 - 2 * CIRCLE_PAD)
    w, h = logo.size
    diag = math.hypot(w, h)
    r = diam / diag
    s = logo.resize((max(1, round(w * r)), max(1, round(h * r))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(s, ((size - s.width) // 2, (size - s.height) // 2))
    return canvas

def make_circle_badge(logo, size):
    disc = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    disc = Image.composite(white, disc, circle_mask(size))
    inner = size * 0.72  # logo sits comfortably on the disc
    s = scaled(logo, inner, inner)
    disc.alpha_composite(s, ((size - s.width) // 2, (size - s.height) // 2))
    return disc

VARIANTS = [
    ("big_square",        BIG,   make_square),
    ("big_circle",        BIG,   make_circle_transparent),
    ("big_circle_badge",  BIG,   make_circle_badge),
    ("small_square",      SMALL, make_square),
    ("small_circle",      SMALL, make_circle_transparent),
    ("small_circle_badge",SMALL, make_circle_badge),
]

def slugify(name):
    s = strip_accents(name).lower()
    s = s.replace("/", "-").replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def folder_name(name):
    return name.replace("/", "-").strip()

def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as f:
        data = f.read()
    with open(dest, "wb") as out:
        out.write(data)

def generate(master_path, out_dir, slug):
    os.makedirs(out_dir, exist_ok=True)
    logo = autocrop(Image.open(master_path))
    files = []
    for suffix, size, fn in VARIANTS:
        img = fn(logo, size)
        fp = os.path.join(out_dir, f"{slug}_{suffix}.png")
        img.save(fp)
        files.append(os.path.relpath(fp, ROOT))
    return files

# ---------------------------------------------------------------- drivers
def collect_jobs():
    """Return list of job dicts with everything needed to build (no downloads)."""
    pool = build_soccer_pool()
    jobs, problems = [], []

    # MSI2026 soccer
    for name, league in MSI:
        if name in DIRECT:
            jobs.append({"comp": "MSI2026", "group": league, "team": name,
                         "slug": slugify(name),
                         "logo": SOCCER_LOGO_BY_ID.format(DIRECT[name]),
                         "matched": f"ESPN id {DIRECT[name]}", "score": 1.0,
                         "how": "direct-id"})
            continue
        e, s, how = match_team(name, pool)
        if not e or s < 0.80:
            problems.append((name, league, e["name"] if e else None, round(s, 2), how))
            continue
        jobs.append({"comp": "MSI2026", "group": league, "team": name,
                     "slug": slugify(name), "logo": e["logo"],
                     "matched": e["name"], "score": round(s, 2), "how": how})

    # NBA
    for t in espn_teams("basketball/nba"):
        team = t["team"]; nm = team.get("displayName",""); logo = pick_logo(team)
        nick = nm.split()[-1] if nm else ""
        two = " ".join(nm.split()[-2:])
        grp = ("Eastern Conference" if (nick in NBA_EAST or two in NBA_EAST)
               else "Western Conference" if (nick in NBA_WEST or two in NBA_WEST) else "NBA")
        jobs.append({"comp":"NBA","group":grp,"team":nm,"slug":slugify(nm),
                     "logo":logo,"matched":nm,"score":1.0,"how":"feed"})

    # MLB
    for t in espn_teams("baseball/mlb"):
        team = t["team"]; nm = team.get("displayName",""); logo = pick_logo(team)
        nick = nm.split()[-1] if nm else ""
        two = " ".join(nm.split()[-2:])
        grp = ("American League" if (nick in MLB_AL or two in MLB_AL)
               else "National League" if (nick in MLB_NL or two in MLB_NL) else "MLB")
        jobs.append({"comp":"MLB","group":grp,"team":nm,"slug":slugify(nm),
                     "logo":logo,"matched":nm,"score":1.0,"how":"feed"})

    return jobs, problems

def cmd_report():
    jobs, problems = collect_jobs()
    by = {}
    for j in jobs:
        by.setdefault(j["comp"], []).append(j)
    print("=== MATCH REPORT ===")
    for comp in ("MSI2026","MLB","NBA"):
        js = by.get(comp, [])
        print(f"\n## {comp}: {len(js)} matched")
        for j in sorted(js, key=lambda x: x["score"]):
            flag = "  <-- LOW" if j["score"] < 0.92 else ""
            print(f"  {j['score']:.2f} {j['how']:12s} {j['team']:28s} -> {j['matched']}{flag}")
    print(f"\n## PROBLEMS ({len(problems)}):")
    for p in problems:
        print("  ", p)
    total = len(jobs)
    print(f"\nTOTAL matched={total}  problems={len(problems)}")

def cmd_build():
    jobs, problems = collect_jobs()
    if problems:
        print("Refusing to build — unresolved matches:")
        for p in problems:
            print("  ", p)
        sys.exit(1)
    manifest = []
    for i, j in enumerate(jobs, 1):
        sport_dir = {"MSI2026":"soccer","NBA":"nba","MLB":"mlb"}[j["comp"]]
        master = os.path.join(MASTERS, sport_dir, j["slug"] + ".png")
        try:
            download(j["logo"], master)
            out_dir = os.path.join(ROOT, j["comp"], folder_name(j["group"]), folder_name(j["team"]))
            files = generate(master, out_dir, j["slug"])
            manifest.append({"competition": j["comp"], "group": j["group"],
                             "team": j["team"], "slug": j["slug"],
                             "source_logo": j["logo"], "matched_as": j["matched"],
                             "match_score": j["score"], "files": files})
            print(f"[{i:3d}/{len(jobs)}] {j['comp']:8s} {j['team']}")
        except Exception as e:
            print(f"[{i:3d}/{len(jobs)}] FAILED {j['team']}: {e}")
            manifest.append({"competition": j["comp"], "team": j["team"], "error": str(e)})
        time.sleep(0.02)
    with open(os.path.join(ROOT, "manifest.json"), "w") as f:
        json.dump({"generated_from": "ESPN public sports API",
                   "variants": [v[0] for v in VARIANTS],
                   "sizes": {"big": BIG, "small": SMALL},
                   "teams": manifest}, f, indent=2, ensure_ascii=False)
    ok = sum(1 for m in manifest if "files" in m)
    print(f"\nDONE: {ok}/{len(jobs)} teams, {ok*len(VARIANTS)} images. manifest.json written.")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"report": cmd_report, "build": cmd_build}.get(mode, cmd_report)()
