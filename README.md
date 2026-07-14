# Empire State Building — Interactive 3D Recreation

A first-person, real-data 3D recreation of the Empire State Building and Midtown
Manhattan, built with [three.js](https://threejs.org/) and WebGL. Walk Fifth
Avenue, step into the Art Deco lobby, ride the express elevator to the
86th-floor observatory, and take in Manhattan in every direction — from the
Hudson River to Central Park.

## Running it

No build step. Serve the folder with any static file server and open it:

```bash
python3 -m http.server 8000
# then visit http://localhost:8000
```

(Or push to GitHub Pages — it's all static files.)

> Opening `index.html` directly from disk won't work because ES modules and
> the data file require `http://` URLs.

## Controls

| Input | Action |
|---|---|
| Click | capture the mouse |
| `W A S D` / arrows | walk |
| Mouse | look |
| `Shift` | run |
| `E` | call / ride the elevator |
| `Esc` | menu |

Or press **Cinematic Tour** for a scripted flight: street → lobby → elevator →
86th-floor deck → skyline finale.

## What's real

The surrounding city is generated from **OpenStreetMap** data, baked into
`data/city_data.js` (~2.4 MB):

- **30,567 building footprints** in the core area (Houston St → 89th St,
  Hudson → East River) with real heights where OSM has them
  (`height` / `building:levels` tags) — Chrysler, One Vanderbilt, 432 Park,
  Central Park Tower, Hudson Yards, etc. all stand at their true locations
  and heights.
- **2,290 tall buildings** in an extended ring — the downtown skyline
  including One World Trade Center, plus uptown, NJ waterfront and
  Brooklyn/Queens.
- **Real shorelines** (Hudson River, East River, the harbor, Roosevelt
  Island) polygonized from OSM coastline data — the Hudson piers are real.
- **Real parks** (Central Park with its lakes and reservoir, Bryant Park,
  Madison Square Park…) and the **real street grid** (7,417 street segments).
- The ESB's own footprint, position and the 29° Manhattan grid rotation come
  from its actual OSM footprint (way 34633854); the model's coordinate origin
  is the building's centroid.

The building itself — setback massing, limestone facade, the three-story
lobby with the aluminum relief mural, the express elevator, and the
86th-floor observatory with its curved safety fence — is hand-modeled to the
real proportions (129 m × 59 m site, deck at 320 m, antenna tip at 443 m).
All textures (marble, terrazzo, elevator sunburst doors, ceiling murals,
flags…) are generated procedurally on `<canvas>` — there are no image assets.

## Rebuilding the city data

```bash
tools/fetch_osm.sh /tmp/osm_raw        # fetch raw data from Overpass API
pip install shapely
python3 tools/bake_city.py /tmp/osm_raw   # writes data/city_data.js
```

## Credits

- Building & map data © [OpenStreetMap](https://www.openstreetmap.org/copyright)
  contributors, available under the [ODbL](https://opendatacommons.org/licenses/odbl/).
- Rendering: [three.js](https://threejs.org/) (r180, vendored in `lib/`, MIT).
