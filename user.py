"""Summit guide: Velib' bikes around the Carrousel du Louvre, live.

A function for the OVHcloud Serverless alpha demo. The handler is `main`, it
takes no argument and returns a small web page (add `?format=json` for the
raw data). Standard library only.

Data: Velib' Metropole open data (GBFS feeds, no key needed).

Environment:
  SUMMIT_RELEASE   the release that deployed this revision (set by the deploy
                   workflow, default "dev")
  SUMMIT_NAME      place name (default "Carrousel du Louvre")
  SUMMIT_LAT/LON   place coordinates (default 48.86183, 2.33431, OpenStreetMap)
"""

from __future__ import annotations

import json
import math
import os
import socket
import time
import urllib.request

FEED = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole"
INFO_URL = FEED + "/station_information.json"
STATUS_URL = FEED + "/station_status.json"

# Station information (names, positions) barely changes: keep it for an hour.
# Station status (bikes, docks) changes all the time: keep it 30 seconds.
# The cache lives in the instance: warm calls reuse it, a cold start empties it.
INFO_TTL = 3600
STATUS_TTL = 30
_cache: dict = {}

# Walking speed used for the "minutes on foot" estimate, in metres per minute.
WALK_M_PER_MIN = 75

_STARTED_AT = time.monotonic()
_CALLS = 0


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


USER_AGENT = "ovhcloud-serverless-summit-guide/1.0 (+https://github.com/antonin-a/serverless-fn-summit-guide)"


def _get_json(url: str) -> dict:
    # The feed refuses Python's default User-Agent with a 403.
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cached(url: str, ttl: int) -> tuple[dict, str]:
    """Returns (payload, "hit" or "miss") from the in-instance cache."""
    now = time.monotonic()
    entry = _cache.get(url)
    if entry and now - entry[0] < ttl:
        return entry[1], "hit"
    payload = _get_json(url)
    _cache[url] = (now, payload)
    return payload, "miss"


def _bike_types(status: dict) -> dict:
    """Mechanical and electric bikes at a station."""
    types = status.get("num_bikes_available_types") or {}
    return {"mechanical": types.get("mechanical", 0), "ebike": types.get("ebike", 0)}


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n <= 1 else many}"


def _recommend(stations: list) -> str:
    take = next((s for s in stations if (s["bikes"] or 0) > 0), None)
    drop = max(stations, key=lambda s: s["docks"] or 0)
    parts = []
    if take:
        parts.append(f"Pour prendre un vélo : {take['name']}, à {take['walkMinutes']} min à pied")
    if drop and (drop["docks"] or 0) > 0:
        left = drop["docks"]
        note = _plural(left, "place", "places") + (", dépêchez-vous" if left <= 2 else "")
        parts.append(f"pour le rendre : {drop['name']} ({note})")
    return " ; ".join(parts) + "." if parts else "Aucun vélo disponible autour du Summit pour le moment."


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _guide() -> dict:
    global _CALLS
    _CALLS += 1
    started = time.monotonic()
    lat = float(_env("SUMMIT_LAT", "48.86183"))
    lon = float(_env("SUMMIT_LON", "2.33431"))

    t0 = time.monotonic()
    info_payload, info_cache = _cached(INFO_URL, INFO_TTL)
    status_payload, status_cache = _cached(STATUS_URL, STATUS_TTL)
    info = info_payload["data"]["stations"]
    status = {s["station_id"]: s for s in status_payload["data"]["stations"]}
    fetch_ms = round((time.monotonic() - t0) * 1000)

    nearest = sorted(info, key=lambda s: _distance_m(lat, lon, s["lat"], s["lon"]))[:3]
    stations = []
    for s in nearest:
        st = status.get(s["station_id"], {})
        distance = round(_distance_m(lat, lon, s["lat"], s["lon"]))
        stations.append({
            "name": s["name"],
            "distanceM": distance,
            "walkMinutes": max(1, round(distance / WALK_M_PER_MIN)),
            "bikes": st.get("num_bikes_available"),
            "bikeTypes": _bike_types(st),
            "docks": st.get("num_docks_available"),
        })

    uptime = time.monotonic() - _STARTED_AT
    return {
        "release": _env("SUMMIT_RELEASE", "dev"),
        "place": _env("SUMMIT_NAME", "Carrousel du Louvre"),
        "recommendation": _recommend(stations),
        "ebikesNearby": sum(st["bikeTypes"]["ebike"] for st in stations),
        "stations": stations,
        "source": "Velib' Metropole open data (GBFS)",
        "cache": {"stationInformation": info_cache, "stationStatus": status_cache},
        "fetchMs": fetch_ms,
        "durationMs": round((time.monotonic() - started) * 1000),
        "instance": {
            "hostname": socket.gethostname(),
            "uptimeSeconds": round(uptime, 1),
            "coldStart": uptime < 5,
            "callsServed": _CALLS,
        },
    }


