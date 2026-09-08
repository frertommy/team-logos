#!/usr/bin/env python3
"""
build_logos.py — fetch latest official team logos and generate standardized variants.

Sources logos from ESPN's public sports API (no API key required):
  https://site.web.api.espn.com/apis/site/v2/sports/<path>/teams
  (the original site.api.espn.com host has been 403-blocked since mid-2026;
  site.web.api.espn.com serves the identical JSON — see ESPN_HOST)
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
  NFL/<AFC|NFC>/<Team>/<6 files>

Usage:
  python3 scripts/build_logos.py report   # match all teams to logos, print confidence, download nothing
  python3 scripts/build_logos.py build     # download masters + generate all variants + manifest
  python3 scripts/build_logos.py build NFL # build one competition, merge into manifest.json
  python3 scripts/build_logos.py build MSI2026 --new            # only teams with no PNGs yet
  python3 scripts/build_logos.py build MSI2026 --teams "Coventry,Hull City"  # named teams only
Team-filtered builds merge into manifest.json by (competition, team), keeping every
other entry untouched and the competition block in its canonical list order.

If a team folder contains an authentic <slug>.svg (see fetch_svgs.py), the PNG
variants are generated from a 2048px render of it (needs cairosvg) instead of
the CDN raster — unless its silhouette disagrees with the raster (wordmark guard).
"""
import sys, os, re, json, time, io, unicodedata, urllib.request, urllib.error
from difflib import SequenceMatcher
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTERS = os.path.join(ROOT, "_masters")
# site.api.espn.com started returning 403 in 2026; site.web.api.espn.com is the same API.
ESPN_HOST = "site.web.api.espn.com"
UA = {"User-Agent": "Mozilla/5.0 (logo-fetch)"}
BIG, SMALL = 512, 128
SQUARE_PAD = 0.06   # fraction of frame as padding for square fit
CIRCLE_PAD = 0.10   # padding for circle fits

# ---------------------------------------------------------------- team lists
# MSI2026: 114 canonical clubs, faithful to public.teams.league_at_creation
# (100 original + the 14 clubs promoted into the big-5 leagues for 2026-27;
#  relegated clubs are kept, nothing is ever removed from this list)
MSI = [
    # Bundesliga (18 + 3 promoted 2026-27)
    ("1. FC Heidenheim", "Bundesliga"), ("1. FC Köln", "Bundesliga"),
    ("1899 Hoffenheim", "Bundesliga"), ("Bayer Leverkusen", "Bundesliga"),
    ("Bayern München", "Bundesliga"), ("Borussia Dortmund", "Bundesliga"),
    ("Borussia Mönchengladbach", "Bundesliga"), ("Eintracht Frankfurt", "Bundesliga"),
    ("FC Augsburg", "Bundesliga"), ("FC St. Pauli", "Bundesliga"),
    ("FSV Mainz 05", "Bundesliga"), ("Hamburger SV", "Bundesliga"),
    ("RB Leipzig", "Bundesliga"), ("SC Freiburg", "Bundesliga"),
    ("Union Berlin", "Bundesliga"), ("VfB Stuttgart", "Bundesliga"),
    ("VfL Wolfsburg", "Bundesliga"), ("Werder Bremen", "Bundesliga"),
    ("FC Schalke 04", "Bundesliga"), ("SC Paderborn 07", "Bundesliga"),   # promoted 2026-27
    ("SV Elversberg", "Bundesliga"),                                       # promoted 2026-27
    # Champions League (2) — domestic feed used to source logo
    ("Bodo/Glimt", "Champions League"), ("Galatasaray", "Champions League"),
    # La Liga (20 + 3 promoted 2026-27)
    ("Alaves", "La Liga"), ("Athletic Club", "La Liga"), ("Atletico Madrid", "La Liga"),
    ("Barcelona", "La Liga"), ("Celta Vigo", "La Liga"), ("Elche", "La Liga"),
    ("Espanyol", "La Liga"), ("Getafe", "La Liga"), ("Girona", "La Liga"),
    ("Levante", "La Liga"), ("Mallorca", "La Liga"), ("Osasuna", "La Liga"),
    ("Oviedo", "La Liga"), ("Rayo Vallecano", "La Liga"), ("Real Betis", "La Liga"),
    ("Real Madrid", "La Liga"), ("Real Sociedad", "La Liga"), ("Sevilla", "La Liga"),
    ("Valencia", "La Liga"), ("Villarreal", "La Liga"),
    ("Deportivo La Coruna", "La Liga"), ("Malaga", "La Liga"),             # promoted 2026-27
    ("Racing Santander", "La Liga"),                                       # promoted 2026-27
    # Liga Portugal (1)
    ("Sporting CP", "Liga Portugal"),
    # Ligue 1 (18 + 2 promoted 2026-27)
    ("Angers", "Ligue 1"), ("Auxerre", "Ligue 1"), ("Le Havre", "Ligue 1"),
    ("Lens", "Ligue 1"), ("Lille", "Ligue 1"), ("Lorient", "Ligue 1"),
    ("Lyon", "Ligue 1"), ("Marseille", "Ligue 1"), ("Metz", "Ligue 1"),
    ("Monaco", "Ligue 1"), ("Nantes", "Ligue 1"), ("Nice", "Ligue 1"),
    ("Paris FC", "Ligue 1"), ("Paris Saint Germain", "Ligue 1"), ("Rennes", "Ligue 1"),
    ("Stade Brestois 29", "Ligue 1"), ("Strasbourg", "Ligue 1"), ("Toulouse", "Ligue 1"),
    ("Estac Troyes", "Ligue 1"), ("Le Mans", "Ligue 1"),                   # promoted 2026-27
    # Premier League (21 + 3 promoted 2026-27)
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
    ("Coventry", "Premier League"), ("Hull City", "Premier League"),       # promoted 2026-27
    ("Ipswich", "Premier League"),                                         # promoted 2026-27
    # Serie A (20 + 3 promoted 2026-27)
    ("AC Milan", "Serie A"), ("AS Roma", "Serie A"), ("Atalanta", "Serie A"),
    ("Bologna", "Serie A"), ("Cagliari", "Serie A"), ("Como", "Serie A"),
    ("Cremonese", "Serie A"), ("Fiorentina", "Serie A"), ("Genoa", "Serie A"),
    ("Hellas Verona", "Serie A"), ("Inter", "Serie A"), ("Juventus", "Serie A"),
    ("Lazio", "Serie A"), ("Lecce", "Serie A"), ("Napoli", "Serie A"),
    ("Parma", "Serie A"), ("Pisa", "Serie A"), ("Sassuolo", "Serie A"),
    ("Torino", "Serie A"), ("Udinese", "Serie A"),
    ("Frosinone", "Serie A"), ("Monza", "Serie A"), ("Venezia", "Serie A"),  # promoted 2026-27
]

