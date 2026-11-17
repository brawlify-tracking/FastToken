# Bot Discord PayPal et Litecoin

Bot Python utilisant `discord.py` et le préfixe `!`.

## 1. Configurer les liens et l'adresse

Dans `config.py`, remplace les valeurs vides :

- `PAYPAL_LINK` : ton lien PayPal complet, commençant par `https://`
- `LITECOIN_ADDRESS` : ton adresse de réception Litecoin

Enregistre le fichier après modification.

## 2. Ajouter le token dans les Secrets

Dans Replit, ouvre **Tools > Secrets** et ajoute :

- Nom : `DISCORD_TOKEN`
- Valeur : le token de ton bot Discord

Ne colle jamais ce token dans `config.py`, dans le chat ou dans un fichier du projet.

## 3. Activer l'intention nécessaire sur Discord

Dans le portail développeur Discord, ouvre ton application, puis **Bot** et active
**Message Content Intent**. Les commandes avec le préfixe `!` en ont besoin.

Quand tu ajoutes le bot à ton serveur, donne-lui au minimum les permissions
nécessaires pour voir les salons concernés et envoyer des messages.

## 4. Installer et lancer

Dans le Shell du projet, lance une fois :

```sh
python3 -m pip install -r discord-bot/requirements.txt
```

Après avoir ajouté `DISCORD_TOKEN` dans Secrets, lance le bot avec :

```sh
python3 discord-bot/main.py
```

Tu peux aussi choisir le workflow **Discord Bot** dans Replit pour le démarrer
et consulter ses journaux.

## Commandes

- `!ppl` envoie le lien PayPal configuré.
- `!ltc` envoie l'adresse Litecoin configurée.

Si une valeur est encore vide ou invalide, le bot explique quel réglage corriger.