# ---- The page ---------------------------------------------------------------
#
# Station cards are rendered here; the strip at the bottom is drawn by the
# browser, which reloads the data every 2 seconds and keeps the last calls:
# bar height = response time, colour = release that answered, red = error.
# The page embeds its data (<script id="data">), so scripts/watch.sh and
# scripts/probe.sh read it even when ?format=json is not available.

BIKE = ('<svg viewBox="0 0 24 16" aria-hidden="true"><circle cx="5" cy="11" r="4"/><circle cx="19" cy="11" r="4"/>'
        '<path d="M5 11 9 4h7l3 7M9 4 12 11h-7M14 2h3"/></svg>')
MAX_ICONS = 20


def _card(st: dict) -> str:
    bikes, docks = st.get("bikes") or 0, st.get("docks") or 0
    types = st.get("bikeTypes")
    ebike = types.get("ebike", 0) if types else 0
    icons = (["mech"] * (bikes - ebike) + ["elec"] * ebike)[:MAX_ICONS]
    row = "".join(f'<i class="{c}">{BIKE}</i>' for c in icons)
    if bikes > len(icons):
        row += f"<em>+{bikes - len(icons)}</em>"
    walk = f" · {st['walkMinutes']} min à pied" if st.get("walkMinutes") else ""
    split = (f'<p class="split"><span class="mech">{_plural(bikes - ebike, "mécanique", "mécaniques")}</span>'
             f'<span class="elec">{_plural(ebike, "électrique", "électriques")}</span></p>' if types else "")
    return (f'<article><h2>{st["name"]}</h2><p class="dim">{st["distanceM"]} m{walk}</p>'
            f'<p class="count"><b>{bikes}</b> {"vélo" if bikes <= 1 else "vélos"}</p>'
            f'<p class="bikes">{row or "<span class=dim>aucun vélo</span>"}</p>{split}'
            f'<p class="dim"><b>{docks}</b> {"place libre" if docks <= 1 else "places libres"} pour rendre</p></article>')


