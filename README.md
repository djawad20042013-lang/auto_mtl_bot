# 🚗 Moniteur Automatique — Toyota Corolla Montréal

Agent gratuit qui surveille **Kijiji** et **Craigslist** pour trouver des Toyota Corolla à moins de 3 000 $ avec moins de 140 000 km, filtre les annonces avec des problèmes majeurs, et t'envoie une notification Telegram instantanément.

---

## Comment ça marche

Le script fait 4 choses à chaque exécution :

1. **Cherche** les nouvelles annonces sur Kijiji et Craigslist Montréal
2. **Filtre** par prix (< 3 000 $) et kilométrage (< 140 000 km)
3. **Analyse** la description pour détecter les problèmes majeurs vs mineurs (50+ mots-clés FR/EN)
4. **Notifie** via Telegram (ou email) seulement les bonnes annonces

Le workflow GitHub Actions exécute le script automatiquement toutes les 2 heures, gratuitement.

---

## Installation en 4 étapes

### Étape 1 — Créer ton bot Telegram (5 minutes)

1. Ouvre Telegram et cherche **@BotFather**
2. Envoie `/newbot`
3. Donne un nom (ex: "Mon Moniteur Auto")
4. Donne un username (ex: `mon_moniteur_auto_bot`)
5. **Copie le token** que BotFather te donne (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
6. Ouvre une conversation avec ton nouveau bot et envoie `/start`
7. Va sur `https://api.telegram.org/bot<TON_TOKEN>/getUpdates`
8. Trouve ton `chat_id` dans la réponse JSON (un nombre comme `123456789`)

### Étape 2 — Créer le repo GitHub (5 minutes)

1. Va sur [github.com/new](https://github.com/new)
2. Crée un nouveau repo (public = gratuit pour GitHub Actions)
3. Upload tous les fichiers de ce dossier dans le repo

### Étape 3 — Configurer les secrets (2 minutes)

Dans ton repo GitHub :

1. Va dans **Settings** → **Secrets and variables** → **Actions**
2. Clique **New repository secret** et ajoute :
   - Nom: `TELEGRAM_BOT_TOKEN` — Valeur: ton token de l'étape 1
   - Nom: `TELEGRAM_CHAT_ID` — Valeur: ton chat_id de l'étape 1

### Étape 4 — Activer le workflow (1 minute)

1. Va dans l'onglet **Actions** de ton repo
2. Tu devrais voir le workflow "🚗 Moniteur Toyota Corolla"
3. Clique **Enable workflow**
4. Clique **Run workflow** pour un premier test

C'est tout! Le script tournera automatiquement toutes les 2 heures.

---

## Utilisation locale (optionnel)

Si tu veux aussi le rouler sur ton ordinateur :

```bash
# Installer les dépendances
pip install -r requirements.txt

# Configurer Telegram (remplace par tes vraies valeurs)
export TELEGRAM_BOT_TOKEN="ton_token_ici"
export TELEGRAM_CHAT_ID="ton_chat_id_ici"

# Tester la connexion Telegram
python scraper.py --test

# Lancer une recherche
python scraper.py

# Effacer l'historique des annonces vues
python scraper.py --reset
```

Pour une exécution automatique locale (Linux/Mac), ajoute un cron job :

```bash
# Ouvre l'éditeur cron
crontab -e

# Ajoute cette ligne (exécution toutes les 2 heures)
0 */2 * * * cd /chemin/vers/car-monitor && /usr/bin/python3 scraper.py >> log.txt 2>&1
```

---

## Et Facebook Marketplace?

Facebook n'offre pas d'API publique et bloque activement le scraping automatisé. Voici la meilleure approche gratuite pour le couvrir aussi :

1. Ouvre Facebook Marketplace
2. Cherche : `Toyota Corolla`
3. Applique les filtres : Prix max 3 000 $, rayon 50 km
4. Clique **Enregistrer la recherche** (icône cloche 🔔)
5. Facebook t'enverra des notifications pour les nouvelles annonces

Combine ça avec ce script pour couvrir Kijiji + Craigslist automatiquement, et tu auras une couverture quasi complète du marché montréalais.

---

## Personnalisation

Pour modifier les critères, édite la section `CONFIG` dans `scraper.py` :

```python
CONFIG = {
    "marque": "toyota",
    "modele": "corolla",
    "prix_max": 3000,       # Change le prix max ici
    "km_max": 140000,       # Change le km max ici
    "ville": "ville-de-montreal",  # Autre ville Kijiji
    # ...
}
```

Pour modifier les mots-clés de filtrage (problèmes majeurs/mineurs), édite les listes `PROBLEMES_MAJEURS` et `PROBLEMES_MINEURS` dans le même fichier.

---

## Coût total : 0 $

| Service | Coût | Utilisation |
|---------|------|-------------|
| GitHub Actions | Gratuit | 2 000 min/mois (on en utilise ~105) |
| Telegram Bot | Gratuit | Notifications illimitées |
| Kijiji | Gratuit | Recherche publique |
| Craigslist | Gratuit | Recherche publique |
| Facebook Marketplace | Gratuit | Alertes intégrées |
