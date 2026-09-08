#!/usr/bin/env python3
"""
fetch_svgs.py — source AUTHENTIC vector SVG logos (no tracing) from Wikidata/Commons.

Strategy (free + license-clean + verifiable):
  1. Resolve each team to its Wikidata entity via wbsearchentities.
  2. Accept the entity ONLY if its English description matches the sport
     (football/soccer | basketball | baseball) AND its label matches the team
     name — otherwise reject (better a miss than the wrong club's logo).
  3. Read the entity's logo image (property P154); keep it only if it is an .svg
     on Wikimedia Commons. Optional Commons file-search fallback (flagged).

Modes:
  report  — resolve + verify all teams, print coverage table, download nothing
  fetch   — download verified SVGs into each team folder as <slug>.svg, write svg_manifest.json

  Both accept an optional competition (e.g. `fetch MSI2026`) and, for fetch, team filters:
    --new              only teams that have no record in svg_manifest.json yet
    --teams "A,B,C"    only the named teams
  Filtered fetches merge into svg_manifest.json by slug; untouched records are kept.

Reads the canonical team list from manifest.json (built by build_logos.py).
"""
import json, sys, os, re, time, unicodedata, urllib.parse, urllib.request
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WD = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"
UA = {"User-Agent": "rivalz-logo-fetch/1.0 (team logo gallery; contact ceo@rivalz.ai)"}

KEYWORDS = {"MSI2026": ("football", "soccer"), "NBA": ("basketball",), "MLB": ("baseball",),
            "NFL": ("american football", "football")}

# Better search strings for ambiguous / short names (disambiguates the Wikidata hit).
QUERY_ALIAS = {
    "Inter": "Inter Milan", "Wolves": "Wolverhampton Wanderers",
    "Tottenham": "Tottenham Hotspur", "Newcastle": "Newcastle United F.C.",
    "West Ham": "West Ham United", "Brighton": "Brighton & Hove Albion",
    "Bournemouth": "AFC Bournemouth", "Leeds": "Leeds United",
    "Sporting CP": "Sporting CP", "Lyon": "Olympique Lyonnais",
    "Marseille": "Olympique de Marseille", "Monaco": "AS Monaco",
    "Nice": "OGC Nice", "Lens": "RC Lens", "Rennes": "Stade Rennais",
    "Strasbourg": "RC Strasbourg", "Le Havre": "Le Havre AC",
    "Stade Brestois 29": "Stade Brestois 29", "Paris FC": "Paris FC",
    "Paris Saint Germain": "Paris Saint-Germain", "Hellas Verona": "Hellas Verona FC",
    "Genoa": "Genoa CFC", "Como": "Como 1907", "Atletico Madrid": "Atletico Madrid",
    "Athletic Club": "Athletic Bilbao", "Celta Vigo": "RC Celta de Vigo",
    "Oviedo": "Real Oviedo", "Alaves": "Deportivo Alaves", "Espanyol": "RCD Espanyol",
    "Mallorca": "RCD Mallorca", "1. FC Köln": "1. FC Köln", "1899 Hoffenheim": "TSG 1899 Hoffenheim",
    "FSV Mainz 05": "1. FSV Mainz 05", "Union Berlin": "1. FC Union Berlin",
    "Hamburger SV": "Hamburger SV", "RB Leipzig": "RB Leipzig",
    "Bodo/Glimt": "FK Bodø/Glimt", "Galatasaray": "Galatasaray S.K. (football)",
    "Inter Milan": "Inter Milan",
    # promoted 2026-27
    "Coventry": "Coventry City", "Ipswich": "Ipswich Town",
    "Deportivo La Coruna": "Deportivo de La Coruña", "Malaga": "Málaga CF",
    "Racing Santander": "Racing de Santander", "Frosinone": "Frosinone Calcio",
    "Monza": "AC Monza", "Venezia": "Venezia FC", "Estac Troyes": "ES Troyes AC",
    "Le Mans": "Le Mans FC",
}

# Direct English-Wikipedia article titles for teams whose name collides with a city/word,
# so Wikidata entity search fails. These are tried first, straight to the infobox SVG.
TITLE_OVERRIDE = {
    "Galatasaray": "Galatasaray S.K.",
    "Metz": "FC Metz",
    "Nantes": "FC Nantes",
    "Bodo/Glimt": "FK Bodø/Glimt",
    # promoted 2026-27 — infobox crest lives on Commons, go straight to the article
    "FC Schalke 04": "FC Schalke 04",
    "SC Paderborn 07": "SC Paderborn 07",
    "SV Elversberg": "SV Elversberg",
}

