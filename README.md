# starlink-track
Quick scipt that'll tell you which starlink satellites are visible from your location.

## List visible Starlink sats over a location and time window.
## Examples:
- Right now, for 15 min from the dish location (API v39), min elev 10°
(requires: grpcurl installed, app toggle ON)

      python starlink_visible.py --now --duration-min 15 --from-dish --tle-file starlink_latest.tle --min-el 10

- Right now at a fixed site

      python starlink_visible.py --now --lat 32.9880 --lon -96.5925 --alt 145 --tle-file starlink_latest.tle

- Arbitrary window

      python starlink_visible.py --start 2025-09-14T18:30:00Z --end 2025-09-14T18:45:00Z \
      --lat 32.7837 --lon -96.7838 --alt 145 --tle-file starlink_latest.tle --min-el 10

As of publishing, you can get latest TLE's via:
`wget -O starlink_latest.tle https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle`
