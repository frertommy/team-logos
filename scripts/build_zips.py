#!/usr/bin/env python3
"""
build_zips.py — pre-built per-competition ZIP archives for the gallery's "Download all" buttons.

For every competition in manifest.json this writes downloads/<COMP>.zip containing
  <COMP>/<Group>/<Team>/<slug>_<variant>.png   all 6 PNG variants of every team
  <COMP>/<Group>/<Team>/<slug>.svg             the authentic vector, where one exists
  manifest.json                                the manifest entries for that competition
  svg_manifest.json                            the svg_manifest entries for that competition
and downloads/index.json — what index.html reads to label the buttons (teams, bytes, files).

GitHub refuses files over 100 MB (and warns over 50 MB). If a competition's archive would
exceed SPLIT_MB it is split into <COMP>-big.zip (512px variants + SVGs) and
<COMP>-small.zip (128px variants), each carrying the same manifest files.

Archives are deterministic — sorted entries, fixed timestamps — so re-running on unchanged
inputs yields byte-identical zips and no spurious git churn.

Usage:
  python3 scripts/build_zips.py            # rebuild every competition + downloads/index.json
  python3 scripts/build_zips.py NFL MLB    # only these (index.json is updated for them)
Run this after build_logos.py / fetch_svgs.py so the archives match the committed PNG/SVG set.
"""
import io, json, os, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "downloads")
SPLIT_MB = 95                      # hard ceiling per archive (GitHub blocks > 100 MB)
FIXED_TIME = (2020, 1, 1, 0, 0, 0)  # constant entry timestamp -> reproducible archives
COMP_ORDER = ["MSI2026", "MLB", "NBA", "NFL"]

def load(name):
    p = os.path.join(ROOT, name)
    return json.load(open(p)) if os.path.exists(p) else None

def add_bytes(zf, arcname, data):
    zi = zipfile.ZipInfo(arcname, date_time=FIXED_TIME)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    zf.writestr(zi, data)

def write_zip(path, files, manifest_doc, svg_doc):
    """files: sorted list of repo-relative paths. Returns bytes written."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in files:
            with open(os.path.join(ROOT, rel), "rb") as f:
                add_bytes(zf, rel, f.read())
        add_bytes(zf, "manifest.json", json.dumps(manifest_doc, indent=2, ensure_ascii=False).encode())
        if svg_doc is not None:
            add_bytes(zf, "svg_manifest.json", json.dumps(svg_doc, indent=2, ensure_ascii=False).encode())
    return os.path.getsize(path)

def build(comp, manifest, svgm):
    teams = [t for t in manifest["teams"] if t.get("competition") == comp and "files" in t]
    svg_recs = [t for t in (svgm or {"teams": []})["teams"] if t.get("competition") == comp]
    svgs = [t["svg"] for t in svg_recs if t.get("svg") and os.path.exists(os.path.join(ROOT, t["svg"]))]
    pngs = [f for t in teams for f in t["files"] if os.path.exists(os.path.join(ROOT, f))]
    missing = [f for t in teams for f in t["files"] if not os.path.exists(os.path.join(ROOT, f))]
    if missing:
        raise SystemExit(f"{comp}: {len(missing)} manifest files missing on disk, e.g. {missing[0]}")
    header = {k: v for k, v in manifest.items() if k != "teams"}
    mdoc = {**header, "competition": comp, "teams": teams}
    sdoc = ({**{k: v for k, v in svgm.items() if k != "teams"}, "competition": comp, "teams": svg_recs}
            if svgm else None)

    big = sorted([f for f in pngs if "_big_" in os.path.basename(f)] + svgs)
    small = sorted(f for f in pngs if "_small_" in os.path.basename(f))
    total = sum(os.path.getsize(os.path.join(ROOT, f)) for f in big + small)
    os.makedirs(OUT, exist_ok=True)
    entry = {"teams": len(teams), "svgs": len(svgs), "files": []}
    if total <= SPLIT_MB * 1024 * 1024:
        for stale in (f"{comp}-big.zip", f"{comp}-small.zip"):
            if os.path.exists(os.path.join(OUT, stale)): os.remove(os.path.join(OUT, stale))
        path = os.path.join(OUT, f"{comp}.zip")
        n = write_zip(path, sorted(big + small), mdoc, sdoc)
        entry["files"].append({"file": f"downloads/{comp}.zip", "bytes": n, "part": "all",
                               "label": "all variants + SVG"})
    else:
        if os.path.exists(os.path.join(OUT, f"{comp}.zip")): os.remove(os.path.join(OUT, f"{comp}.zip"))
        for part, files, label in (("big", big, "512px variants + SVG"), ("small", small, "128px variants")):
            path = os.path.join(OUT, f"{comp}-{part}.zip")
            n = write_zip(path, files, mdoc, sdoc)
            entry["files"].append({"file": f"downloads/{comp}-{part}.zip", "bytes": n, "part": part, "label": label})
    for f in entry["files"]:
        if f["bytes"] > SPLIT_MB * 1024 * 1024:
            raise SystemExit(f"{f['file']} is {f['bytes']/1e6:.1f} MB — over the {SPLIT_MB} MB ceiling")
        print(f"  {f['file']:32s} {f['bytes']/1048576:6.1f} MB  ({entry['teams']} teams, {entry['svgs']} SVG)")
    return entry

def main():
    manifest, svgm = load("manifest.json"), load("svg_manifest.json")
    if not manifest:
        raise SystemExit("manifest.json not found — run build_logos.py first")
    present = [c for c in COMP_ORDER if any(t.get("competition") == c for t in manifest["teams"])]
    present += sorted({t.get("competition") for t in manifest["teams"]} - set(present) - {None})
    wanted = sys.argv[1:] or present
    unknown = [c for c in wanted if c not in present]
    if unknown:
        raise SystemExit(f"unknown competition(s): {unknown}; have {present}")
    ipath = os.path.join(OUT, "index.json")
    index = json.load(open(ipath)) if os.path.exists(ipath) else {"competitions": {}}
    for comp in wanted:
        print(f"{comp}:")
        index["competitions"][comp] = build(comp, manifest, svgm)
    index["competitions"] = {c: index["competitions"][c] for c in present if c in index["competitions"]}
    index["split_mb"] = SPLIT_MB
    with open(ipath, "w") as f:
        json.dump(index, f, indent=2)
    print(f"downloads/index.json written ({len(index['competitions'])} competitions)")

if __name__ == "__main__":
    main()
