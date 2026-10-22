# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; versionnement [SemVer](https://semver.org/lang/fr/).

## [0.1.0] — 2026-10-22 — Démonstration (MVP)

### Ajouté
- Tableau de bord provinces / départements : prix au kilo, projections à **M+1, M+2, M+3**, carte cliquable, couche des marchés.
- Quatre produits : mil, sorgho, maïs, riz importé ; scénarios illustratifs ; moyenne 5 ans et seuil d'alerte de prix.
- **Mode relecture** : prévision refaite à une date passée avec les seules données disponibles, comparée au réalisé ;
  trois épisodes de la soudure 2024.
- **Alertes** (hausse rapide, seuil de prix, seuil MEB) avec confiance et facteurs ; validation par un analyste,
  journal, message prêt pour le Cluster.
- **MEB** (composante céréales) avec seuil réglable ; composition dans `data/meb_composition.csv`.
- **Brouillon Al Aswak** (texte et export Word avec graphiques).
- Page **Fiabilité & données** : rétro-test hors échantillon contre « prix inchangé », niveaux de méthode,
  audit de couverture, marchés pilotes proposés.
- Nettoyage des données (relevés isolés, mois synchronisés), rattachement des marchés aux provinces.
- 126 tests automatisés, intégration continue.

### Limites connues
- Données publiques WFP arrêtées à juin 2026 ; seuils, scénarios et composition du MEB non validés par le SISAAP.
- Méthode de niveau 1 uniquement (référence saisonnière) ; facteurs externes non connectés.
