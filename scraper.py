#!/usr/bin/env python3
"""
🚗 Moniteur de voitures - Kijiji & Craigslist
Cherche automatiquement des Toyota Corolla à bon prix à Montréal
et envoie des notifications Telegram quand une annonce correspond.

Utilisation:
    python scraper.py              # Exécution unique
    python scraper.py --test       # Tester la notification Telegram
    python scraper.py --reset      # Effacer l'historique des annonces vues
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — Modifie ces valeurs selon tes besoins
# ═══════════════════════════════════════════════════════════════

CONFIG = {
    # Critères de recherche
    "marque": "toyota",
    "modele": "corolla",
    "prix_max": 3000,
    "km_max": 140000,
    "ville": "ville-de-montreal",
    "rayon_km": 50,

    # Telegram (voir README pour obtenir ces valeurs)
    "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),

    # Email (optionnel, alternative à Telegram)
    "email_actif": False,
    "email_expediteur": os.environ.get("EMAIL_FROM", ""),
    "email_mot_de_passe": os.environ.get("EMAIL_PASSWORD", ""),
    "email_destinataire": os.environ.get("EMAIL_TO", ""),
    "email_smtp": "smtp.gmail.com",
    "email_port": 587,
}

# ═══════════════════════════════════════════════════════════════
# FILTRAGE INTELLIGENT — Problèmes mineurs vs majeurs
# ═══════════════════════════════════════════════════════════════

# Mots-clés indiquant des PROBLÈMES MAJEURS → on REJETTE l'annonce
PROBLEMES_MAJEURS = [
    # Mécanique grave
    r"transmission\s+(à\s+changer|finie|brisée|morte|slip|patine)",
    r"moteur\s+(à\s+changer|brûlé|mort|fini|grippé|seized|blown)",
    r"engine\s+(blown|seized|knock|replacement)",
    r"head\s+gasket", r"joint\s+de\s+culasse",
    r"accident\s+majeur", r"major\s+accident",
    r"total\s+loss", r"perte\s+totale",
    r"salvage", r"reconstruit", r"rebuilt\s+title",
    r"flood\s+damage", r"dommage.+inondation",
    r"frame\s+(rust|damage|rot|bend)", r"châssis\s+(rouillé|endommagé|plié)",
    r"sous-?cadre\s+(pourri|rouillé|percé)",
    r"subframe\s+(rust|rot|hole)",
    r"timing\s+(chain|belt)\s+(broke|broken|snapped)",
    r"chaîne\s+de\s+distribution\s+(brisée|cassée)",
    r"catalytic\s+converter\s+(stolen|missing)",
    r"catalyseur\s+(volé|manquant)",
    r"ne\s+(roule|démarre|part)\s+(plus|pas)",
    r"does\s+not\s+(run|start|drive)",
    r"non\s+roulable", r"not\s+drivable", r"not\s+running",
    r"pour\s+(pièces|les\s+pièces|la\s+scrap)", r"for\s+parts",
    r"scrap", r"ferraille",
    r"turbo\s+(mort|fini|blown)",
    r"overheating", r"surchauffe",
    r"rod\s+knock", r"cognement",
    r"cracked\s+block", r"bloc\s+(fissuré|craqué)",
]

# Mots-clés indiquant des PROBLÈMES MINEURS → on ACCEPTE
PROBLEMES_MINEURS = [
    r"égratignure", r"scratch", r"éraflure",
    r"bosse\s+mineur", r"small\s+dent", r"minor\s+dent", r"petite\s+bosse",
    r"a/?c\s+(ne\s+fonctionne|broken|not\s+working|à\s+recharger)",
    r"air\s+climatisé", r"climatisation",
    r"window\s+(regulator|motor)", r"lève-?vitre",
    r"radio", r"speaker", r"haut-?parleur",
    r"cosmétique", r"cosmetic",
    r"peinture\s+(écaillée|usée)", r"paint\s+(chip|fade|peel)",
    r"rust\s+(minor|surface|small|spot)", r"rouille\s+(mineur|surface|légère|petite)",
    r"brake\s+(pad|rotor)", r"freins\s+à\s+(faire|changer)",
    r"plaquettes", r"disques\s+de\s+frein",
    r"pneus?\s+(à\s+changer|usé|worn)", r"tires?\s+(worn|need)",
    r"exhaust\s+(leak|small)", r"petit.+exhaust",
    r"muffler", r"silencieux",
    r"check\s+engine\s+light", r"lumière\s+moteur",
    r"sensor", r"capteur",
    r"battery", r"batterie",
    r"alternator", r"alternateur",
    r"starter", r"démarreur",
    r"tie\s+rod", r"ball\s+joint", r"rotule",
    r"bearing", r"roulement",
    r"suspension\s+(usée|worn|bruit|noise)",
    r"strut", r"amortisseur", r"shock",
    r"alignment", r"alignement",
    r"needs?\s+(inspection|safety)", r"à\s+inspecter",
]

# ═══════════════════════════════════════════════════════════════
# FICHIER D'HISTORIQUE — évite de renvoyer la même annonce
# ═══════════════════════════════════════════════════════════════

HISTORIQUE_PATH = Path(__file__).parent / "annonces_vues.json"


def charger_historique() -> set:
    if HISTORIQUE_PATH.exists():
        with open(HISTORIQUE_PATH, "r") as f:
            return set(json.load(f))
    return set()


def sauvegarder_historique(historique: set):
    with open(HISTORIQUE_PATH, "w") as f:
        json.dump(list(historique), f)


# ═══════════════════════════════════════════════════════════════
# ANALYSE DES ANNONCES
# ═══════════════════════════════════════════════════════════════


def analyser_problemes(texte: str) -> dict:
    """Analyse le texte d'une annonce pour détecter les problèmes."""
    texte_lower = texte.lower()
    majeurs_trouves = []
    mineurs_trouves = []

    for pattern in PROBLEMES_MAJEURS:
        match = re.search(pattern, texte_lower)
        if match:
            majeurs_trouves.append(match.group())

    for pattern in PROBLEMES_MINEURS:
        match = re.search(pattern, texte_lower)
        if match:
            mineurs_trouves.append(match.group())

    return {
        "majeurs": majeurs_trouves,
        "mineurs": mineurs_trouves,
        "verdict": "REJETÉ" if majeurs_trouves else "ACCEPTÉ",
    }


