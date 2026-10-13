"""Summit guide: Velib' bikes around the Carrousel du Louvre, live.

A function for the OVHcloud Serverless alpha demo. The handler is `main`, it
takes no argument and returns a JSON-serialisable dict (starter contract of
function-python3.12-hello). Standard library only.

Data: Velib' Metropole open data (GBFS feeds, no key needed).

Environment:
  SUMMIT_RELEASE   the release that deployed this revision (set by the deploy
                   workflow, default "dev")
  SUMMIT_NAME      place name (default "Carrousel du Louvre")
  SUMMIT_LAT/LON   place coordinates (default 48.8622, 2.3330)
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
    """GBFS gives a list of single-key dicts: [{"mechanical": 20}, {"ebike": 1}]."""
    types = {"mechanical": 0, "ebike": 0}
    for item in status.get("num_bikes_available_types") or []:
        for kind, count in item.items():
            types[kind] = types.get(kind, 0) + count
    return types


def _recommend(stations: list) -> str:
    take = next((s for s in stations if (s["bikes"] or 0) > 0), None)
    drop = max(stations, key=lambda s: s["docks"] or 0)
    parts = []
    if take:
        parts.append(f"Pour prendre un vélo : {take['name']}, à {take['walkMinutes']} min à pied")
    if drop and (drop["docks"] or 0) > 0:
        parts.append(f"pour le rendre : {drop['name']} ({drop['docks']} places)")
    return " ; ".join(parts) + "." if parts else "Aucun vélo disponible autour du Summit pour le moment."


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def main():
    global _CALLS
    _CALLS += 1
    started = time.monotonic()
    lat = float(_env("SUMMIT_LAT", "48.8622"))
    lon = float(_env("SUMMIT_LON", "2.3330"))

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


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
