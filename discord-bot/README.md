# Bot Discord PayPal et Litecoin

Bot Python utilisant `discord.py` et le préfixe `!`.

## 1. Configurer les liens et l'adresse

Dans `config.py`, modifie les valeurs :

- `PAYPAL_LINK` : ton lien PayPal complet, commençant par `https://`
- `LITECOIN_ADDRESS_SHIN` : l'adresse Litecoin envoyée par `!ltc`
- `LITECOIN_ADDRESS_YASKO` : l'adresse Litecoin envoyée par `!ltcy`
- `VOUCH_PROMPT` : le texte envoyé au client par `!vch`

Enregistre le fichier après modification.

## 2. Ajouter le token dans les Secrets

Dans Replit, ouvre **Tools > Secrets** et ajoute :

- Nom : `DISCORD_TOKEN`
- Valeur : le token de ton bot Discord

Ne colle jamais ce token dans `config.py`, dans le chat ou dans un fichier du projet.

## 3. Activer l'intention nécessaire sur Discord

Dans le portail développeur Discord, ouvre ton application, puis **Bot** et active
**Message Content Intent**. Les commandes avec le préfixe `!` en ont besoin.

Quand tu ajoutes le bot à ton serveur, donne-lui les permissions nécessaires
pour voir les salons, envoyer des messages, intégrer des liens et gérer les rôles.

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
- `!ltc` envoie l'adresse « Shin Addy » configurée.
- `!ltcy` envoie l'adresse « Yasko Addy » configurée.
- `!verifysetup @Rôle` publie un panneau de vérification dans le salon courant.
- `!vchsetup #salon` configure le salon de publication des vouches; sans argument,
  la commande affiche le salon actuel.
- `!vch` publie le message de vouch dans le ticket. La prochaine réponse textuelle
  d'un membre sans la permission « Gérer les messages » est copiée dans le salon
  configuré, sans nom ni lien vers le ticket. La demande expire après 15 minutes.

Si une valeur est encore vide ou invalide, le bot explique quel réglage corriger.

## Publier les vouches

1. Crée le salon où tu veux afficher les vouches. Un administrateur lance
   `!vchsetup #vouches` en mentionnant le salon; le réglage est conservé.
2. Autorise le bot à voir ce salon, à envoyer des messages et à intégrer des liens.
3. Dans un ticket, un membre du staff ayant la permission **Gérer les messages**
   lance `!vch`.
4. Le bot affiche `+rep FastToken Boost ❤️‍🩹` et indique au client que sa prochaine
   réponse sera publiée sans son nom. Cette réponse textuelle est publiée dans
   le salon configuré sous forme d'embed, sans auteur ni lien vers le ticket.

Le bot n'ajoute ni nom d'utilisateur ni lien vers le ticket, retire les mentions
Discord et ne recopie pas les pièces jointes. La demande reste en attente au
redémarrage du bot et expire après 15 minutes. Le client doit éviter d'inclure
lui-même des informations personnelles dans son texte.

## Vérification des nouveaux membres

1. Crée un rôle de membre vérifié dans les paramètres du serveur.
2. Place le rôle du bot au-dessus de ce rôle et vérifie qu'il a la permission
   **Gérer les rôles**.
3. Dans le salon où les nouveaux membres se vérifieront, lance
   `!verifysetup @RôleVérifié` en mentionnant le rôle. Seuls les administrateurs
   peuvent publier ce panneau.
4. Dans les permissions des salons privés, cache-les à `@everyone` et autorise
   le rôle vérifié à les voir.

Le bouton attribue le rôle au membre et les panneaux restent actifs après un
redémarrage du bot.
