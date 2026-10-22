# Politique de sécurité

## Signaler une vulnérabilité
N'ouvrez **pas** de ticket public. Écrivez à adam.ali@aims-cameroon.org avec une description, les étapes pour
reproduire et l'impact estimé. Nous accusons réception sous 5 jours ouvrés.

## Données et confidentialité
- Ce dépôt ne contient **que des données publiques** (prix WFP, limites administratives). Aucune donnée de ménage ou de
  bénéficiaire, aucun secret, aucun identifiant.
- N'ajoutez jamais de données non publiques du SISAAP, de la DPSA ou de l'ONASA à ce dépôt public. Les séries SIMPA
  doivent être fournies à l'exécution (stockage privé), pas committées.
- Les secrets (clés, mots de passe) vont dans `.streamlit/secrets.toml` (ignoré par Git) ou dans les « Secrets » de la
  plateforme d'hébergement.

## Limites de la version de démonstration
Le sélecteur de profil « Analyste / Lecteur » n'est **pas** une authentification. Avant tout pilote réel : ajouter une
authentification, un stockage persistant des validations et un contrôle d'accès.
