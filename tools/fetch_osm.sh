#!/usr/bin/env bash
# Fetch raw OpenStreetMap data (via Overpass API) used to bake data/city_data.js.
# Usage: tools/fetch_osm.sh <raw_dir>   then: python3 tools/bake_city.py <raw_dir>
set -euo pipefail
RAW="${1:?usage: fetch_osm.sh <raw_dir>}"
mkdir -p "$RAW"
API="https://overpass-api.de/api/interpreter"
UA="esb-3d-project/1.0"

fetch() { # $1 out file, $2 query
  local out="$1" q="$2" i
  for i in 1 2 3 4 5; do
    if curl -sS --max-time 300 -H "User-Agent: $UA" "$API" \
        --data-urlencode "data=$q" -o "$RAW/$out" \
        && python3 -c "import json,sys;json.load(open('$RAW/$out'))" 2>/dev/null; then
      echo "OK $out"; return 0
    fi
    echo "retry $i for $out"; sleep $((i*15))
  done
  echo "FAILED $out"; return 1
}

# All buildings, core midtown bbox (split into two tiles for server load)
fetch buildings_south.json '[out:json][timeout:240][maxsize:536870912];(way["building"](40.725,-74.020,40.758,-73.950);relation["building"](40.725,-74.020,40.758,-73.950););out geom;'
fetch buildings_north.json '[out:json][timeout:240][maxsize:536870912];(way["building"](40.758,-74.020,40.790,-73.950);relation["building"](40.758,-74.020,40.790,-73.950););out geom;'
# Tall buildings in the extended ring (downtown incl. One WTC, uptown, NJ, Brooklyn)
fetch buildings_far.json '[out:json][timeout:240][maxsize:536870912];(way["building"](if:number(t["height"])>=35||number(t["building:levels"])>=11)(40.66,-74.05,40.845,-73.885);relation["building"](if:number(t["height"])>=35||number(t["building:levels"])>=11)(40.66,-74.05,40.845,-73.885););out geom;'
# Coastline (Hudson River / East River shores)
fetch coastline.json '[out:json][timeout:240];way["natural"="coastline"](40.66,-74.07,40.85,-73.88);out geom;'
# Inland water (Central Park reservoir + lakes)
fetch water.json '[out:json][timeout:240][maxsize:536870912];(way["natural"="water"](40.68,-74.05,40.83,-73.90);relation["natural"="water"](40.68,-74.05,40.83,-73.90);way["waterway"="riverbank"](40.68,-74.05,40.83,-73.90););out geom(40.68,-74.05,40.83,-73.90);'
# Parks and green space
fetch parks.json '[out:json][timeout:240][maxsize:536870912];(way["leisure"~"^(park|garden|pitch|playground)$"](40.70,-74.05,40.83,-73.90);relation["leisure"~"^(park|garden)$"](40.70,-74.05,40.83,-73.90);way["landuse"~"^(grass|recreation_ground)$"](40.70,-74.05,40.83,-73.90););out geom(40.70,-74.05,40.83,-73.90);'
# Street grid
fetch roads.json '[out:json][timeout:240][maxsize:536870912];way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified)$"](40.715,-74.030,40.800,-73.940);out geom;'
