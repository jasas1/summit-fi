#!/usr/bin/env python3
"""Rebuild the summit-fi site from the trackpicker data — one command.

Reads the trackpicker "full" pool (candidates + Jev scores + profiles), then
regenerates:
  - csv/summit-fi-all.csv, one csv/summit-fi-<genre>.csv per genre,
    and the three csv/summit-fi-<profile>-top10.csv playlists;
  - index.html, by filling template.html with the current rows and stats.

Design lives in template.html (edit it, then re-run). Data and stats come from
trackpicker, so the page and the counts stay in sync with the pool.

Usage:
  python3 regenerate.py                 # uses ~/DEV/trackpicker
  TRACKPICKER=/path/to/trackpicker python3 regenerate.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRACKPICKER = Path(os.environ.get("TRACKPICKER", Path.home() / "DEV" / "trackpicker"))
SET = "full"  # which trackpicker data set to publish

# Fixed profile order — must match the PROFILES array in template.html
# (each row carries these three composites and ranks, in this order).
PROFILES = [
    {"key": "showcase", "csv": "summit-fi-showcase-top10.csv"},
    {"key": "tube-magic", "csv": "summit-fi-tubemagic-top10.csv"},
    {"key": "stress-test", "csv": "summit-fi-stresstest-top10.csv"},
]
GENRE_ORDER = ["jazz", "vocal", "classical", "acoustic", "pop", "rock", "electronic", "other"]


def die(msg: str) -> None:
    sys.exit(f"regenerate.py: {msg}")


def main() -> int:
    if not TRACKPICKER.is_dir():
        die(f"trackpicker not found at {TRACKPICKER} (set TRACKPICKER=/path).")
    sys.path.insert(0, str(TRACKPICKER))
    try:
        import trackpicker as tp  # noqa: E402
    except Exception as e:  # pragma: no cover
        die(f"could not import trackpicker.py from {TRACKPICKER}: {e}")

    data = TRACKPICKER / "data" / SET
    cand_f, scores_f = data / "candidates.json", data / "scores.json"
    if not scores_f.exists():
        die(f"{scores_f} missing — run `trackpicker.py --set {SET} score` first.")
    tracks = tp.load_json(cand_f)
    scores = tp.load_json(scores_f)
    profiles = tp.load_json(TRACKPICKER / "data" / "profiles.json")
    manifest = tp.load_json(TRACKPICKER / "data" / "dimensions.json")
    labels = {d: manifest["dimensions"][d]["label"] for d in manifest["dimensions"]}
    for p in PROFILES:
        if p["key"] not in profiles:
            die(f"profile '{p['key']}' missing from profiles.json")

    # top-N rank per profile (which tracks make each top 10, and in what order)
    ranks: dict[str, dict[str, int]] = {}
    for p in PROFILES:
        for i, picked in enumerate(tp.pick(tracks, scores, profiles[p["key"]], 10), 1):
            ranks.setdefault(picked["track"]["id"], {})[p["key"]] = i

    # rows: [title, artist, album, genre, best, sc0, sc1, sc2, rk0, rk1, rk2, listen]
    rows = []
    for t in tracks:
        entry = scores[t["id"]]
        dims = entry["dimensions"]
        best = max(dims, key=lambda d: dims[d]["normalized"])
        comps = [round(tp.composite(entry, profiles[p["key"]]), 2) for p in PROFILES]
        rk = ranks.get(t["id"], {})
        listen = (t.get("listen_for") or "").strip()
        if len(listen) > 170:
            listen = listen[:167].rsplit(" ", 1)[0] + "…"
        rows.append([t["title"], t["artist"], t.get("album") or "", t["genre"], labels[best],
                     comps[0], comps[1], comps[2],
                     rk.get(PROFILES[0]["key"], 0), rk.get(PROFILES[1]["key"], 0), rk.get(PROFILES[2]["key"], 0),
                     listen])

    # stats
    total = len(rows)
    confs = [x["confidence"] for v in scores.values() for x in v["dimensions"].values()]
    mean_conf = f"{sum(confs) / len(confs):.2f}" if confs else "0.00"
    present = [g for g in GENRE_ORDER if any(t["genre"] == g for t in tracks)]

    # write CSVs
    csv_dir = HERE / "csv"
    csv_dir.mkdir(exist_ok=True)

    def write_csv(path: Path, items):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["title", "artist", "album"])
            w.writerows([t["title"], t["artist"], t.get("album") or ""] for t in items)

    write_csv(csv_dir / "summit-fi-all.csv", tracks)
    for g in present:
        write_csv(csv_dir / f"summit-fi-{g}.csv", [t for t in tracks if t["genre"] == g])
    for p in PROFILES:
        top = [picked["track"] for picked in tp.pick(tracks, scores, profiles[p["key"]], 10)]
        write_csv(csv_dir / p["csv"], top)

    # fill the template
    template = (HERE / "template.html").read_text(encoding="utf-8")
    out = (template
           .replace("__ROWS__", json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
           .replace("__TOTAL__", str(total))
           .replace("__GENRES__", str(len(present)))
           .replace("__MEANCONF__", mean_conf))
    if "__ROWS__" in out or "__TOTAL__" in out:
        die("template still has unfilled placeholders")
    (HERE / "index.html").write_text(out, encoding="utf-8")

    print(f"regenerated: {total} tracks, {len(present)} genres, mean confidence {mean_conf}")
    print(f"  index.html + {1 + len(present) + len(PROFILES)} CSVs written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
