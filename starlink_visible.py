#!/usr/bin/env python3
#
# Leo Green <leo@nurgle.net>
#
# List visible Starlink sats over a location and time window.
# Examples:
#   # Right now, for 15 min from the dish location (API v39), min elev 10°
#   # (requires: grpcurl installed, app toggle ON)
#   python starlink_visible.py --now --duration-min 15 --from-dish --tle-file starlink_2025-09-14.tle --min-el 10
#
#   # Right now at a fixed site
#   python starlink_visible.py --now --lat 32.9880 --lon -96.5925 --alt 145 --tle-file starlink_2025-09-14.tle
#
#   # Arbitrary window
#   python starlink_visible.py --start 2025-09-14T18:30:00Z --end 2025-09-14T18:45:00Z \
#       --lat 32.7837 --lon -96.7838 --alt 145 --tle-file starlink_2025-09-14.tle --min-el 10
# 
#   As of publishing, you can get latest TLE's via:
#   wget -O starlink_latest.tle https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle


from skyfield.api import Loader, wgs84
from skyfield.sgp4lib import EarthSatellite
from datetime import datetime, timezone, timedelta
import argparse, sys, os, json, subprocess

TS = Loader('~/.skyfield-data').timescale()

def load_tles(path):
    sats = []
    with open(path, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    i = 0
    while i + 2 < len(lines):
        name, l1, l2 = lines[i], lines[i+1], lines[i+2]
        if l1.startswith('1 ') and l2.startswith('2 '):
            sats.append(EarthSatellite(l1, l2, name, TS))
            i += 3
        else:
            i += 1
    return sats

def frange(t0, t1, step_s=30):
    t = t0
    while t <= t1:
        yield t
        t += timedelta(seconds=step_s)

def parse_iso_z(s):
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    return datetime.fromisoformat(s).astimezone(timezone.utc)

def fetch_location_from_dish():
    """grpcurl -> SpaceX.API.Device.Device/Handle {get_location:{}}; supports API v39 getLocation.lla"""
    cmd = ('grpcurl -plaintext -d \'{"get_location":{}}\' '
           '192.168.100.1:9200 SpaceX.API.Device.Device/Handle')
    raw = subprocess.check_output(cmd, shell=True, timeout=8)
    data = json.loads(raw.decode('utf-8', errors='ignore'))
    # v39:
    lla = data.get("getLocation", {}).get("lla")
    if isinstance(lla, dict) and all(k in lla for k in ("lat","lon","alt")):
        return float(lla["lat"]), float(lla["lon"]), float(lla["alt"])
    # fallback: crawl
    def search(o):
        if isinstance(o, dict):
            if ("latitude" in o and "longitude" in o) or ("lat" in o and "lon" in o):
                return o
            for v in o.values():
                r = search(v)
                if r: return r
        elif isinstance(o, list):
            for v in o:
                r = search(v)
                if r: return r
        return None
    got = search(data)
    if not got:
        raise RuntimeError("Dish GetLocation returned no lat/lon (is the app toggle ON?)")
    lat = got.get("latitude", got.get("lat"))
    lon = got.get("longitude", got.get("lon"))
    alt = got.get("altitudeM", got.get("alt", 0.0))
    return float(lat), float(lon), float(alt)

def visible_list(tle_file, lat, lon, alt, start, end, min_el, step_s=30):
    sats = load_tles(tle_file)
    if not sats:
        print("No TLEs parsed from file.", file=sys.stderr)
        return []
    site = wgs84.latlon(lat, lon, elevation_m=alt)
    visible = {}
    for dt in frange(start, end, step_s):
        t = TS.from_datetime(dt)
        for sat in sats:
            topoc = (sat - site).at(t)
            alt_deg, az_deg, _ = topoc.altaz()
            if alt_deg.degrees >= min_el:
                visible.setdefault(sat, []).append((dt, alt_deg.degrees, az_deg.degrees % 360.0))
    rows = []
    for sat, samples in visible.items():
        samples.sort(key=lambda x: x[0])
        chunk, prev = [], None
        for s in samples:
            if prev and (s[0] - prev[0]).total_seconds() > 180:
                if chunk:
                    rows.append((sat, chunk))
                chunk = []
            chunk.append(s); prev = s
        if chunk:
            rows.append((sat, chunk))
    rows.sort(key=lambda r: max(el for _, el, _ in r[1]), reverse=True)
    return rows

def main():
    ap = argparse.ArgumentParser(description="List visible Starlink sats (includes --now mode).")
    ap.add_argument("--tle-file", required=True, help="Starlink TLE file (same UTC day as now/window)")
    ap.add_argument("--now", action="store_true", help="Use current UTC time")
    ap.add_argument("--duration-min", type=int, default=15, help="Window length (minutes) for --now")
    ap.add_argument("--start", help="Start time ISO/Z (ignored if --now)")
    ap.add_argument("--end", help="End time ISO/Z (ignored if --now)")
    ap.add_argument("--lat", type=float, help="Latitude (deg, N+)")
    ap.add_argument("--lon", type=float, help="Longitude (deg, E+)")
    ap.add_argument("--alt", type=float, default=0.0, help="Altitude (m)")
    ap.add_argument("--from-dish", action="store_true", help="Fetch lat/lon/alt via grpcurl get_location")
    ap.add_argument("--min-el", type=float, default=10.0, help="Minimum elevation (deg)")
    ap.add_argument("--step-s", type=int, default=30, help="Sampling step seconds")
    args = ap.parse_args()

    # Time window
    if args.now:
        mid = datetime.now(timezone.utc)
        half = timedelta(minutes=max(1, args.duration_min)) / 2
        start = mid - half
        end = mid + half
    else:
        if not (args.start and args.end):
            ap.error("Provide --now OR both --start and --end")
        start = parse_iso_z(args.start)
        end = parse_iso_z(args.end)

    # Location
    if args.from_dish:
        try:
            lat, lon, alt = fetch_location_from_dish()
            print(f"[INFO] Dish location: {lat:.6f}, {lon:.6f}, {alt:.1f} m")
        except Exception as e:
            print(f"[WARN] from-dish failed: {e}", file=sys.stderr)
            if args.lat is None or args.lon is None:
                ap.error("Need --lat/--lon if --from-dish fails")
            lat, lon, alt = args.lat, args.lon, args.alt
    else:
        if args.lat is None or args.lon is None:
            ap.error("Need --lat/--lon or use --from-dish")
        lat, lon, alt = args.lat, args.lon, args.alt

    # Compute
    rows = visible_list(args.tle_file, lat, lon, alt, start, end, args.min_el, args.step_s)
    if not rows:
        print("No Starlink above min elevation in that window.", file=sys.stderr)
        return

    # Print
    for sat, chunk in rows:
        t0, t1 = chunk[0][0], chunk[-1][0]
        max_el, t_peak, az_at_peak = -1.0, None, None
        for dt, el, az in chunk:
            if el > max_el:
                max_el, t_peak, az_at_peak = el, dt, az
        print(f"{sat.model.satnum:>6}  {sat.name:22s}  "
              f"{t0:%Y-%m-%d %H:%M:%SZ} → {t1:%Y-%m-%d %H:%M:%SZ}  "
              f"peak {max_el:5.1f}° at {t_peak:%H:%M:%S}  az≈{az_at_peak:5.1f}°")

if __name__ == "__main__":
    main()

