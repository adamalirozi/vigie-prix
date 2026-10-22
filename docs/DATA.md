# Données : sources, licences, dictionnaire

Ce dépôt ne contient que des **données publiques**. Chaque jeu garde la licence de son producteur.

## Sources

| Fichier | Contenu | Producteur | Licence | Lien |
|---|---|---|---|---|
| `data/wfp_food_prices_tcd.csv` | Prix de détail mensuels par marché et produit (FCFA), Tchad | WFP (sources d'origine : FAO-WFP, FEWS NET via FAO GIEWS/FPMA, SIMPA, WFP) | Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO) | https://data.humdata.org/dataset/wfp-food-prices-for-chad |
| `data/wfp_markets_tcd.csv` | Registre des marchés (nom, province, département, latitude, longitude) | WFP, extrait du jeu « Global WFP markets » | CC BY-IGO | https://data.humdata.org/dataset/global-wfp-food-prices |
| `data/geo/tchad_provinces.geojson`, `tchad_departments.geojson` | Limites administratives niveaux 1 et 2 | geoBoundaries (champs `shapeName`, `shapeISO`, `shapeID`) | CC BY 4.0 pour la version « gbOpen » ; **vérifier la licence indiquée dans les métadonnées du fichier du Tchad** | https://www.geoboundaries.org |
| `data/meb_composition.csv` | Ration céréalière du MEB (kg par personne et par jour) | **Provisoire**, à remplacer par la composition validée du Cluster Sécurité Alimentaire | — | — |

Les prix sont fournis par le WFP « tels quels » ; leur exactitude n'est pas garantie par ce projet.

## Mentions à conserver (attribution)

> Prix : WFP Price Database via HDX (CC BY-IGO). Limites administratives : geoBoundaries — Runfola, D. et al. (2020),
> *geoBoundaries: A global database of political administrative boundaries*, PLOS ONE 15(4): e0231866.

## Dictionnaire des données brutes

**Prix** : `date` (jour 15 du mois), `admin1`, `admin2`, `market`, `market_id`, `latitude`, `longitude`, `category`,
`commodity`, `commodity_id`, `unit` (l'application n'utilise que `KG`), `priceflag`, `pricetype` (détail), `currency`
(XAF), `price`, `usdprice`.

**Marchés** : `market_id`, `market`, `countryiso3`, `admin1`, `admin2`, `latitude`, `longitude`.

**Produits suivis** (`config.py`, `COMMODITIES`) : Mil = `Millet` ; Sorgho = `Sorghum` puis `Sorghum (red)` (séries
fusionnées par ordre de priorité) ; Maïs = `Maize (white)` ; Riz importé = `Rice (imported)`.

## Ce que l'application en fait

1. Marchés sans coordonnées écartés (ex. Oum Hadjer). Province du marché = libellé administratif du WFP ; département =
   celui qui contient le point (ou le plus proche dans cette province).
2. **Nettoyage** : relevés isolés très éloignés de la médiane glissante du marché, et mois où tous les marchés bougent
   ensemble puis reviennent (anomalies synchronisées). Paramètres : `OUTLIER_*`, `SYNC_*` dans `config.py`.
3. Petits trous (≤ 2 mois) comblés par interpolation ; au-delà, la donnée reste absente.
4. Prix provincial = médiane des marchés actifs ; « prix actuel » = dernier prix de moins de 3 mois avant le dernier relevé.

## Mettre à jour les données

Télécharger le CSV « Chad - Food Prices » et les lignes du Tchad du CSV « Global WFP markets » sur HDX, les enregistrer
sous les mêmes noms dans `data/`, vérifier les colonnes, lancer `python -m pytest`, puis `git commit` et `git push`.
Le cache de l'application se renouvelle seul (clé : date de modification des fichiers).

## Anomalies connues (à confirmer avec le SISAAP)

- Mois synchronisés écartés : septembre 2024 et janvier 2025 (tous produits), mai 2026 (mil), et quelques autres
  selon le produit (liste dans l'application, page « Fiabilité & données »).
- Tibesti : aucun prix depuis août 2024. Maïs : aucun prix récent à Borkou, Ennedi et Wadi Fira.
- Plusieurs provinces ne sont suivies que par un ou deux marchés.