# Crests absent from Commons/Wikidata P154 but hosted on English Wikipedia as
# fair-use vector files. Pinned by exact enwiki file name (verified by hand).
ENWIKI_FILEPATH = "https://en.wikipedia.org/wiki/Special:FilePath/"
ENWIKI_FILE = {
    "Atlanta Falcons": "Atlanta Falcons logo.svg",
    "Denver Broncos": "Denver Broncos logo.svg",
    "Los Angeles Rams": "LA Rams logo.svg",
    "Miami Dolphins": "Miami Dolphins logo.svg",
    "Minnesota Vikings": "Minnesota Vikings logo.svg",
    "New England Patriots": "New England Patriots logo.svg",
    "Philadelphia Eagles": "Philadelphia Eagles logo.svg",
    # articles whose infobox pageimage is the wordmark — pin the crest file
    "Cleveland Browns": "Cleveland Browns logo.svg",
    "Detroit Lions": "Detroit Lions logo.svg",
    "Houston Texans": "Houston Texans logo.svg",
    "Jacksonville Jaguars": "Jacksonville Jaguars logo.svg",
    "Las Vegas Raiders": "Las Vegas Raiders logo.svg",
    "Seattle Seahawks": "Seattle Seahawks logo.svg",
    "Tampa Bay Buccaneers": "Tampa Bay Buccaneers logo.svg",
    "Tennessee Titans": "Tennessee Titans Logo 2026.svg",
    "New York Jets": "New York Jets logo.svg",
    "Arizona Cardinals": "Arizona Cardinals logo.svg",
    "Baltimore Ravens": "Baltimore Ravens logo.svg",
    "Chicago Bears": "Chicago Bears logo primary.svg",
    "Carolina Panthers": "Carolina Panthers logo.svg",
    # MSI2026 clubs promoted for 2026-27 (current enwiki infobox crest, verified 2026-09-08)
    "Coventry": "Coventry City FC crest.svg",
    "Hull City": "Hull City A.F.C. logo.svg",
    "Ipswich": "Ipswich Town.svg",
    "Deportivo La Coruna": "RC Deportivo A Coruña logo 2026.svg",   # new 2026 crest
    "Malaga": "Málaga CF.svg",
    "Racing Santander": "Racing de Santander logo.svg",
    "Frosinone": "Frosinone Calcio logo.svg",
    "Monza": "AC Monza logo (2021).svg",
    "Venezia": "Venezia FC crest.svg",
    "Le Mans": "Le Mans FC logo.svg",
}

# Files that are real vector artwork but carry embedded raster pattern/gradient fills
# (official Illustrator exports). Shipped as-is; the note is written to svg_manifest.json.
SVG_NOTE = {
    "Coventry": "vector paths with embedded raster gradient fills (official export as published on Wikipedia)",
}

# Teams whose only available SVG must NOT be shipped, with the reason:
#  - wordmark: the only free SVG is a wide WORDMARK (not the crest/badge). Verified by
#    rendering + comparing to the trusted ESPN PNG (low shape-IoU, ar > 4).
#  - raster-embedded: the Wikipedia "SVG" is a bitmap wrapped in an <svg> (the crest
#    artwork is embedded <image> tiles, only overlays are paths) — not a real vector.
# Blocked teams keep the CDN-raster PNG set only.
BLOCK = {"Toronto Blue Jays": "wordmark", "Golden State Warriors": "wordmark", "AS Roma": "wordmark",
         "Estac Troyes": "raster-embedded"}   # ESTAC_Troyes_Logo.svg: 74% base64 PNG