def extraire_km(texte: str) -> int | None:
    """Extrait le kilométrage d'un texte."""
    patterns = [
        r"([\d,.\s]+)\s*km",
        r"([\d,.\s]+)\s*kilo",
        r"([\d,.\s]+)\s*miles?",
    ]
    for pattern in patterns:
        match = re.search(pattern, texte.lower())
        if match:
            nombre = match.group(1).replace(",", "").replace(" ", "").replace(".", "")
            try:
                km = int(nombre)
                if "mile" in pattern:
                    km = int(km * 1.60934)
                if 1000 < km < 900000:
                    return km
            except ValueError:
                continue
    return None


def extraire_prix(texte: str) -> int | None:
    """Extrait le prix d'un texte."""
    patterns = [
        r"\$\s*([\d,.\s]+)",
        r"([\d,.\s]+)\s*\$",
        r"([\d,.\s]+)\s*dollars?",
    ]
    for pattern in patterns:
        match = re.search(pattern, texte.lower())
        if match:
            nombre = match.group(1).replace(",", "").replace(" ", "").replace(".", "")
            try:
                prix = int(nombre)
                if 100 < prix < 50000:
                    return prix
            except ValueError:
                continue
    return None


# ═══════════════════════════════════════════════════════════════
# SCRAPER KIJIJI
# ═══════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def chercher_kijiji() -> list[dict]:
    """Cherche des Toyota Corolla sur Kijiji Montréal."""
    annonces = []
    prix_max = CONFIG["prix_max"]
    ville = CONFIG["ville"]

    url = (
        f"https://www.kijiji.ca/b-autos-camions/{ville}"
        f"/toyota-corolla/k0c174l1700281"
        f"?price=__${prix_max}"
        f"&kilometers=__140000km"
        f"&sort=dateDesc"
    )

    print(f"🔍 Recherche Kijiji: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Kijiji utilise différentes structures — on essaie plusieurs sélecteurs
        items = soup.select("[data-listing-id]")
        if not items:
            items = soup.select("li.search-item, div.search-item")
        if not items:
            items = soup.select("[data-testid='listing-card']")

        print(f"   → {len(items)} annonces trouvées sur la page")

        for item in items:
            try:
                annonce = parser_annonce_kijiji(item)
                if annonce:
                    annonces.append(annonce)
            except Exception as e:
                print(f"   ⚠️ Erreur parsing annonce: {e}")
                continue

    except requests.RequestException as e:
        print(f"❌ Erreur Kijiji: {e}")

    return annonces


def parser_annonce_kijiji(item) -> dict | None:
    """Parse une annonce Kijiji individuelle."""
    # Titre
    titre_el = item.select_one("a.title, h3 a, [data-testid='listing-title'] a, a[class*='title']")
    if not titre_el:
        titre_el = item.select_one("a")
    if not titre_el:
        return None

    titre = titre_el.get_text(strip=True)
    lien = titre_el.get("href", "")
    if lien and not lien.startswith("http"):
        lien = "https://www.kijiji.ca" + lien

    # Prix
    prix_el = item.select_one(".price, [class*='price'], [data-testid='listing-price']")
    prix_texte = prix_el.get_text(strip=True) if prix_el else ""
    prix = extraire_prix(prix_texte) if prix_texte else None

    # Description courte
    desc_el = item.select_one(".description, [class*='description']")
    description = desc_el.get_text(strip=True) if desc_el else ""

    # Kilométrage (souvent dans les attributs)
    km = None
    attrs = item.select("[class*='attribute'], [class*='detail']")
    for attr in attrs:
        texte = attr.get_text(strip=True)
        km_found = extraire_km(texte)
        if km_found:
            km = km_found
            break

    if km is None:
        km = extraire_km(titre + " " + description + " " + prix_texte)

    # ID unique
    listing_id = item.get("data-listing-id", "")
    if not listing_id:
        listing_id = hashlib.md5(lien.encode()).hexdigest()[:12]

    return {
        "id": f"kijiji_{listing_id}",
        "source": "Kijiji",
        "titre": titre,
        "prix": prix,
        "km": km,
        "lien": lien,
        "description": description,
        "texte_complet": f"{titre} {description} {prix_texte}",
    }


# ═══════════════════════════════════════════════════════════════
# SCRAPER CRAIGSLIST (Montréal)
# ═══════════════════════════════════════════════════════════════


def chercher_craigslist() -> list[dict]:
    """Cherche des Toyota Corolla sur Craigslist Montréal."""
    annonces = []
    prix_max = CONFIG["prix_max"]

    url = (
        f"https://montreal.craigslist.org/search/cta"
        f"?query=toyota+corolla"
        f"&max_price={prix_max}"
        f"&sort=date"
    )

    print(f"🔍 Recherche Craigslist: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.select("li.cl-static-search-result, .result-row, li.cl-search-result")
        print(f"   → {len(items)} annonces trouvées")

        for item in items:
            try:
                # Titre + lien
                titre_el = item.select_one("a.titlestring, a.posting-title, a[class*='title'], a")
                if not titre_el:
                    continue

                titre = titre_el.get_text(strip=True)
                lien = titre_el.get("href", "")
                if lien and not lien.startswith("http"):
                    lien = "https://montreal.craigslist.org" + lien

                # Prix
                prix_el = item.select_one(".priceinfo, .result-price, [class*='price']")
                prix_texte = prix_el.get_text(strip=True) if prix_el else ""
                prix = extraire_prix(prix_texte)

                # Détails
                meta_el = item.select_one(".meta, .result-meta")
                meta = meta_el.get_text(strip=True) if meta_el else ""
                km = extraire_km(titre + " " + meta)

                listing_id = hashlib.md5(lien.encode()).hexdigest()[:12]

                annonces.append({
                    "id": f"craigslist_{listing_id}",
                    "source": "Craigslist",
                    "titre": titre,
                    "prix": prix,
                    "km": km,
                    "lien": lien,
                    "description": meta,
                    "texte_complet": f"{titre} {meta}",
                })

            except Exception as e:
                print(f"   ⚠️ Erreur parsing: {e}")
                continue

    except requests.RequestException as e:
        print(f"❌ Erreur Craigslist: {e}")

    return annonces


# ═══════════════════════════════════════════════════════════════
# DÉTAILS D'UNE ANNONCE (fetch la page complète)
# ═══════════════════════════════════════════════════════════════


def obtenir_details(annonce: dict) -> str:
    """Va chercher la description complète d'une annonce."""
    if not annonce.get("lien"):
        return annonce.get("description", "")

    try:
        time.sleep(1)  # politesse
        resp = requests.get(annonce["lien"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Kijiji
        desc = soup.select_one("[class*='descriptionContainer'], #posti-description")
        if desc:
            return desc.get_text(strip=True)

        # Craigslist
        desc = soup.select_one("#postingbody")
        if desc:
            return desc.get_text(strip=True)

        # Fallback
        return soup.get_text(strip=True)[:2000]

    except Exception as e:
        print(f"   ⚠️ Impossible de charger les détails: {e}")
        return annonce.get("description", "")


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════


def envoyer_telegram(message: str):
    """Envoie un message via Telegram Bot."""
    token = CONFIG["telegram_bot_token"]
    chat_id = CONFIG["telegram_chat_id"]

    if not token or not chat_id:
        print("⚠️  Telegram non configuré — notification affichée en console seulement")
        print("=" * 60)
        print(message)
        print("=" * 60)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print("✅ Notification Telegram envoyée!")
    except requests.RequestException as e:
        print(f"❌ Erreur Telegram: {e}")


def envoyer_email(sujet: str, corps: str):
    """Envoie un email via Gmail SMTP."""
    if not CONFIG["email_actif"]:
        return

    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(corps, "html")
    msg["Subject"] = sujet
    msg["From"] = CONFIG["email_expediteur"]
    msg["To"] = CONFIG["email_destinataire"]

    try:
        with smtplib.SMTP(CONFIG["email_smtp"], CONFIG["email_port"]) as server:
            server.starttls()
            server.login(CONFIG["email_expediteur"], CONFIG["email_mot_de_passe"])
            server.send_message(msg)
            print("✅ Email envoyé!")
    except Exception as e:
        print(f"❌ Erreur email: {e}")


def formater_notification(annonce: dict, analyse: dict) -> str:
    """Formate le message de notification."""
    prix = f"${annonce['prix']:,}" if annonce["prix"] else "Prix non indiqué"
    km = f"{annonce['km']:,} km" if annonce["km"] else "KM non indiqué"
    mineurs = ", ".join(analyse["mineurs"][:5]) if analyse["mineurs"] else "Aucun détecté"

    return (
        f"🚗 <b>NOUVELLE ANNONCE TROUVÉE!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{annonce['titre']}</b>\n"
        f"💰 Prix: <b>{prix}</b>\n"
        f"📏 Kilométrage: <b>{km}</b>\n"
        f"📍 Source: {annonce['source']}\n"
        f"🔧 Problèmes mineurs: {mineurs}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 {annonce['lien']}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


# ═══════════════════════════════════════════════════════════════
# LOGIQUE PRINCIPALE
# ═══════════════════════════════════════════════════════════════


def filtrer_annonce(annonce: dict) -> tuple[bool, dict]:
    """
    Applique tous les filtres sur une annonce.
    Retourne (acceptée: bool, analyse: dict)
    """
    # Filtre prix
    if annonce["prix"] and annonce["prix"] > CONFIG["prix_max"]:
        return False, {"raison": f"Prix trop élevé: ${annonce['prix']}"}

    # Filtre km
    if annonce["km"] and annonce["km"] > CONFIG["km_max"]:
        return False, {"raison": f"Trop de km: {annonce['km']}"}

    # Vérifie que c'est bien une Corolla
    texte = annonce["texte_complet"].lower()
    if "corolla" not in texte:
        return False, {"raison": "Pas une Corolla"}

    # Analyse les problèmes
    # On va chercher la description complète pour mieux analyser
    details = obtenir_details(annonce)
    texte_complet = f"{annonce['texte_complet']} {details}"
    analyse = analyser_problemes(texte_complet)

    if analyse["verdict"] == "REJETÉ":
        return False, analyse

    # Mettre à jour le km si on l'a trouvé dans les détails
    if annonce["km"] is None:
        km = extraire_km(details)
        if km:
            annonce["km"] = km
            if km > CONFIG["km_max"]:
                return False, {"raison": f"Trop de km (détails): {km}"}

    return True, analyse


def executer():
    """Fonction principale — cherche et filtre les annonces."""
    print(f"\n{'='*60}")
    print(f"🚗 Moniteur Toyota Corolla — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Prix max: ${CONFIG['prix_max']} | KM max: {CONFIG['km_max']:,}")
    print(f"{'='*60}\n")

    historique = charger_historique()
    nouvelles = 0

    # Chercher sur toutes les sources
    toutes_annonces = []
    toutes_annonces.extend(chercher_kijiji())
    time.sleep(2)
    toutes_annonces.extend(chercher_craigslist())

    print(f"\n📊 Total: {len(toutes_annonces)} annonces trouvées")

    for annonce in toutes_annonces:
        # Déjà vue?
        if annonce["id"] in historique:
            continue

        print(f"\n🔎 Analyse: {annonce['titre'][:60]}...")

        acceptee, analyse = filtrer_annonce(annonce)
        historique.add(annonce["id"])

        if acceptee:
            nouvelles += 1
            message = formater_notification(annonce, analyse)
            print(f"   ✅ ACCEPTÉE — Envoi notification...")
            envoyer_telegram(message)
            if CONFIG["email_actif"]:
                envoyer_email(
                    f"🚗 Toyota Corolla trouvée — {annonce['prix']}$",
                    message.replace("\n", "<br>"),
                )
            time.sleep(1)
        else:
            raison = analyse.get("raison", "")
            majeurs = analyse.get("majeurs", [])
            if majeurs:
                raison = f"Problèmes majeurs: {', '.join(majeurs[:3])}"
            print(f"   ❌ Rejetée — {raison}")

    sauvegarder_historique(historique)

    print(f"\n{'='*60}")
    print(f"✅ Terminé! {nouvelles} nouvelle(s) annonce(s) envoyée(s)")
    print(f"   {len(historique)} annonces dans l'historique total")
    print(f"{'='*60}\n")


def tester_telegram():
    """Envoie un message test sur Telegram."""
    print("📤 Test de notification Telegram...")
    envoyer_telegram(
        "🧪 <b>TEST — Moniteur Toyota Corolla</b>\n\n"
        "✅ La connexion Telegram fonctionne!\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


# ═══════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--test" in sys.argv:
        tester_telegram()
    elif "--reset" in sys.argv:
        if HISTORIQUE_PATH.exists():
            HISTORIQUE_PATH.unlink()
            print("🗑️  Historique effacé!")
        else:
            print("ℹ️  Pas d'historique à effacer.")
    else:
        executer()
