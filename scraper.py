#!/usr/bin/env python3
"""
🚗 Moniteur de voitures — Kijiji & Craigslist
Cherche automatiquement des voitures à bon prix à Montréal
et envoie des notifications Telegram quand une annonce correspond.

Marques prioritaires: Toyota, Honda, Hyundai (⭐ dans les notifs)
Accepte aussi: toute autre marque qui respecte les critères

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
    "prix_max": 3000,
    "km_max": 140000,
    "ville": "ville-de-montreal",
    "rayon_km": 50,

    # Marques prioritaires (⭐ dans les notifs)
    "marques_prioritaires": ["toyota", "honda", "hyundai"],

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

PROBLEMES_MAJEURS = [
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
]

# ═══════════════════════════════════════════════════════════════
# FICHIER D'HISTORIQUE
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
# DÉTECTION DE MARQUE
# ═══════════════════════════════════════════════════════════════

MARQUES_CONNUES = {
    "toyota": ["toyota", "camry", "corolla", "rav4", "yaris", "matrix", "prius", "echo", "tercel", "celica", "solara", "avalon", "venza", "sienna", "tacoma", "tundra", "highlander", "4runner", "sequoia", "supra"],
    "honda": ["honda", "civic", "accord", "fit", "crv", "cr-v", "hrv", "hr-v", "element", "insight", "prelude", "del sol", "odyssey", "pilot", "ridgeline", "passport"],
    "hyundai": ["hyundai", "elantra", "sonata", "accent", "tucson", "santa fe", "veloster", "genesis", "kona", "venue", "ioniq", "tiburon"],
    "nissan": ["nissan", "sentra", "altima", "versa", "maxima", "rogue", "pathfinder", "murano", "frontier", "titan", "juke", "kicks"],
    "mazda": ["mazda", "mazda3", "mazda 3", "mazda6", "mazda 6", "cx-5", "cx5", "cx-3", "cx3", "mx-5", "miata", "protege", "tribute"],
    "subaru": ["subaru", "impreza", "outback", "forester", "legacy", "wrx", "crosstrek", "brz"],
    "kia": ["kia", "forte", "soul", "rio", "optima", "sportage", "sorento", "seltos", "stinger", "niro", "telluride"],
    "volkswagen": ["volkswagen", "vw", "jetta", "golf", "passat", "tiguan", "atlas", "beetle"],
    "ford": ["ford", "focus", "fusion", "fiesta", "escape", "explorer", "mustang", "ranger", "f-150", "f150", "taurus", "edge"],
    "chevrolet": ["chevrolet", "chevy", "cruze", "malibu", "impala", "equinox", "traverse", "trax", "spark", "sonic", "cobalt", "cavalier", "camaro", "silverado"],
    "mitsubishi": ["mitsubishi", "lancer", "outlander", "eclipse", "rvr", "mirage"],
    "dodge": ["dodge", "dart", "charger", "challenger", "journey", "caravan", "grand caravan", "durango", "neon"],
    "pontiac": ["pontiac", "vibe", "g5", "g6", "sunfire", "grand prix", "grand am", "wave"],
    "saturn": ["saturn", "ion", "astra", "vue", "outlook"],
    "suzuki": ["suzuki", "swift", "sx4", "aerio", "vitara", "grand vitara"],
    "acura": ["acura", "integra", "rsx", "tl", "tsx", "el", "csx", "mdx", "rdx", "ilx", "tlx"],
}


def detecter_marque(texte: str) -> str | None:
    texte_lower = texte.lower()
    for marque, mots_cles in MARQUES_CONNUES.items():
        for mot in mots_cles:
            if mot in texte_lower:
                return marque
    return None


def est_marque_prioritaire(texte: str) -> bool:
    marque = detecter_marque(texte)
    return marque in CONFIG["marques_prioritaires"]


# ═══════════════════════════════════════════════════════════════
# ANALYSE DES ANNONCES
# ═══════════════════════════════════════════════════════════════


def analyser_problemes(texte: str) -> dict:
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


def extraire_annee(texte: str) -> int | None:
    match = re.search(r"\b(19[89]\d|20[0-2]\d)\b", texte)
    if match:
        return int(match.group(1))
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
    annonces = []
    prix_max = CONFIG["prix_max"]
    ville = CONFIG["ville"]

    url = (
        f"https://www.kijiji.ca/b-autos-camions/grand-montreal"
        f"/k0c174l80002"
        f"?price=__${prix_max}"
        f"&kilometers=__140000km"
        f"&sort=dateDesc"
        f"&radius=200.0"
        f"&address=Montr%C3%A9al%2C+QC"
    )

    print(f"🔍 Recherche Kijiji (toutes marques): {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

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
    titre_el = item.select_one("a.title, h3 a, [data-testid='listing-title'] a, a[class*='title']")
    if not titre_el:
        titre_el = item.select_one("a")
    if not titre_el:
        return None

    titre = titre_el.get_text(strip=True)
    lien = titre_el.get("href", "")
    if lien and not lien.startswith("http"):
        lien = "https://www.kijiji.ca" + lien

    prix_el = item.select_one(".price, [class*='price'], [data-testid='listing-price']")
    prix_texte = prix_el.get_text(strip=True) if prix_el else ""
    prix = extraire_prix(prix_texte) if prix_texte else None

    desc_el = item.select_one(".description, [class*='description']")
    description = desc_el.get_text(strip=True) if desc_el else ""

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
    annonces = []
    prix_max = CONFIG["prix_max"]

    url = (
        f"https://montreal.craigslist.org/search/cta"
        f"?max_price={prix_max}"
        f"&sort=date"
    )

    print(f"🔍 Recherche Craigslist (toutes marques): {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.select("li.cl-static-search-result, .result-row, li.cl-search-result")
        print(f"   → {len(items)} annonces trouvées")

        for item in items:
            try:
                titre_el = item.select_one("a.titlestring, a.posting-title, a[class*='title'], a")
                if not titre_el:
                    continue

                titre = titre_el.get_text(strip=True)
                lien = titre_el.get("href", "")
                if lien and not lien.startswith("http"):
                    lien = "https://montreal.craigslist.org" + lien

                prix_el = item.select_one(".priceinfo, .result-price, [class*='price']")
                prix_texte = prix_el.get_text(strip=True) if prix_el else ""
                prix = extraire_prix(prix_texte)

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
# DÉTAILS D'UNE ANNONCE
# ═══════════════════════════════════════════════════════════════


def obtenir_details(annonce: dict) -> str:
    if not annonce.get("lien"):
        return annonce.get("description", "")

    try:
        time.sleep(1)
        resp = requests.get(annonce["lien"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        desc = soup.select_one("[class*='descriptionContainer'], #posti-description")
        if desc:
            return desc.get_text(strip=True)

        desc = soup.select_one("#postingbody")
        if desc:
            return desc.get_text(strip=True)

        return soup.get_text(strip=True)[:2000]

    except Exception as e:
        print(f"   ⚠️ Impossible de charger les détails: {e}")
        return annonce.get("description", "")


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════


def envoyer_telegram(message: str):
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
    prix = f"${annonce['prix']:,}" if annonce["prix"] else "Prix non indiqué"
    km = f"{annonce['km']:,} km" if annonce["km"] else "KM non indiqué"
    mineurs = ", ".join(analyse["mineurs"][:5]) if analyse["mineurs"] else "Aucun détecté"

    texte = annonce["texte_complet"]
    marque = detecter_marque(texte)
    marque_display = marque.upper() if marque else "AUTRE"
    annee = extraire_annee(annonce["titre"])
    annee_display = str(annee) if annee else "?"

    prioritaire = est_marque_prioritaire(texte)
    etoile = "⭐ " if prioritaire else ""
    badge = " — MARQUE PRIORITAIRE ⭐" if prioritaire else ""

    return (
        f"🚗 <b>{etoile}NOUVELLE ANNONCE TROUVÉE!{badge}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{annonce['titre']}</b>\n"
        f"🏷️ Marque: <b>{marque_display}</b> | Année: <b>{annee_display}</b>\n"
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
    # ❌ Pas de prix = on skip
    if annonce["prix"] is None:
        return False, {"raison": "Aucun prix indiqué"}

    # ❌ Prix trop élevé
    if annonce["prix"] > CONFIG["prix_max"]:
        return False, {"raison": f"Prix trop élevé: ${annonce['prix']}"}

    # ❌ Prix suspectement bas (probable arnaque ou pour pièces)
    if annonce["prix"] < 300:
        return False, {"raison": f"Prix trop bas (arnaque?): ${annonce['prix']}"}

    # ❌ Trop de km
    if annonce["km"] and annonce["km"] > CONFIG["km_max"]:
        return False, {"raison": f"Trop de km: {annonce['km']}"}

    texte = annonce["texte_complet"].lower()

    # ❌ Filtrer les concessionnaires et annonces commerciales
    mots_concessionnaire = [
        r"concessionnaire", r"dealership", r"dealer",
        r"certified\s+pre.owned", r"véhicule\s+certifié",
        r"financement\s+disponible", r"financing\s+available",
        r"garantie\s+prolongée", r"extended\s+warranty",
        r"www\.", r"\.com", r"\.ca",
        r"venez\s+nous\s+voir", r"come\s+visit",
        r"notre\s+inventaire", r"our\s+inventory",
        r"appelez.nous", r"call\s+us\s+today",
        r"car\s*fax", r"carproof",
        r"auto\s*trader", r"autotrader",
        r"groupe\s+auto", r"auto\s+group",
        r"motors?\s+(inc|ltd|ltée|enr)",
        r"autos?\s+(inc|ltd|ltée|enr)",
    ]
    for pattern in mots_concessionnaire:
        if re.search(pattern, texte):
            return False, {"raison": f"Concessionnaire détecté: {pattern}"}

    # ❌ Filtrer les voitures trop récentes (2020+, impossible sous 3000$ légitime)
    annee = extraire_annee(annonce["titre"])
    if annee and annee >= 2020:
        return False, {"raison": f"Voiture trop récente ({annee})"}

    # ❌ Filtrer les non-voitures (motos, VTT, pièces, etc.)
    mots_non_voiture = [
        r"\bmoto\b", r"\bmotorcycle\b", r"\bscooter\b",
        r"\bvtt\b", r"\batv\b", r"\bquad\b",
        r"\bbateau\b", r"\bboat\b",
        r"\bmotoneige\b", r"\bsnowmobile\b",
        r"\bremorque\b", r"\btrailer\b",
        r"\bcamion\s+lourd\b", r"\bheavy\s+truck\b",
        r"\bpièces?\s+d[e']", r"\bparts\s+for\b",
        r"\broue", r"\btire[s]?\s+for\s+sale",
        r"\bjante", r"\brim[s]?\s+for\b",
        r"\bmag[s]?\s+(pour|for)\b",
    ]
    for pattern in mots_non_voiture:
        if re.search(pattern, texte):
            return False, {"raison": f"Pas une voiture: {pattern}"}

    # Analyse les problèmes (va chercher la description complète)
    details = obtenir_details(annonce)
    texte_complet = f"{annonce['texte_complet']} {details}"
    analyse = analyser_problemes(texte_complet)

    # ❌ Vérifier les filtres concessionnaire dans les détails aussi
    for pattern in mots_concessionnaire:
        if re.search(pattern, details.lower()):
            return False, {"raison": f"Concessionnaire détecté (détails): {pattern}"}

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
    print(f"\n{'='*60}")
    print(f"🚗 Moniteur Auto Montréal — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Prix max: ${CONFIG['prix_max']} | KM max: {CONFIG['km_max']:,}")
    print(f"   Marques prioritaires: {', '.join(CONFIG['marques_prioritaires'])}")
    print(f"   + toutes les autres marques qui respectent les critères")
    print(f"{'='*60}\n")

    historique = charger_historique()
    nouvelles = 0
    prioritaires = 0

    toutes_annonces = []
    toutes_annonces.extend(chercher_kijiji())
    time.sleep(2)
    toutes_annonces.extend(chercher_craigslist())

    print(f"\n📊 Total: {len(toutes_annonces)} annonces trouvées")

    for annonce in toutes_annonces:
        if annonce["id"] in historique:
            continue

        print(f"\n🔎 Analyse: {annonce['titre'][:60]}...")

        acceptee, analyse = filtrer_annonce(annonce)
        historique.add(annonce["id"])

        if acceptee:
            nouvelles += 1
            if est_marque_prioritaire(annonce["texte_complet"]):
                prioritaires += 1
            message = formater_notification(annonce, analyse)
            print(f"   ✅ ACCEPTÉE — Envoi notification...")
            envoyer_telegram(message)
            if CONFIG["email_actif"]:
                envoyer_email(
                    f"🚗 Voiture trouvée — {annonce['prix']}$",
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
    print(f"   dont {prioritaires} marque(s) prioritaire(s) ⭐")
    print(f"   {len(historique)} annonces dans l'historique total")
    print(f"{'='*60}\n")


def tester_telegram():
    print("📤 Test de notification Telegram...")
    marques = ", ".join(CONFIG["marques_prioritaires"])
    envoyer_telegram(
        "🧪 <b>TEST — Moniteur Auto Montréal</b>\n\n"
        "✅ La connexion Telegram fonctionne!\n"
        f"🔍 Recherche: toutes les voitures ≤ ${CONFIG['prix_max']} / ≤ {CONFIG['km_max']:,} km\n"
        f"⭐ Marques prioritaires: {marques}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


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
