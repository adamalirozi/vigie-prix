<div align="center">

# Vigie Prix

**Des prévisions de prix des céréales à 1, 2 et 3 mois, et le suivi du MEB, pour agir avant la hausse.**
*1–3 month cereal price projections and MEB alerts for Chad — demonstration (MVP).*

[![CI](https://github.com/adamalirozi/vigie-prix/actions/workflows/ci.yml/badge.svg)](https://github.com/adamalirozi/vigie-prix/actions/workflows/ci.yml)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://YOUR-APP.streamlit.app)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-demonstration-orange)

[**Démo en ligne**](https://vigie-prix-nzmskazxva2ysia9wlmneh.streamlit.app) · [Données](docs/DATA.md) · [Déploiement](docs/DEPLOYMENT.md) · [Déroulé de démo](docs/DEMO_SCRIPT.md) · [Contribuer](CONTRIBUTING.md) · [README en français](README.fr.md)

</div>

<!-- Ajouter 2-3 captures dans docs/img/ puis décommenter :
![Vue Provinces](docs/img/provinces.png)
![Mode relecture](docs/img/relecture.png)
-->

Streamlit demo of the project *« Agir avant la hausse, pas après »*: 1-3 month cereal price projections for
Al Aswak and MEB monitoring, on **public WFP data** (retail prices in **FCFA/kg**).

> **Status: demonstration.** Thresholds, alerts and the MEB composition are *not* validated by SISAAP; projections are a
> simple seasonal reference ("level 1"); external factors (fuel, rain, conflict) are not connected. The app says so in the header,
> in the methodology panel, in every export and in the Word draft.

## Run

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Development: `pip install -r requirements-dev.txt`, then `python -m pytest` (126 tests, about 2 minutes) and `ruff check .`

**Offline demo:** switch on *"Carte sans fond (hors ligne)"* — the only internet dependency is the map background.

## What the demo shows (and the proposal promise it answers)

| Proposal | In the app |
|---|---|
| Forecasts at **1, 2 and 3 months**, for millet, sorghum, maize, imported rice | Product selector + **M+1 / M+2 / M+3** button, applied to map, table, KPIs, alerts, MEB |
| **Per market** forecast, "most fragile markets" | Market table per province + national "marchés les plus exposés", with data reliability shown |
| Interactive **dashboard (map)** | *Provinces* and *Départements* views, click-to-select, market layer, price sources shown |
| **Al Aswak** preparation module | *Al Aswak* view: auto-written French draft + Word export with charts, marked "BROUILLON À VALIDER" |
| **MEB alerts**, threshold set by SISAAP | *MEB* view (cereal component, editable `data/meb_composition.csv`), adjustable threshold, MEB alerts |
| **Validation** by SISAAP analysts, suspension, audit trail | *Alertes*: roles (Analyste / Lecteur), validate / suspend / reject, comment, journal, message for the Cluster (nothing is sent) |
| Each alert shows **factors and a confidence level** | Confidence (3 levels, rules documented) + factors list; unreliable markets flagged, not hidden |
| Thresholds "non validés" in the demo | Banner + labels on every threshold |
| "Simple method first" benchmark | *Fiabilité & données*: out-of-sample back-test vs "price unchanged", hit rate on rises, bias, 3 method levels |
| Phase 1 **data audit**, 10-20 pilot markets | *Fiabilité & données*: coverage map, cleaning findings, **proposed pilot markets** |
| **"Agir avant la hausse"** curve | **Replay mode**: redo the forecast as of a past date with only the data then available, compare to what happened |

### Suggested 5-minute path
1. *Provinces*: show today's situation, switch M+1/M+2/M+3, click a province.
2. *Épisode d'illustration* → "Soudure 2024 · mil, Hadjer-Lamis": green line = realised prices after the forecast.
3. *Alertes* (profile *Analyste SISAAP*): see which alerts were confirmed, validate one, read the Cluster message.
4. *MEB*, then *Al Aswak* → "Préparer le fichier Word".
5. *Fiabilité & données*: be upfront about what level 1 can and cannot do.

## Data and what was found in it

- `data/wfp_food_prices_tcd.csv`, `data/wfp_markets_tcd.csv`: WFP exports (HDX). Data ends **June 2026**, so the app anchors
  on the last observation and shows a "n months behind" warning; the replay mode is how it demonstrates "act before the rise".
- **Cleaning** (reported in the app): isolated readings far from a market's own rolling median are dropped, and months where
  *every* market jumps together then reverses are dropped as probable collection artefacts. Found for millet: Sep 2024,
  Jan 2025, May 2026 (other products: Sep 2024, Jan 2025, and a few more) — to confirm with SISAAP. See `config.py`
  (`OUTLIER_*`, `SYNC_*`, `MASK_SYNC_ANOMALIES`).
- Markets are assigned to provinces by WFP's administrative label (the boundary file is approximate near borders: e.g. Moundou).
- Tibesti has no price since Aug 2024 and is shown grey; maize has no recent price in Borkou, Ennedi, Wadi Fira.
- Markets without coordinates (e.g. Oum Hadjer) are not used.

## Honest performance (public data, out-of-sample, see the app)

The seasonal reference is **about as accurate as "price unchanged"** at 3 months, flags roughly half of the rises of 10 % or
more for millet/sorghum/maize, and almost none for imported rice. It is the benchmark that levels 2 and 3 (market links,
fuel, rain, conflict, ML on SIMPA series) must beat — not the product itself. The three demo episodes were chosen because
the method alerted; the *Fiabilité* page shows the averages, including the misses. Replay confirmations of "seuil de prix"
alerts are lenient (the price stays above the threshold); "hausse rapide" confirmations are the meaningful ones.

## Structure

```
app.py                  navigation, filters, callbacks
config.py               constants: products, thresholds, scenarios, episodes, paths, palette
data/                   WFP CSVs, geo/*.geojson, meb_composition.csv ; state/ (validations, created at run time)
services/
  geo.py                boundaries, simplification, market -> province/department
  prices.py             source, cleaning, model (as_of replay, horizon, reliability, market forecasts)
  evaluation.py         back-test, verdict text, pilot markets
  meb.py                cereal component of the MEB
  alerts.py             rules, confidence, factors, validation store + audit log, Cluster message
  bulletin.py           Al Aswak draft (text + Word with matplotlib charts)
  cached.py             Streamlit caches (small hashable keys)  ·  export.py  CSV / Excel
ui/                     charts.py, components.py, formatting.py, context.py, styles.css, views/*.py
tests/                  126 tests incl. no-look-ahead checks, back-test, alerts workflow, episodes, Word, end-to-end app
```

## Before a real pilot

- Replace `meb_composition.csv` with the Cluster-validated basket and add the non-cereal items.
- Replace the data source: implement `PriceSource` (`services/prices.py`) for SIMPA/DPSA series; re-run the back-test.
- Have SISAAP set the thresholds and confirm the scenario drifts (`SCENARIOS`) and the cleaned months.
- Add real authentication (the *Analyste/Lecteur* switch is a demo device) and a persistent audit store.
- Level 2 inputs (CHIRPS rain, fuel prices, events, cross-border prices) and a real Cadre Harmonisé layer.
- Set `ORG_NAME` in `config.py` (a placeholder is shown in the footer).

## Data sources and licences

Prices: WFP Price Database via HDX (CC BY-IGO). Boundaries: geoBoundaries (CC BY 4.0 for the open release; check the
Chad file's metadata). Full table, attribution text and data dictionary: [docs/DATA.md](docs/DATA.md).

## Licence

Code: [MIT](LICENSE). The data in `data/` keeps its producers' licences. See also [SECURITY.md](SECURITY.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Citation

See [CITATION.cff](CITATION.cff) (GitHub shows a "Cite this repository" button).

## Contact

adamalirozi/vigie-prix · adam.ali@aims-cameroon.org
