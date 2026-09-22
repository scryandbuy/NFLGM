"""
FETCH THE CFB 27 RATINGS FROM EA'S HUB, every player, every attribute.

EA's ratings site is a Next.js app. There is no public REST API, but the
server-rendered data is served at the Next.js data endpoint:

    https://www.ea.com/_next/data/<buildId>/games/ea-sports-college-football/
        ratings.json?franchiseSlug=ea-sports-college-football&team=<teamId>

The buildId rotates with each deploy and is read off the ratings page. One
request per team (138), full roster each, no pagination. Standard library
only. Writes cfb27_ratings.csv beside this file with one row per player and
one column per rating, named the way the Madden seed names them
(speed_rating, throw_acc_short_rating, ...), plus team, position, class
(FR/SO/JR/SR, redshirt flag), dev trait, archetype, height, weight.

Run it anywhere with internet:   python3 fetch_cfb27.py
"""
import csv, json, re, sys, time, urllib.request
from pathlib import Path

RATINGS_URL = "https://www.ea.com/games/ea-sports-college-football/ratings"
DATA_TMPL = ("https://www.ea.com/_next/data/{build_id}/games/"
             "ea-sports-college-football/ratings.json?franchiseSlug=ea-sports-college-football")
HEADERS = {"User-Agent": "Mozilla/5.0 (nfl-gm-sim; research use)"}
OUT = Path(__file__).with_name("cfb27_ratings.csv")
RAW = Path(__file__).with_name("cfb27_raw")


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def build_id():
    html = get(RATINGS_URL)
    m = re.search(r'"buildId":"([^"]+)"', html)
    if not m:
        raise SystemExit("could not find the Next.js buildId on the ratings page")
    return m.group(1)


def teams(base):
    out, seen = [], set()
    for group in base["pageProps"]["ratingsFilters"].get("teamGroups", []):
        conf = group.get("label", group.get("id", ""))
        for t in group.get("teams", []):
            if t["id"] not in seen:
                seen.add(t["id"]); out.append(dict(id=t["id"], name=t["label"], conference=conf))
    return out


def snake(s):
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def flatten(item, team):
    """One player row. Every numeric rating becomes <name>_rating."""
    row = dict(team=team["name"], conference=team["conference"], team_id=team["id"])
    for k in ("firstName", "lastName", "fullName", "jerseyNum", "schoolYear", "height",
              "weight", "overallRating", "archetype", "playerAbilities"):
        v = item.get(k)
        if isinstance(v, dict): v = v.get("label") or v.get("id")
        if isinstance(v, list): v = "|".join(str(x.get("label", x) if isinstance(x, dict) else x) for x in v)
        row[snake(k)] = v
    pos = item.get("position") or {}
    row["position"] = pos.get("id") or pos.get("label")
    for k in ("team", "devTrait", "iteration", "class"):
        v = item.get(k)
        if isinstance(v, dict): v = v.get("label") or v.get("id")
        if v is not None: row[snake(k)] = v
    # the ratings live under stats: {speed: {value: 91, ...}, ...} on the hub;
    # take whatever numeric block is there
    stats = item.get("stats") or {}
    for k, v in stats.items():
        val = v.get("value") if isinstance(v, dict) else v
        if isinstance(val, (int, float)):
            row[snake(k) + "_rating"] = val
    # anything else numeric and not yet captured
    for k, v in item.items():
        if isinstance(v, (int, float)) and snake(k) not in row and k not in ("overallRating",):
            row[snake(k)] = v
    return row


def main():
    RAW.mkdir(exist_ok=True)
    bid = build_id()
    print("buildId", bid)
    base = json.loads(get(DATA_TMPL.format(build_id=bid)))
    tl = teams(base)
    print(len(tl), "teams")
    rows = []
    for i, t in enumerate(tl, 1):
        p = RAW / f"{t['id']}.json"
        if p.exists():
            data = json.loads(p.read_text())
        else:
            data = json.loads(get(DATA_TMPL.format(build_id=bid) + f"&team={t['id']}"))
            p.write_text(json.dumps(data)); time.sleep(0.4)
        items = data["pageProps"]["ratingDetails"]["items"]
        rows += [flatten(it, t) for it in items]
        print(f"  {i:3d}/{len(tl)} {t['name']}: {len(items)}", flush=True)
    cols = []
    for r in rows:
        for k in r:
            if k not in cols: cols.append(k)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    print(f"wrote {len(rows)} players, {len(cols)} columns -> {OUT}")


if __name__ == "__main__":
    main()