def strip_accents(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
def norm(s):
    s = strip_accents(s).lower()
    s = re.sub(r"\b(fc|cf|afc|ac|as|sc|ssc|rc|cd|ud|ss|sv|tsg|fsv|sk|fk|cfc|f c|s k)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())
def ratio(a, b): return SequenceMatcher(None, norm(a), norm(b)).ratio()
def toks(s): return set(norm(s).split())

def api(base, params, tries=4):
    params = {**params, "format": "json"}
    url = base + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as f:
                return json.loads(f.read())
        except Exception as e:
            if i == tries - 1: raise
            time.sleep(0.6)

def wbsearch(q):
    d = api(WD, {"action": "wbsearchentities", "search": q, "language": "en",
                 "uselang": "en", "type": "item", "limit": 12})
    out = []
    for h in d.get("search", []):
        out.append({"id": h["id"], "label": h.get("label", ""),
                    "desc": (h.get("description") or "")})
    return out

def logo_files(qid):
    d = api(WD, {"action": "wbgetclaims", "entity": qid, "property": "P154"})
    files = []
    for c in d.get("claims", {}).get("P154", []):
        try:
            files.append(c["mainsnak"]["datavalue"]["value"])
        except Exception:
            pass
    return files

def label_matches(team, label):
    q = QUERY_ALIAS.get(team, team)
    if toks(q) and toks(q) <= toks(label): return True
    if toks(team) and toks(team) <= toks(label): return True
    return ratio(q, label) >= 0.6 or ratio(team, label) >= 0.6

# Reject women's/reserve/youth/unrelated entities (Eintracht women, Dortmund II, "Boston Massacre"…)
REJECT = re.compile(r"\b(women|woman|femenin\w*|f[eé]minin\w*|ladies|reserve\w*|youth|academy|"
                    r"u1[5-9]|u2[0-3]|massacre|season|history|stadium|supporters)\b|\b(ii|b)\b", re.I)

def enwiki_title(qid):
    d = api(WD, {"action": "wbgetentities", "ids": qid, "props": "sitelinks"})
    try:
        return d["entities"][qid]["sitelinks"]["enwiki"]["title"]
    except Exception:
        return None

def wiki_pageimage(title):
    d = api("https://en.wikipedia.org/w/api.php",
            {"action": "query", "redirects": 1, "prop": "pageimages",
             "piprop": "original", "titles": title})
    try:
        p = list(d["query"]["pages"].values())[0]
        return p.get("original", {}).get("source")
    except Exception:
        return None

def resolve(team, comp):
    ef = ENWIKI_FILE.get(team)
    if ef:
        return {"status": "svg", "src": "enwiki-file-pin",
                "url": ENWIKI_FILEPATH + urllib.parse.quote(ef.replace(" ", "_")),
                "file": ef, "qid": None, "label": team, "desc": "(enwiki file pin)"}
    if team in BLOCK:
        return {"status": "blocked-" + BLOCK[team], "label": team,
                "desc": {"wordmark": "only a free wordmark exists; keep PNG",
                         "raster-embedded": "Wikipedia SVG is a wrapped bitmap; keep PNG"}[BLOCK[team]],
                "file": None}
    to = TITLE_OVERRIDE.get(team)
    if to:
        img = wiki_pageimage(to)
        if img and img.lower().rsplit("?", 1)[0].endswith(".svg"):
            return {"status": "svg", "src": "wikipedia", "url": img, "file": to,
                    "qid": None, "label": to, "desc": "(title override)"}
    q = QUERY_ALIAS.get(team, team)
    kw = KEYWORDS[comp]
    hits = wbsearch(q)
    chosen = None
    for h in hits:
        if REJECT.search(h["label"]) or REJECT.search(h["desc"]):
            continue
        if any(k in h["desc"].lower() for k in kw) and label_matches(team, h["label"]):
            chosen = h; break
    if not chosen:
        return {"status": "no-entity", "tried": q,
                "top": (hits[0]["label"] + " — " + hits[0]["desc"]) if hits else ""}
    base = {"qid": chosen["id"], "label": chosen["label"], "desc": chosen["desc"]}
    # 1) current infobox SVG from English Wikipedia (free + correct men's-club entity)
    title = enwiki_title(chosen["id"])
    if title:
        img = wiki_pageimage(title)
        if img and img.lower().rsplit("?", 1)[0].endswith(".svg"):
            return {**base, "status": "svg", "src": "wikipedia", "url": img, "file": title}
    # 2) Wikidata P154 SVG fallback (Commons)
    files = logo_files(chosen["id"])
    svgs = [f for f in files if f.lower().endswith(".svg")]
    if svgs:
        return {**base, "status": "svg", "src": "commons-p154",
                "url": file_url(svgs[0]), "file": svgs[0]}
    return {**base, "status": ("png-only" if files else "no-logo"),
            "file": files[0] if files else None}

def load_teams():
    d = json.load(open(os.path.join(ROOT, "manifest.json")))
    teams = []
    for t in d["teams"]:
        if "files" not in t: continue
        folder = os.path.dirname(t["files"][0])
        teams.append({"name": t["team"], "slug": t["slug"], "comp": t["competition"],
                      "group": t["group"], "folder": folder})
    return teams

def file_url(fname):
    return FILEPATH + urllib.parse.quote(fname.replace(" ", "_"))

def cmd_report():
    only = sys.argv[2] if len(sys.argv) > 2 else None
    teams = load_teams()
    if only: teams = [t for t in teams if t["comp"] == only]
    rows = []
    for i, t in enumerate(teams, 1):
        r = resolve(t["name"], t["comp"])
        rows.append((t, r))
        time.sleep(0.05)
        if i % 20 == 0: print(f"  …resolved {i}/{len(teams)}", file=sys.stderr)
    by = {}
    for t, r in rows: by.setdefault(t["comp"], []).append((t, r))
    found = 0
    for comp in ("MSI2026", "MLB", "NBA", "NFL"):
        lst = by.get(comp, [])
        svg = [x for x in lst if x[1]["status"] == "svg"]
        found += len(svg)
        print(f"\n## {comp}: {len(svg)}/{len(lst)} have an authentic SVG")
        for t, r in lst:
            if r["status"] != "svg":
                print(f"   --   {t['name']:26s} [{r['status']}] {r.get('label','')} {('· '+r.get('desc','')) if r.get('desc') else r.get('top','')}")
        print("   --- found: ---")
        for t, r in svg:
            print(f"   ok   {t['name']:26s} [{r.get('src')}] {r['file']}")
    print(f"\nTOTAL authentic SVGs: {found}/{len(teams)}")

def parse_args(argv):
    """[COMP] [--new] [--teams A,B,C | --teams=A,B,C]"""
    only, new_only, names = None, False, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--new": new_only = True
        elif a.startswith("--teams="): names = a.split("=", 1)[1]
        elif a == "--teams": i += 1; names = argv[i] if i < len(argv) else ""
        elif not a.startswith("--"): only = a
        i += 1
    if names is not None: names = {n.strip() for n in names.split(",") if n.strip()}
    return only, new_only, names

def cmd_fetch():
    only, new_only, names = parse_args(sys.argv[2:])
    spath = os.path.join(ROOT, "svg_manifest.json")
    prev = json.load(open(spath))["teams"] if os.path.exists(spath) else []
    prev_by_slug = {t["slug"]: t for t in prev}
    all_teams = load_teams()
    teams = [t for t in all_teams if t["comp"] == only] if only else list(all_teams)
    if names is not None:
        unknown = names - {t["name"] for t in teams}
        if unknown: print("Unknown team name(s):", ", ".join(sorted(unknown))); sys.exit(1)
        teams = [t for t in teams if t["name"] in names]
    if new_only:
        teams = [t for t in teams if t["slug"] not in prev_by_slug]
    if not teams:
        print("Nothing to fetch."); return
    partial = new_only or names is not None
    out = []
    okn = 0
    for i, t in enumerate(teams, 1):
        r = resolve(t["name"], t["comp"])
        rec = {"team": t["name"], "slug": t["slug"], "competition": t["comp"], "group": t["group"]}
        if r["status"] == "svg":
            url = r["url"]
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as f:
                    data = f.read()
                head = data[:300].lstrip()
                if not (head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in data[:1000]):
                    raise ValueError("not an SVG payload")
                dest = os.path.join(ROOT, t["folder"], t["slug"] + ".svg")
                with open(dest, "wb") as o: o.write(data)
                rec.update({"svg": os.path.relpath(dest, ROOT), "source": url,
                            "src": r.get("src"), "wikidata": r["qid"],
                            "commons_file": r["file"], "bytes": len(data)})
                if t["name"] in SVG_NOTE: rec["note"] = SVG_NOTE[t["name"]]
                okn += 1
                print(f"[{i:3d}/{len(teams)}] OK   {t['name']} ({len(data)} B)")
            except Exception as e:
                rec.update({"svg": None, "error": str(e), "attempted": url})
                print(f"[{i:3d}/{len(teams)}] FAIL {t['name']}: {e}")
        else:
            rec.update({"svg": None, "reason": r["status"]})
            print(f"[{i:3d}/{len(teams)}] --   {t['name']} ({r['status']})")
        out.append(rec)
        time.sleep(0.05)
    if prev and (only or partial):
        fetched = {t["slug"]: t for t in out}
        if partial:
            # merge by slug; order follows manifest.json for every team that has a record
            merged = {**prev_by_slug, **fetched}
            out = [merged[t["slug"]] for t in all_teams if t["slug"] in merged]
            out += [v for k, v in merged.items() if k not in {t["slug"] for t in all_teams}]
        else:
            out = [t for t in prev if t.get("competition") != only] + out
    json.dump({"source": "Wikidata P154 -> Wikimedia Commons", "teams": out},
              open(spath, "w"), indent=2, ensure_ascii=False)
    print(f"\nDONE: {okn}/{len(teams)} SVGs fetched. svg_manifest.json written.")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"report": cmd_report, "fetch": cmd_fetch}.get(mode, cmd_report)()
