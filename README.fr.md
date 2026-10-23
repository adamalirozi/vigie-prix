# Vigie Prix — démonstration (MVP)

Des prévisions de prix des céréales à **1, 2 et 3 mois** pour « Al Aswak » et le suivi du **MEB**, sur données publiques
du WFP (prix de détail en FCFA/kg). **Démonstration** : seuils, alertes et composition du MEB **non validés par le SISAAP**.

**Démo en ligne** : https://vigie-prix-nzmskazxva2ysia9wlmneh.streamlit.app

## Ce que montre la démonstration
- **Provinces et départements** : prix au kilo, projection M+1/M+2/M+3, carte cliquable, marchés suivis, prix estimés
  indiqués comme tels.
- **Relecture** : l'outil refait la prévision à une date passée avec les seules données alors disponibles, puis la compare à
  ce qui s'est passé (trois épisodes de la soudure 2024).
- **Alertes** : hausse rapide, seuil de prix, seuil MEB ; niveau de confiance et facteurs ; **validation par un analyste**,
  journal, message prêt pour le Cluster Sécurité Alimentaire (rien n'est envoyé).
- **MEB** (composante céréales), **brouillon Al Aswak** (export Word), **page Fiabilité & données** (rétro-test contre
  « prix inchangé », niveaux de méthode, audit de couverture, marchés pilotes proposés).

## Lancer en local
```bash
python -m venv .venv && source .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Honnêteté sur la méthode
La projection actuelle est une **référence saisonnière** (niveau 1) : sur les données publiques, elle est à peu près aussi
précise que « prix inchangé » à 3 mois. Elle sert de point de comparaison que les niveaux 2 et 3 (marchés voisins,
carburant, pluie, conflit, apprentissage sur séries SIMPA) devront battre. Détails : onglet *Fiabilité & données*.

## Documentation
[Données et licences](docs/DATA.md) · [Déploiement](docs/DEPLOYMENT.md) · [Déroulé de démonstration](docs/DEMO_SCRIPT.md) ·
[Contribuer](CONTRIBUTING.md) · [Sécurité](SECURITY.md) · [Journal des modifications](CHANGELOG.md)

Code sous licence MIT ; les données gardent la licence de leurs producteurs.
