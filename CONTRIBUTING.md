# Contribuer

Merci de votre intérêt. Ce projet est une démonstration ; les contributions qui améliorent la fiabilité, la clarté ou la
documentation sont les bienvenues.

## Installation
```bash
git clone https://github.com/adamalirozi/vigie-prix.git && cd REPO
python -m venv .venv && source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
streamlit run app.py
```

## Avant d'ouvrir une demande de fusion (pull request)
```bash
ruff check .          # style et erreurs courantes
python -m pytest      # 126 tests, environ 2 minutes
```
- Une modification de la **méthode** (saisonnalité, seuils, nettoyage, confiance) s'accompagne d'un test et d'une mise à
  jour de `ui/components.py` (panneau « Méthodologie ») et du `CHANGELOG.md`.
- Une modification des **données** ne doit contenir que des données publiques, avec leur source et leur licence
  (voir `docs/DATA.md`).
- Aucune valeur « magique » dans le code : les constantes vont dans `config.py`.
- Garder une séparation nette : calcul dans `services/` (sans Streamlit), affichage dans `ui/`.

## Messages de commit
Format court à l'impératif : `Ajoute l'horizon M+2 aux alertes`, `Corrige le rattachement des marchés frontaliers`.
Préfixes conseillés : `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.

## Signaler un problème
Utilisez les modèles de tickets : anomalie, fonctionnalité, ou **problème de données** (prix suspect, marché mal
localisé, mois à écarter).
