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
  report  — resolve + verify all 160, print coverage table, download nothing
  fetch   — download verified SVGs into each team folder as <slug>.svg, write svg_manifest.json

Reads the canonical 160 teams from manifest.json (built by build_logos.py).
"""
import json, sys, os, re, time, unicodedata, urllib.parse, urllib.request
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WD = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"
UA = {"User-Agent": "rivalz-logo-fetch/1.0 (team logo gallery; contact ceo@rivalz.ai)"}

KEYWORDS = {"MSI2026": ("football", "soccer"), "NBA": ("basketball",), "MLB": ("baseball",)}

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
}

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
    teams = load_teams()
    rows = []
    for i, t in enumerate(teams, 1):
        r = resolve(t["name"], t["comp"])
        rows.append((t, r))
        time.sleep(0.05)
        if i % 20 == 0: print(f"  …resolved {i}/{len(teams)}", file=sys.stderr)
    by = {}
    for t, r in rows: by.setdefault(t["comp"], []).append((t, r))
    found = 0
    for comp in ("MSI2026", "MLB", "NBA"):
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

def cmd_fetch():
    teams = load_teams()
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
    json.dump({"source": "Wikidata P154 -> Wikimedia Commons", "teams": out},
              open(os.path.join(ROOT, "svg_manifest.json"), "w"), indent=2, ensure_ascii=False)
    print(f"\nDONE: {okn}/{len(teams)} SVGs fetched. svg_manifest.json written.")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"report": cmd_report, "fetch": cmd_fetch}.get(mode, cmd_report)()