def _page(data: dict) -> str:
    reco = data.get("recommendation")
    return (PAGE.replace("{{RELEASE}}", data["release"])
            .replace("{{RECO}}", f'<p class="reco">{reco}</p>' if reco else "")
            .replace("{{CARDS}}", "".join(_card(s) for s in data["stations"]))
            .replace("{{DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))


PAGE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vélib' au Summit · {{RELEASE}}</title><link rel="icon" href="data:,">
<style>
:root { --v1: #4F7CFF; --v2: #1FA35B; --v3: #E8590C; --ink: #0D1B2A; --dim: #5B6B7F; --mech: #2F6FE4; --elec: #1FA35B; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink); background: #EEF2FA; }
header { background: #000E9C; color: #fff; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
header h1 { margin: 0; font-size: 1.5rem; } header p { margin: 2px 0 0; opacity: .85; font-size: .9rem; }
#badge { background: var(--rel, #5B6B7F); font-weight: 800; font-size: 1.5rem; padding: 6px 14px; border-radius: 10px; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 18px 24px; }
.reco { background: #fff; border-left: 6px solid var(--elec); border-radius: 10px; padding: 12px 16px; font-weight: 600; margin: 0 0 16px; }
#cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
article { background: #fff; border-radius: 14px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
article p { margin: 6px 0; } h2 { margin: 0; font-size: 1.05rem; }
.dim { color: var(--dim); font-size: .9rem; } .dim b { color: var(--ink); }
.count { color: var(--dim); } .count b { font-size: 2.6rem; color: var(--ink); margin-right: 4px; }
.bikes { display: flex; flex-wrap: wrap; gap: 3px; min-height: 20px; }
.bikes svg { width: 24px; height: 16px; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; stroke: var(--mech); }
.bikes .elec svg { stroke: var(--elec); } .bikes em { font-style: normal; font-weight: 700; color: var(--dim); }
.split span { font-size: .78rem; font-weight: 700; color: #fff; padding: 2px 8px; border-radius: 10px; margin-right: 6px; }
.split .mech { background: var(--mech); } .split .elec { background: var(--elec); }
.speed { background: #fff; border-radius: 14px; padding: 14px 16px; margin-top: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.speed p { margin: 0; } #now { font-size: 1.1rem; } #now b { font-size: 1.5rem; }
#strip { display: flex; gap: 3px; align-items: flex-end; height: 56px; margin: 10px 0 4px; }
#strip i { flex: 0 0 calc((100% - 117px) / 40); min-height: 4px; border-radius: 3px 3px 0 0; }
</style></head>
<body>
<header><span id="badge">{{RELEASE}}</span><div><h1>Vélib' autour du Summit</h1>
<p>Carrousel du Louvre · en direct · une fonction OVHcloud Serverless</p></div></header>
<div class="wrap">
<div id="reco">{{RECO}}</div>
<section id="cards">{{CARDS}}</section>
<section class="speed">
<p id="now"></p>
<div id="strip"></div>
<p class="dim">Un appel toutes les 2 s : hauteur = temps de réponse, couleur = release qui a répondu, rouge = erreur.</p>
</section></div>
<script type="application/json" id="data">{{DATA}}</script>
<script>
(function () {
  var calls = [], $ = function (id) { return document.getElementById(id); };
  function colour(rel) { return getComputedStyle(document.documentElement).getPropertyValue('--' + rel) || '#5B6B7F'; }
  function show(d, ms) {
    $('badge').textContent = d.release; $('badge').style.setProperty('--rel', colour(d.release));
    var cache = !d.cache ? 'pas de cache' : d.cache.stationStatus === 'hit' ? 'données en cache' : 'cache rafraîchi';
    $('now').innerHTML = (ms == null ? '' : 'Réponse en <b>' + Math.round(ms) + ' ms</b> · ') +
      'attente de Vélib\\' : <b>' + d.fetchMs + ' ms</b> · ' + cache;
  }
  function draw() {
    var max = Math.max.apply(null, calls.map(function (c) { return c.ms; }).concat([300]));
    $('strip').innerHTML = calls.map(function (c) {
      return '<i title="' + (c.rel || 'erreur') + ' ' + Math.round(c.ms) + ' ms" style="height:' +
        Math.max(6, 100 * c.ms / max) + '%;background:' + (c.rel ? colour(c.rel) : '#C92A2A') + '"></i>';
    }).join('');
  }
  function tick() {
    var t0 = performance.now();
    fetch(location.pathname + location.search, { cache: 'no-store' }).then(function (r) {
      return r.text().then(function (txt) {
        var ms = performance.now() - t0, doc = new DOMParser().parseFromString(txt, 'text/html'), el = doc.getElementById('data');
        if (!r.ok || !el) { calls.push({ ms: ms }); return; }
        var d = JSON.parse(el.textContent);
        calls.push({ ms: ms, rel: d.release });
        $('cards').innerHTML = doc.getElementById('cards').innerHTML;
        $('reco').innerHTML = doc.getElementById('reco').innerHTML;
        show(d, ms);
      });
    }).catch(function () { calls.push({ ms: performance.now() - t0 }); })
      .then(function () { if (calls.length > 40) calls.shift(); draw(); setTimeout(tick, 2000); });
  }
  show(JSON.parse($('data').textContent), null);
  setTimeout(tick, 2000);
})();
</script>
</body></html>
"""


def main():
    data = _guide()
    try:
        from flask import Response, request  # the platform's Python runtime runs handlers inside Flask
    except ImportError:
        return data
    try:
        if request.args.get("format") == "json":
            return data
    except RuntimeError:  # no request context
        pass
    return Response(_page(data), status=200, mimetype="text/html")


if __name__ == "__main__":
    print(json.dumps(_guide(), ensure_ascii=False, indent=2))