# Explicit overrides for clubs whose ESPN name won't fuzzy-match the DB name.
# value = exact ESPN displayName to look for in the pool (matched via normalize).
ALIAS = {
    "1. FC Köln": "Cologne",
    "Wolves": "Wolverhampton Wanderers",
    "Inter": "Internazionale",
    "Deportivo La Coruna": "Deportivo",   # ESPN displayName is just "Deportivo"
    "Estac Troyes": "Troyes",
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
NFL_AFC = {"Bills","Dolphins","Patriots","Jets","Ravens","Bengals","Browns","Steelers",
           "Texans","Colts","Jaguars","Titans","Broncos","Chiefs","Raiders","Chargers"}
NFL_NFC = {"Cowboys","Giants","Eagles","Commanders","Bears","Lions","Packers","Vikings",
           "Falcons","Panthers","Saints","Buccaneers","Cardinals","Rams","49ers","Seahawks"}

# NFL: ESPN's site.api feed is now 403-blocked, but the logo CDN is stable and
# addressed by team abbreviation. All 32 pinned by hand (verified vs core API).
NFL_LOGO_BY_ABBR = "https://a.espncdn.com/i/teamlogos/nfl/500/{}.png"
NFL_TEAMS = [
    ("Arizona Cardinals","ari"), ("Atlanta Falcons","atl"), ("Baltimore Ravens","bal"),
    ("Buffalo Bills","buf"), ("Carolina Panthers","car"), ("Chicago Bears","chi"),
    ("Cincinnati Bengals","cin"), ("Cleveland Browns","cle"), ("Dallas Cowboys","dal"),
    ("Denver Broncos","den"), ("Detroit Lions","det"), ("Green Bay Packers","gb"),
    ("Houston Texans","hou"), ("Indianapolis Colts","ind"), ("Jacksonville Jaguars","jax"),
    ("Kansas City Chiefs","kc"), ("Las Vegas Raiders","lv"), ("Los Angeles Chargers","lac"),
    ("Los Angeles Rams","lar"), ("Miami Dolphins","mia"), ("Minnesota Vikings","min"),
    ("New England Patriots","ne"), ("New Orleans Saints","no"), ("New York Giants","nyg"),
    ("New York Jets","nyj"), ("Philadelphia Eagles","phi"), ("Pittsburgh Steelers","pit"),
    ("San Francisco 49ers","sf"), ("Seattle Seahawks","sea"), ("Tampa Bay Buccaneers","tb"),
    ("Tennessee Titans","ten"), ("Washington Commanders","wsh"),
]

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
    url = f"https://{ESPN_HOST}/apis/site/v2/sports/{path}/teams"
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

def render_svg_master(svg_path, dest_png, height=2048):
    """Render a local authentic SVG to a high-res PNG master (crisper than CDN rasters).
    Requires cairosvg (pip install cairosvg); returns False if unavailable."""
    if sys.platform == "darwin":  # let cairocffi find Homebrew's libcairo
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib:/usr/local/lib")
    try:
        import cairosvg
    except (ImportError, OSError):
        return False
    try:
        cairosvg.svg2png(url=svg_path, write_to=dest_png, output_height=height)
        return True
    except Exception as e:
        print(f"    svg render failed ({os.path.basename(svg_path)}): {e}")
        return False

# Teams where the CDN itself serves a wide wordmark-style primary; the compact
# SVG badge is the better master for square/circle avatar crops. Skips shape check.
FORCE_SVG = {"new-york-jets"}

def pick_master(master, out_dir, slug, sport_dir):
    """Prefer a high-res render of the team's authentic SVG over the CDN raster,
    but only when its silhouette matches the trusted raster (rejects wordmarks)."""
    import math
    svg_path = os.path.join(out_dir, slug + ".svg")
    if not os.path.exists(svg_path):
        return master, "cdn-png"
    hi = os.path.join(MASTERS, sport_dir, slug + "_svg.png")
    if not render_svg_master(svg_path, hi):
        return master, "cdn-png"
    if slug in FORCE_SVG:
        return hi, "svg@2048"
    try:
        a_svg = autocrop(Image.open(hi)); a_png = autocrop(Image.open(master))
        r_svg = a_svg.width / a_svg.height
        r_png = a_png.width / a_png.height
        if abs(math.log(r_svg / r_png)) > 0.35:
            print(f"    svg shape mismatch for {slug} (ar {r_svg:.2f} vs {r_png:.2f}) — keeping CDN raster")
            return master, "cdn-png"
    except Exception:
        return master, "cdn-png"
    return hi, "svg@2048"

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
def collect_jobs(only=None):
    """Return list of job dicts with everything needed to build (no downloads).
    only='NFL' etc. skips the other competitions (and their now-blocked feeds)."""
    jobs, problems = [], []
    pool = build_soccer_pool() if only in (None, "MSI2026") else []

    # MSI2026 soccer
    for name, league in (MSI if only in (None, "MSI2026") else []):
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
    for t in (espn_teams("basketball/nba") if only in (None, "NBA") else []):
        team = t["team"]; nm = team.get("displayName",""); logo = pick_logo(team)
        nick = nm.split()[-1] if nm else ""
        two = " ".join(nm.split()[-2:])
        grp = ("Eastern Conference" if (nick in NBA_EAST or two in NBA_EAST)
               else "Western Conference" if (nick in NBA_WEST or two in NBA_WEST) else "NBA")
        jobs.append({"comp":"NBA","group":grp,"team":nm,"slug":slugify(nm),
                     "logo":logo,"matched":nm,"score":1.0,"how":"feed"})

    # MLB
    for t in (espn_teams("baseball/mlb") if only in (None, "MLB") else []):
        team = t["team"]; nm = team.get("displayName",""); logo = pick_logo(team)
        nick = nm.split()[-1] if nm else ""
        two = " ".join(nm.split()[-2:])
        grp = ("American League" if (nick in MLB_AL or two in MLB_AL)
               else "National League" if (nick in MLB_NL or two in MLB_NL) else "MLB")
        jobs.append({"comp":"MLB","group":grp,"team":nm,"slug":slugify(nm),
                     "logo":logo,"matched":nm,"score":1.0,"how":"feed"})

    # NFL — direct CDN pins (site.api feed is 403-blocked, see NFL_TEAMS)
    for nm, abbr in (NFL_TEAMS if only in (None, "NFL") else []):
        nick = nm.split()[-1]
        grp = ("AFC" if nick in NFL_AFC
               else "NFC" if nick in NFL_NFC else "NFL")
        jobs.append({"comp":"NFL","group":grp,"team":nm,"slug":slugify(nm),
                     "logo":NFL_LOGO_BY_ABBR.format(abbr),
                     "matched":f"ESPN CDN {abbr}","score":1.0,"how":"direct-cdn"})

    return jobs, problems

def cmd_report():
    jobs, problems = collect_jobs()
    by = {}
    for j in jobs:
        by.setdefault(j["comp"], []).append(j)
    print("=== MATCH REPORT ===")
    for comp in ("MSI2026","MLB","NBA","NFL"):
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

def has_all_variants(j):
    out_dir = os.path.join(ROOT, j["comp"], folder_name(j["group"]), folder_name(j["team"]))
    return all(os.path.exists(os.path.join(out_dir, f"{j['slug']}_{s}.png")) for s, _, _ in VARIANTS)

def parse_build_args(argv):
    """build [COMP] [--new] [--teams A,B,C | --teams=A,B,C]"""
    only, new_only, teams = None, False, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--new":
            new_only = True
        elif a.startswith("--teams="):
            teams = a.split("=", 1)[1]
        elif a == "--teams":
            i += 1; teams = argv[i] if i < len(argv) else ""
        elif not a.startswith("--"):
            only = a
        i += 1
    if teams is not None:
        teams = {t.strip() for t in teams.split(",") if t.strip()}
    return only, new_only, teams

def merge_manifest(prev, built, order, comps, partial):
    """Merge freshly built entries into the previous manifest.
    prev: previous entries; built: new entries; order: canonical (comp, team) keys for
    the touched comps; comps: competitions touched; partial: True when a team filter was
    used (carry over untouched teams of those comps), False = whole-competition rebuild."""
    key = lambda t: (t.get("competition"), t.get("team"))
    block = {key(t): t for t in prev if key(t)[0] in comps} if partial else {}
    block.update({key(t): t for t in built})
    ordered = [block[k] for k in order if k in block]
    ordered += [t for k, t in block.items() if k not in set(order)]
    final, inserted = [], False
    for t in prev:                       # keep the competition block where it already sits
        if key(t)[0] in comps:
            if not inserted:
                final.extend(ordered); inserted = True
            continue
        final.append(t)
    if not inserted:
        final.extend(ordered)
    return final

def cmd_build():
    # optional competition filter: `build NFL` builds only NFL and merges into manifest.json
    # optional team filters: `--new` (teams with no PNGs yet) / `--teams "A,B"`
    only, new_only, teams_filter = parse_build_args(sys.argv[2:])
    jobs, problems = collect_jobs(only)
    if only:
        jobs = [j for j in jobs if j["comp"] == only]
        problems = [] if only != "MSI2026" else problems
        if not jobs:
            print(f"No teams for competition {only!r}"); sys.exit(1)
    if problems:
        print("Refusing to build — unresolved matches:")
        for p in problems:
            print("  ", p)
        sys.exit(1)
    order = [(j["comp"], j["team"]) for j in jobs]      # canonical order, pre-filter
    if teams_filter is not None:
        unknown = teams_filter - {j["team"] for j in jobs}
        if unknown:
            print("Unknown team name(s):", ", ".join(sorted(unknown))); sys.exit(1)
        jobs = [j for j in jobs if j["team"] in teams_filter]
    if new_only:
        jobs = [j for j in jobs if not has_all_variants(j)]
    if not jobs:
        print("Nothing to build (all requested teams already have their 6 variants)."); return
    partial = new_only or teams_filter is not None
    manifest = []
    for i, j in enumerate(jobs, 1):
        sport_dir = {"MSI2026":"soccer","NBA":"nba","MLB":"mlb","NFL":"nfl"}[j["comp"]]
        master = os.path.join(MASTERS, sport_dir, j["slug"] + ".png")
        try:
            download(j["logo"], master)
            out_dir = os.path.join(ROOT, j["comp"], folder_name(j["group"]), folder_name(j["team"]))
            use, master_kind = pick_master(master, out_dir, j["slug"], sport_dir)
            files = generate(use, out_dir, j["slug"])
            manifest.append({"competition": j["comp"], "group": j["group"],
                             "team": j["team"], "slug": j["slug"],
                             "source_logo": j["logo"], "master": master_kind,
                             "matched_as": j["matched"],
                             "match_score": j["score"], "files": files})
            print(f"[{i:3d}/{len(jobs)}] {j['comp']:8s} {j['team']} ({master_kind})")
        except Exception as e:
            print(f"[{i:3d}/{len(jobs)}] FAILED {j['team']}: {e}")
            manifest.append({"competition": j["comp"], "team": j["team"], "error": str(e)})
        time.sleep(0.02)
    mpath = os.path.join(ROOT, "manifest.json")
    if (only or partial) and os.path.exists(mpath):
        prev = json.load(open(mpath))["teams"]
        comps = {j["comp"] for j in jobs}
        manifest = merge_manifest(prev, manifest, order, comps, partial)
    with open(mpath, "w") as f:
        json.dump({"generated_from": "ESPN public sports API (+ authentic SVG masters where available)",
                   "variants": [v[0] for v in VARIANTS],
                   "sizes": {"big": BIG, "small": SMALL},
                   "teams": manifest}, f, indent=2, ensure_ascii=False)
    ok = sum(1 for m in manifest if "files" in m)
    print(f"\nDONE: {ok} teams in manifest, {len(jobs)} built this run. manifest.json written.")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"report": cmd_report, "build": cmd_build}.get(mode, cmd_report)()
