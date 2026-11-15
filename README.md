# Seasons Ahead

A web app that helps the people who plan a farm's production choose crop rotations that protect the soil and hold
up in a changing climate. Built for the NASA Space Apps Challenge 2026, challenge *Field Shift: Adapting Farms with
NASA Data*.

The producer finds their field on the map and answers a short interview about each plot: soil analysis, priorities
and constraints. Seasons Ahead combines those answers with NASA data on rainfall, climate, soil moisture, vegetation
and terrain, plus national soil maps. For each plot it compares the current rotation with at least two alternatives
and explains the reasons, the evidence, the benefits, what is still unknown and the risks of each one. The final
decision stays with the producer.

The app works in English and Spanish, for fields in Uruguay, the United States and the rest of the world (with less
local data outside Uruguay and the U.S.).

## What it shows

- **Plan**: what to grow on each plot, season by season, on a map or over the real terrain in 3D, and how that plan
  would have done in every season since 2000.
- **Compare**: the current rotation next to the alternatives, with soil loss (USLE) against the soil's tolerance,
  drought, frost and heat risk for each crop, and expected income.
- **Data**: the climate, the soil and the satellite record behind every number, with a "what if the climate changes"
  scenario.
- **Report for the agronomist**: a printable summary of the farm and the plan.
- **Assistant**: an optional chat that answers questions about the results. Without it, the app runs the full
  analysis with a guided interview.

Examples to try without loading a field: `/app?demo=1` (Durazno, Uruguay) and `/app?demo=us` (Madison County, Iowa).

## Data

| Data | Source |
|---|---|
| Daily climate since 1991 | NASA POWER |
| Daily rainfall since 2000 | NASA GPM IMERG, via Giovanni |
| Root-zone soil moisture | NASA SMAP L4 (`SPL4SMGP.008`), via AppEEARS and Google Earth Engine; GLDAS 2.1 |
| Vegetation and bare soil (NDVI) | NASA MODIS MOD13Q1 v061 (ORNL DAAC and Google Earth Engine); HLS Landsat and Sentinel-2 (NASA CMR, GIBS) |
| Terrain, 30 m | NASA SRTM, via AWS Terrain Tiles |
| Land surface temperature, 70 m | NASA ECOSTRESS (example field in Uruguay) |
| Climate projections 2026-2035 | NASA NEX-GDDP-CMIP6 (30 models), via Google Earth Engine |
| Soils, land registry, rainfall erosivity (Uruguay) | MGAP-DGRN |
| Soils (United States) | USDA-NRCS SSURGO |
| Crop history (United States) | USDA-NASS Cropland Data Layer |
| Soils (rest of the world) | ISRIC SoilGrids |
| Crop water use | FAO-56 |
| Background imagery | NASA GIBS; Esri World Imagery |
| Place names and roads | GeoNames; OpenStreetMap |

The models do not invent numbers: every figure comes from a calculation in the backend, and the screen says where it
came from and how sure it is.

## Run it locally

Requirements: Python 3.12+ and Node 20+.

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Linux/Mac: .venv/bin/pip
.venv/Scripts/python -m uvicorn fieldshift.api:app --port 8000

# frontend, in another terminal
cd frontend
npm install
npm run dev                                         # http://localhost:5173 (home) and /app (the tool)
```

Or everything at once, built and served by the backend on one port: `bash iniciar.sh`, then open
http://localhost:8000.

## Configuration

Everything is optional: without these variables the app still works, with less data or in guided mode.

| Variable | What it enables |
|---|---|
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | The chat assistant (Google Gemini). `FIELDSHIFT_MODELO` changes the model; `FIELDSHIFT_IA=0` forces guided mode. |
| `EARTHDATA_USER`, `EARTHDATA_PASS` | SMAP soil moisture through AppEEARS (a NASA Earthdata Login account). |
| `EARTHDATA_TOKEN` | GPM IMERG rainfall through Giovanni. |
| `EE_CUENTA_SERVICIO` | A Google Earth Engine service account (JSON) for the MODIS history, HLS, GLDAS and CMIP6. The Earth Engine project ID is set in `backend/fieldshift/fuentes/modis_historia.py`. |
| `FIELDSHIFT_CLAVE` | Optional password for the whole site. |
| `FIELDSHIFT_CACHE` | Folder for the data cache (default: `backend/cache`). |

For local use, the credentials can also go in a `.secretos/` folder at the project root (`earthdata.env`,
`earthdata_token.txt`, `ee_cuenta_servicio.json`). It is ignored by git.

## Deploy

The project is ready for Vercel: `vercel.json` builds the frontend and `main.py` serves the FastAPI backend as a
Python function. Set the variables above in the project settings.

## Project structure

```
backend/
  fieldshift/
    api.py          HTTP API (FastAPI)
    agente/         interview, guided mode and chat assistant
    analisis/       climate, water balance, erosion, rotations and the plan
    fuentes/        clients for NASA, USDA, MGAP and other data sources
    datos/          bundled reference data (soils, places, grids)
  scripts/          scripts that rebuild the bundled data
  tests/            tests (pytest, no internet needed)
frontend/
  src/              React app (map, plan, compare, data, 3D terrain, chat)
  public/ejemplos/  example fields
ejemplos/           sample files to upload (soil analysis, field history, weather station, field outline)
```

Code comments and identifiers are in Spanish.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q
cd frontend && npm run test:i18n && npm run typecheck
```

## Use of Super Intelligence (SI)

Most of the code was written with the help of SI coding assistants (Claude Code by Anthropic and Gemini by Google),
under the team's direction and review. The optional chat assistant in the app runs on the Google Gemini API, and
some interface translations were drafted with SI. The farmer illustration in the presentation was drawn in code with
an SI assistant and carries a visible "SI-generated" mark. No NASA logos or mission identifiers were generated.

## Team

Gaspar Birenbaum and Patrick Kaitazoff.
