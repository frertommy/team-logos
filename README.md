# team-logos

Standardized logo assets for every team across **three competitions** — **160 teams, 960 images**.

| Competition | Teams | What it is |
|---|---|---|
| **MSI2026** | 100 | Soccer clubs across 9 leagues (Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Liga Portugal, + Galatasaray & Bodø/Glimt). Mirrors the canonical `teams` table. |
| **MLB** | 30 | Major League Baseball |
| **NBA** | 30 | National Basketball Association |

Every logo is the **current official crest** (latest as of the 2026-06-15 build), sourced as a transparent PNG.

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
├── manifest.json                   machine-readable index of every team + file + source
└── scripts/build_logos.py          reproducible fetch + generate pipeline
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

---

## Source, freshness & attribution

- Logos are fetched from **ESPN's public sports API** (`site.api.espn.com`) and logo CDN (`a.espncdn.com`), which serve each team's current official crest as a transparent PNG.
- **"Latest / 2026":** these are the live current crests at build time. Most crests are stable year to year, so "latest" means *current official*, not a guaranteed new-for-2026 redesign.
- ESPN's Serie A league feed lagged behind the promoted sides, so **Hellas Verona, Cremonese, and Pisa** were pulled directly by their verified ESPN team IDs (119, 4050, 3956).
- **Sporting CP** is the Lisbon club (disambiguated from Sporting Gijón).

### Trademarks
All club, league, and franchise logos are **trademarks of their respective owners** and are included here solely for team identification within Rivalz products. This repository is **private**. Respect each rights holder's guidelines before any public or commercial use.

## Regenerating

The entire set is reproducible. From the repo root:

```bash
python3 scripts/build_logos.py report   # match all teams to logos + print confidence (no downloads)
python3 scripts/build_logos.py build     # download masters + regenerate all 960 variants + manifest.json
```

Requires Python 3 with [Pillow](https://pypi.org/project/Pillow/). Raw downloaded masters land in `_masters/` (git-ignored); the script re-downloads as needed and skips files already present.

To change sizes or padding, edit the `BIG`, `SMALL`, `SQUARE_PAD`, `CIRCLE_PAD` constants at the top of `scripts/build_logos.py`.
