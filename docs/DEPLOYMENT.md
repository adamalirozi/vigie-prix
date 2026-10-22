# Déploiement sur Streamlit Community Cloud

1. Dépôt GitHub contenant `app.py`, `requirements.txt` (versions épinglées) et `data/` à la racine.
2. Compte sur https://share.streamlit.io, connecté à GitHub (autoriser l'accès au dépôt).
3. **Create app** → *Yup, I have an app* → dépôt, branche `main`, fichier `app.py`.
4. **Advanced settings** → Python **3.12** (version testée). Aucun secret n'est nécessaire.
5. **Deploy**. Premier démarrage : quelques minutes (installation des dépendances).
6. Mise à jour : `git push` sur `main` redéploie automatiquement ; changer `requirements.txt` réinstalle les dépendances.

## À savoir
- Ressources partagées et limitées (jusqu'à 2 cœurs, 2,7 Go de mémoire). L'application utilise environ 250 Mo.
- Une application sans visite pendant 12 heures s'endort ; un clic la réveille. Prévoir de la réveiller avant une démonstration.
- Le disque est **éphémère** : les validations d'alertes sont perdues au redémarrage. En démonstration publique, chaque
  visiteur a ses propres validations (`VIGIE_ISOLATE_SESSIONS=1`, valeur par défaut).
- Une version de Python ne se change qu'en supprimant et redéployant l'application.
- Une seule application privée par compte ; pour limiter l'accès : *Share* → *Only specific people can view this app*.
- Sans connexion internet côté salle de démonstration : activer « Carte sans fond (hors ligne) ».

## Autres hébergements
`streamlit run app.py --server.port 8501` sur un serveur ; ou un conteneur Docker (image Python 3.12, `pip install -r
requirements.txt`, `EXPOSE 8501`). Pour un pilote réel : authentification, stockage persistant des validations
(`VIGIE_ISOLATE_SESSIONS=0` seulement derrière une authentification), HTTPS et journalisation d'accès.
