# team-logos

Standardized logo assets for every team across **four competitions** — **206 teams, 1,236 images** — plus a one-click **[per-competition zip](#download-all-logos-for-a-competition)** of each set.

| Competition | Teams | What it is |
|---|---|---|
| **MSI2026** | 114 | Soccer clubs across 9 leagues (Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Liga Portugal, + Galatasaray & Bodø/Glimt). Mirrors the canonical `teams` table — 100 original clubs plus the **14 promoted into the big-5 leagues for 2026-27** (added 2026-09-08; relegated clubs are kept, nothing is removed). |
| **MLB** | 30 | Major League Baseball |
| **NFL** | 32 | National Football League |
| **NBA** | 30 | National Basketball Association |

Every logo is the **current official crest** (latest as of the 2026-06-15 build), sourced as a transparent PNG. NFL (added 2026-08-06) and the 14 promoted MSI2026 clubs (added 2026-09-08) go one step further: their PNG sets are rasterized from the authentic vector crest at 2048px, then downscaled — noticeably crisper than CDN rasters. **112 of the 206 teams** additionally include an authentic **vector `.svg`** (see [Vector logos](#vector-svg-logos)).

---

## Folder structure

```
team-logos/
├── MSI2026/
│   └── <League>/<Team>/            e.g. MSI2026/Premier League/Arsenal/
├── MLB/
│   └── <American League|National League>/<Team>/
├── NBA/
│   └── <Eastern Conference|Western Conference>/<Team>/
├── NFL/
│   └── <AFC|NFC>/<Team>/                e.g. NFL/NFC/Dallas Cowboys/
├── downloads/
│   ├── MSI2026.zip · MLB.zip · NBA.zip · NFL.zip   one-click "download all" per competition
│   └── index.json                  sizes/counts the gallery reads to label the buttons
├── manifest.json                   machine-readable index of every team + file + source
├── svg_manifest.json               index of the authentic vector SVGs
└── scripts/
    ├── build_logos.py              reproducible fetch + generate pipeline (PNG variants + manifest.json)
    ├── fetch_svgs.py               authentic-SVG sourcing (Wikipedia / Wikimedia) + svg_manifest.json
    └── build_zips.py               regenerates downloads/*.zip + downloads/index.json
```

## The 6 variants per team

Each team folder contains six PNGs. **All have a transparent background** except the `_badge` files, which add a solid white disc.

| File suffix | Size | Shape | Background | Use for |
|---|---|---|---|---|
| `_big_square` | 512×512 | logo fills the square | transparent | cards, headers, hero art |
| `_big_circle` | 512×512 | logo inset to fit a circle | transparent | large circular avatars (won't clip when cropped round) |
| `_big_circle_badge` | 512×512 | logo on a white disc | white disc, transparent corners | avatars/badges on dark or busy backgrounds |
| `_small_square` | 128×128 | logo fills the square | transparent | lists, table rows, chips |
| `_small_circle` | 128×128 | logo inset to fit a circle | transparent | small circular avatars |
| `_small_circle_badge` | 128×128 | logo on a white disc | white disc, transparent corners | small badges |

**Square vs. circle:** the square variant fills the frame; the circle variant scales the logo down so its bounding box fits *inside* the inscribed circle — so if your UI crops the image to a round shape, nothing gets cut off.

File names are ASCII slugs of the team, e.g.:

```
MSI2026/Premier League/Arsenal/
  arsenal_big_square.png   arsenal_big_circle.png   arsenal_big_circle_badge.png
  arsenal_small_square.png arsenal_small_circle.png arsenal_small_circle_badge.png
```

## manifest.json

One entry per team with its competition, group (league/conference), the source logo URL it was built from, and the relative paths of all 6 generated files. Use this to wire logos into an app without walking the directory tree.

## Download all logos for a competition

The gallery ([index.html](https://frertommy.github.io/team-logos/)) shows a **"Download all &lt;competition&gt; logos"** button in the header of every competition and league/conference page. They serve pre-built archives committed under `downloads/`:

| Archive | Teams | Size | Contents |
|---|---|---|---|
| [`downloads/MSI2026.zip`](downloads/MSI2026.zip) | 114 | 30.7 MB | `MSI2026/<League>/<Team>/` — all 6 PNGs per team + 50 SVGs |
| [`downloads/MLB.zip`](downloads/MLB.zip) | 30 | 5.3 MB | `MLB/<League>/<Team>/` — all 6 PNGs per team + 26 SVGs |
| [`downloads/NBA.zip`](downloads/NBA.zip) | 30 | 7.1 MB | `NBA/<Conference>/<Team>/` — all 6 PNGs per team + 4 SVGs |
| [`downloads/NFL.zip`](downloads/NFL.zip) | 32 | 5.8 MB | `NFL/<Conference>/<Team>/` — all 6 PNGs per team + 32 SVGs |

Each zip keeps the exact repo directory tree for that competition and adds a `manifest.json` / `svg_manifest.json` holding just that competition's entries (same schema as the root files). Archives are deterministic (sorted entries, fixed timestamps), so regenerating on unchanged inputs is a no-op for git. If an archive ever exceeded 95 MB (GitHub's hard limit is 100 MB) `build_zips.py` splits it into `<COMP>-big.zip` (512px + SVG) and `<COMP>-small.zip` (128px) and the gallery shows both buttons — none needs that today.

Regenerate after any logo change: `python3 scripts/build_zips.py` (see [Regenerating](#regenerating)).

## Vector (SVG) logos

In addition to the PNGs, **112 of the 206 teams** also ship an authentic vector **`.svg`** (MSI2026 50 · MLB 26 · NBA 4 · NFL 32), placed next to the PNGs as `<slug>.svg` and indexed in `svg_manifest.json`.

- These are **real vector files — never auto-traced** from the PNGs. Sources: the current English-Wikipedia infobox crest (72), Wikimedia Commons `P154` (10), and hand-pinned English-Wikipedia crest files (30; fair-use vectors, the same route used for the NFL set).
- The remaining **94 teams have no usable SVG**: their current crests are copyrighted and exist only as raster / fair-use files (this is most of the marquee clubs — Arsenal, Real Madrid, Liverpool, Man Utd/City — and most NBA franchises). The 512px PNG is the asset for those.
- A few of the US vectors are official **cap/wordmark** marks (the only free vector available for that team).
- **Estac Troyes** is deliberately PNG-only: the Wikipedia "SVG" for the club is a bitmap wrapped in an `<svg>` (74 % embedded raster), so it is blocked in `fetch_svgs.py` rather than shipped as a fake vector. **Coventry**'s crest SVG is genuine vector artwork whose gradient fills are embedded raster tiles (official export); it is shipped with a `note` in `svg_manifest.json`.

Run `python3 scripts/fetch_svgs.py report` for exact per-team coverage.

---

## Source, freshness & attribution

- Logos are fetched from **ESPN's public sports API** and logo CDN (`a.espncdn.com`), which serve each team's current official crest as a transparent PNG. The original `site.api.espn.com` host has been 403-blocked since mid-2026; the build now uses `site.web.api.espn.com`, which serves the identical JSON (`ESPN_HOST` in `build_logos.py`).
- **2026-27 promoted clubs** (Coventry, Hull City, Ipswich · Deportivo La Coruna, Malaga, Racing Santander · Frosinone, Monza, Venezia · FC Schalke 04, SC Paderborn 07, SV Elversberg · Estac Troyes, Le Mans) were added 2026-09-08. Their PNG sets are rendered from the current Wikipedia infobox crest SVG at 2048px (`cairosvg`), with the ESPN raster kept as the shape-check reference and `source_logo` — except Troyes, which is built from the ESPN raster (see [Vector logos](#vector-svg-logos)). Deportivo's vector is the club's **new 2026 crest** ("A Coruña"), which ESPN's CDN had not yet picked up at build time.
- **"Latest / 2026":** these are the live current crests at build time. Most crests are stable year to year, so "latest" means *current official*, not a guaranteed new-for-2026 redesign.
- ESPN's Serie A league feed lagged behind the promoted sides, so **Hellas Verona, Cremonese, and Pisa** were pulled directly by their verified ESPN team IDs (119, 4050, 3956).
- **Sporting CP** is the Lisbon club (disambiguated from Sporting Gijón).

### Trademarks
All club, league, and franchise logos are **trademarks of their respective owners** and are included here solely for team identification within Rivalz products. This repository is **private**. Respect each rights holder's guidelines before any public or commercial use.

## Regenerating

The entire set is reproducible. From the repo root:

```bash
python3 scripts/build_logos.py report   # match all teams to logos + print confidence (no downloads)
python3 scripts/build_logos.py build     # download masters + regenerate all 1,236 variants + manifest.json
python3 scripts/build_logos.py build MSI2026 --new                  # only teams that have no PNGs yet
python3 scripts/build_logos.py build MSI2026 --teams "Coventry,Monza"  # only the named teams

python3 scripts/fetch_svgs.py report     # show authentic-SVG coverage per team (no downloads)
python3 scripts/fetch_svgs.py fetch      # download the verified vector SVGs + write svg_manifest.json
python3 scripts/fetch_svgs.py fetch MSI2026 --new                   # same --new / --teams filters

python3 scripts/build_zips.py            # rebuild downloads/*.zip + downloads/index.json (run last)
```

Adding teams end-to-end: append them to the `MSI` list (or the US team tables) in `build_logos.py`, then run `build <COMP> --new` → `fetch_svgs.py fetch <COMP> --new` → `build <COMP> --teams "…"` (so the PNGs are re-rendered from the SVG masters) → `build_zips.py`. Team-filtered runs merge into the manifests by team and leave every other entry byte-for-byte untouched.

Requires Python 3 with [Pillow](https://pypi.org/project/Pillow/); [cairosvg](https://pypi.org/project/CairoSVG/) (plus the `cairo` C library, e.g. `brew install cairo`) is needed to render SVG masters — without it the build silently falls back to the CDN raster. Raw downloaded masters land in `_masters/` (git-ignored); the script re-downloads as needed and skips files already present.

To change sizes or padding, edit the `BIG`, `SMALL`, `SQUARE_PAD`, `CIRCLE_PAD` constants at the top of `scripts/build_logos.py`.
