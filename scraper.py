#!/usr/bin/env python3
"""
🚗 Moniteur de voitures — Kijiji & Craigslist
Cherche automatiquement des voitures à bon prix autour de Montréal
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
import unicodedata
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

CONFIG = {
    "prix_max": 3000,
    "prix_min": 300,
    "km_max": 140000,
    "annee_max": 2019,          # rejette 2020+
    "rayon_km": 200,

    "marques_prioritaires": ["toyota", "honda", "hyundai"],

    "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),

    "email_actif": False,
    "email_expediteur": os.environ.get("EMAIL_FROM", ""),
    "email_mot_de_passe": os.environ.get("EMAIL_PASSWORD", ""),
    "email_destinataire": os.environ.get("EMAIL_TO", ""),
    "email_smtp": "smtp.gmail.com",
    "email_port": 587,
}

# ═══════════════════════════════════════════════════════════════
# PROBLÈMES MAJEURS (rejet) vs MINEURS (accepté)
# ═══════════════════════════════════════════════════════════════

PROBLEMES_MAJEURS = [
    r"transmission\s+(a\s+changer|finie|brisee|morte|slip|patine)",
    r"moteur\s+(a\s+changer|brule|mort|fini|grippe|seized|blown)",
    r"engine\s+(blown|seized|knock|replacement)",
    r"\bhead\s+gasket\b", r"joint\s+de\s+culasse",
    r"accident\s+majeur", r"major\s+accident",
    r"\btotal\s+loss\b", r"perte\s+totale",
    r"\bsalvage\b", r"\breconstruit\b", r"rebuilt\s+title",
    r"flood\s+damage", r"dommage.{0,15}inondation",
    r"frame\s+(rust|damage|rot|bend)", r"chassis\s+(rouille|endommage|plie)",
    r"sous-?cadre\s+(pourri|rouille|perce)",
    r"subframe\s+(rust|rot|hole)",
    r"timing\s+(chain|belt)\s+(broke|broken|snapped)",
    r"chaine\s+de\s+distribution\s+(brisee|cassee)",
    r"catalytic\s+converter\s+(stolen|missing)",
    r"catalyseur\s+(vole|manquant)",
    r"ne\s+(roule|demarre|part)\s+(plus|pas)",
    r"does\s+not\s+(run|start|drive)",
    r"non\s+roulable", r"not\s+drivable", r"not\s+running",
    r"pour\s+(pieces|les\s+pieces|la\s+scrap)", r"for\s+parts",
    r"\bscrap\b", r"\bferraille\b",
    r"turbo\s+(mort|fini|blown)",
    r"\boverheat", r"\bsurchauffe\b",
    r"rod\s+knock", r"\bcognement\b",
    r"cracked\s+block", r"bloc\s+(fissure|craque)",
]

PROBLEMES_MINEURS = [
    r"egratignure", r"\bscratch", r"eraflure",
    r"bosse\s+mineur", r"small\s+dent", r"minor\s+dent", r"petite\s+bosse",
    r"a/?c\s+(ne\s+fonctionne|broken|not\s+working|a\s+recharger)",
    r"air\s+climatise", r"climatisation",
    r"window\s+(regulator|motor)", r"leve-?vitre",
    r"\bradio\b", r"\bspeaker", r"haut-?parleur",
    r"cosmetique", r"cosmetic",
    r"peinture\s+(ecaillee|usee)", r"paint\s+(chip|fade|peel)",
    r"rust\s+(minor|surface|small|spot)", r"rouille\s+(mineur|surface|legere|petite)",
    r"brake\s+(pad|rotor)", r"freins\s+a\s+(faire|changer)",
    r"plaquettes", r"disques\s+de\s+frein",
    r"pneus?\s+(a\s+changer|use|worn)", r"tires?\s+(worn|need)",
    r"exhaust\s+(leak|small)",
    r"\bmuffler\b", r"silencieux",
    r"check\s+engine\s+light", r"lumiere\s+moteur",
    r"\bsensor\b", r"\bcapteur\b",
    r"\bbattery\b", r"\bbatterie\b",
    r"\balternator\b", r"\balternateur\b",
    r"\bstarter\b", r"\bdemarreur\b",
    r"tie\s+rod", r"ball\s+joint", r"\brotule\b",
    r"\bbearing\b", r"\broulement\b",
    r"suspension\s+(usee|worn|bruit|noise)",
    r"\bstrut\b", r"amortisseur", r"\bshock\b",
    r"alignment", r"alignement",
]

# ═══════════════════════════════════════════════════════════════
# FILTRES CONCESSIONNAIRE
# Séparés en deux niveaux pour éviter les faux positifs.
# ═══════════════════════════════════════════════════════════════

# Appliqués partout (titre + description) — sans ambiguïté
CONCESSIONNAIRE_STRICT = [
    r"\bconcessionnaire\b", r"\bdealership\b",
    r"certified\s+pre.owned", r"vehicule\s+certifie",
    r"financement\s+disponible", r"financing\s+available",
    r"garantie\s+prolongee", r"extended\s+warranty",
    r"venez\s+nous\s+voir", r"come\s+visit\s+us",
    r"notre\s+inventaire", r"our\s+inventory",
    r"appelez[- ]nous", r"call\s+us\s+today",
    r"\bcarfax\b", r"\bcarproof\b",
    r"groupe\s+auto\b", r"\bauto\s+group\b",
    r"motors?\s+(inc|ltd|ltee|enr)\b",
    r"autos?\s+(inc|ltd|ltee|enr)\b",
    r"\bkm\s+garantis?\b",
    r"plusieurs\s+vehicules?\s+(en\s+)?(stock|inventaire)",
]

# Appliqués UNIQUEMENT au titre + courte description de la liste.
# Jamais au texte complet de la page: chaque page Kijiji contient
# "kijiji.ca" et "www." dans son menu, ce qui rejetterait tout.
CONCESSIONNAIRE_URL = [
    r"www\.", r"\.com\b", r"\.ca\b",
    r"\bdealer\b", r"\bautotrader\b",
]

NON_VOITURE = [
    r"\bmoto\b", r"\bmotorcycle\b", r"\bscooter\b",
    r"\bvtt\b", r"\batv\b", r"\bquad\b",
    r"\bbateau\b", r"\bboat\b",
    r"\bmotoneige\b", r"\bsnowmobile\b",
    r"\bremorque\b", r"\btrailer\b",
    r"camion\s+lourd", r"heavy\s+truck",
    r"\bpieces?\s+d[e']", r"\bparts\s+for\b",
    r"\bjante", r"\brims?\s+for\b",
    r"\bmags?\s+(pour|for)\b",
    r"\bpneus?\s+a\s+vendre\b", r"\btires?\s+for\s+sale\b",
    r"^pneus?\b", r"^tires?\b", r"^roues?\b", r"^wheels?\b",
    r"\bpneus?\s+d.(hiver|ete)\b", r"\bwinter\s+tires?\b",
    r"\bset\s+of\s+\d\s+(tires?|rims?|wheels?)\b",
    r"\b4\s+pneus\b", r"\bbanc\s+de\s+char\b", r"\bsieges?\s+auto\b",
]

# ═══════════════════════════════════════════════════════════════
# HISTORIQUE
# ═══════════════════════════════════════════════════════════════

HISTORIQUE_PATH = Path(__file__).parent / "annonces_vues.json"


def charger_historique() -> set:
    if HISTORIQUE_PATH.exists():
        try:
            with open(HISTORIQUE_PATH, "r") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            print("⚠️  Historique illisible, on repart à zéro")
    return set()


def sauvegarder_historique(historique: set):
    try:
        with open(HISTORIQUE_PATH, "w") as f:
            json.dump(sorted(historique), f)
    except OSError as e:
        print(f"⚠️  Impossible de sauvegarder l'historique: {e}")


# ═══════════════════════════════════════════════════════════════
# DÉTECTION DE MARQUE
# ═══════════════════════════════════════════════════════════════

MARQUES_CONNUES = {
    "toyota": ["toyota", "camry", "corolla", "rav4", "yaris", "matrix", "prius", "echo", "tercel", "celica", "solara", "avalon", "venza", "sienna", "tacoma", "tundra", "highlander", "4runner", "sequoia"],
    "honda": ["honda", "civic", "accord", "crv", "cr-v", "hrv", "hr-v", "insight", "prelude", "odyssey", "ridgeline"],
    "hyundai": ["hyundai", "elantra", "sonata", "accent", "tucson", "santa fe", "veloster", "kona", "tiburon"],
    "nissan": ["nissan", "sentra", "altima", "versa", "maxima", "rogue", "pathfinder", "murano", "frontier", "juke"],
    "mazda": ["mazda", "mazda3", "mazda 3", "mazda6", "mazda 6", "cx-5", "cx5", "cx-3", "miata", "protege", "tribute"],
    "subaru": ["subaru", "impreza", "outback", "forester", "legacy", "wrx", "crosstrek"],
    "kia": ["kia", "forte", "rio", "optima", "sportage", "sorento", "spectra", "magentis"],
    "volkswagen": ["volkswagen", "jetta", "passat", "tiguan", "beetle"],
    "ford": ["ford", "focus", "fusion", "fiesta", "escape", "explorer", "mustang", "taurus", "f-150", "f150"],
    "chevrolet": ["chevrolet", "chevy", "cruze", "malibu", "impala", "equinox", "cobalt", "cavalier", "aveo", "optra"],
    "mitsubishi": ["mitsubishi", "lancer", "outlander", "eclipse", "rvr", "mirage"],
    "dodge": ["dodge", "caravan", "grand caravan", "avenger", "neon", "journey"],
    "pontiac": ["pontiac", "vibe", "sunfire", "grand prix", "grand am", "g5", "g6"],
    "saturn": ["saturn", "astra"],
    "suzuki": ["suzuki", "sx4", "aerio", "vitara"],
    "acura": ["acura", "integra", "rsx", "tsx", "csx"],
    "volvo": ["volvo"],
    "bmw": ["bmw"],
    "audi": ["audi"],
    "mercedes": ["mercedes", "benz"],
    "buick": ["buick", "allure", "lacrosse", "century"],
    "chrysler": ["chrysler", "sebring", "300", "pt cruiser"],
    "jeep": ["jeep", "cherokee", "wrangler", "liberty", "compass", "patriot"],
}


def detecter_marque(texte: str):
    """Détecte la marque. Cherche d'abord le nom de marque, puis les modèles."""
    texte_lower = normaliser(texte)

    # Priorité au nom de marque explicite
    for marque in MARQUES_CONNUES:
        if re.search(rf"\b{re.escape(marque)}\b", texte_lower):
            return marque

    # Sinon on cherche par modèle
    for marque, mots_cles in MARQUES_CONNUES.items():
        for mot in mots_cles[1:]:
            if re.search(rf"\b{re.escape(mot)}\b", texte_lower):
                return marque
    return None


def est_marque_prioritaire(texte: str) -> bool:
    return detecter_marque(texte) in CONFIG["marques_prioritaires"]


# ═══════════════════════════════════════════════════════════════
# EXTRACTION
# ═══════════════════════════════════════════════════════════════


def normaliser(texte: str) -> str:
    """
    Minuscules + suppression des accents.
    Beaucoup de vendeurs écrivent sans accents ("transmission a changer"),
    donc on normalise des deux côtés pour que les patterns matchent quand même.
    """
    if not texte:
        return ""
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def analyser_problemes(texte: str) -> dict:
    texte_lower = normaliser(texte)
    majeurs, mineurs = [], []

    for pattern in PROBLEMES_MAJEURS:
        m = re.search(pattern, texte_lower)
        if m:
            majeurs.append(m.group().strip())

    for pattern in PROBLEMES_MINEURS:
        m = re.search(pattern, texte_lower)
        if m:
            mineurs.append(m.group().strip())

    return {
        "majeurs": majeurs,
        "mineurs": mineurs,
        "verdict": "REJETÉ" if majeurs else "ACCEPTÉ",
    }


def extraire_km(texte: str):
    if not texte:
        return None
    t = texte.lower()

    for pattern, is_mile in [
        (r"([\d][\d,.\s]{2,})\s*km", False),
        (r"([\d][\d,.\s]{2,})\s*kilo", False),
        (r"([\d][\d,.\s]{2,})\s*miles?\b", True),
    ]:
        for m in re.finditer(pattern, t):
            nombre = re.sub(r"[,.\s]", "", m.group(1))
            try:
                km = int(nombre)
            except ValueError:
                continue
            if is_mile:
                km = int(km * 1.60934)
            if 1000 < km < 900000:
                return km
    return None


def extraire_prix(texte: str):
    if not texte:
        return None
    t = texte.lower()

    for pattern in [r"\$\s*([\d][\d,.\s]*)", r"([\d][\d,.\s]*)\s*\$", r"([\d][\d,.\s]*)\s*dollars?"]:
        for m in re.finditer(pattern, t):
            nombre = re.sub(r"[,.\s]", "", m.group(1))
            try:
                prix = int(nombre)
            except ValueError:
                continue
            if 100 <= prix <= 50000:
                return prix
    return None


def extraire_annee(texte: str):
    if not texte:
        return None
    annees = [int(a) for a in re.findall(r"\b(19[89]\d|20[0-2]\d)\b", texte)]
    annee_courante = datetime.now().year
    valides = [a for a in annees if 1980 <= a <= annee_courante + 1]
    return valides[0] if valides else None


# ═══════════════════════════════════════════════════════════════
# SCRAPERS
# ═══════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def chercher_kijiji() -> list:
    annonces = []
    prix_max = CONFIG["prix_max"]
    km_max = CONFIG["km_max"]
    rayon = CONFIG["rayon_km"]

    url = (
        f"https://www.kijiji.ca/b-autos-camions/grand-montreal/k0c174l80002"
        f"?price=__${prix_max}"
        f"&kilometers=__{km_max}km"
        f"&sort=dateDesc"
        f"&radius={rayon}.0"
        f"&address=Montr%C3%A9al%2C+QC"
    )

    print(f"🔍 Kijiji (rayon {rayon} km): {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.select("[data-listing-id]")
        if not items:
            items = soup.select("li.search-item, div.search-item")
        if not items:
            items = soup.select("[data-testid='listing-card']")

        print(f"   → {len(items)} annonces sur la page")

        for item in items:
            try:
                a = parser_annonce_kijiji(item)
                if a:
                    annonces.append(a)
            except Exception as e:
                print(f"   ⚠️ parsing: {e}")

    except requests.RequestException as e:
        print(f"❌ Erreur Kijiji: {e}")

    return annonces


def parser_annonce_kijiji(item):
    titre_el = item.select_one(
        "a.title, h3 a, [data-testid='listing-title'] a, a[class*='title'], h3"
    )
    if not titre_el:
        return None

    titre = titre_el.get_text(strip=True)
    if not titre:
        return None

    lien = titre_el.get("href", "")
    if not lien:
        parent_a = item.select_one("a[href*='/v-']")
        lien = parent_a.get("href", "") if parent_a else ""
    if lien and not lien.startswith("http"):
        lien = "https://www.kijiji.ca" + lien

    prix_el = item.select_one(".price, [class*='price'], [data-testid='listing-price']")
    prix_texte = prix_el.get_text(strip=True) if prix_el else ""
    prix = extraire_prix(prix_texte)

    desc_el = item.select_one(".description, [class*='description']")
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    km = None
    for attr in item.select("[class*='attribute'], [class*='detail']"):
        km = extraire_km(attr.get_text(" ", strip=True))
        if km:
            break
    if km is None:
        km = extraire_km(f"{titre} {description}")

    listing_id = item.get("data-listing-id") or (
        hashlib.md5(lien.encode()).hexdigest()[:12] if lien else None
    )
    if not listing_id:
        return None

    return {
        "id": f"kijiji_{listing_id}",
        "source": "Kijiji",
        "titre": titre,
        "prix": prix,
        "km": km,
        "lien": lien,
        "description": description,
        # Texte court: titre + desc courte. Sert aux filtres URL.
        "texte_court": f"{titre} {description}",
    }


def chercher_craigslist() -> list:
    annonces = []
    prix_max = CONFIG["prix_max"]

    url = (
        f"https://montreal.craigslist.org/search/cta"
        f"?max_price={prix_max}&sort=date"
    )

    print(f"🔍 Craigslist: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.select(
            "li.cl-static-search-result, .result-row, li.cl-search-result"
        )
        print(f"   → {len(items)} annonces")

        vus = set()
        for item in items:
            try:
                titre_el = item.select_one(
                    "a.titlestring, a.posting-title, a[class*='title']"
                )
                if not titre_el:
                    titre_el = item.select_one("a[href*='/cto/'], a[href*='/ctd/']")
                if not titre_el:
                    continue

                titre = titre_el.get_text(strip=True)
                lien = titre_el.get("href", "")
                if not titre or not lien:
                    continue
                if not lien.startswith("http"):
                    lien = "https://montreal.craigslist.org" + lien

                if lien in vus:
                    continue
                vus.add(lien)

                prix_el = item.select_one(
                    ".priceinfo, .result-price, [class*='price']"
                )
                prix = extraire_prix(prix_el.get_text(strip=True) if prix_el else "")

                meta_el = item.select_one(".meta, .result-meta")
                meta = meta_el.get_text(" ", strip=True) if meta_el else ""
                km = extraire_km(f"{titre} {meta}")

                listing_id = hashlib.md5(lien.encode()).hexdigest()[:12]

                annonces.append({
                    "id": f"craigslist_{listing_id}",
                    "source": "Craigslist",
                    "titre": titre,
                    "prix": prix,
                    "km": km,
                    "lien": lien,
                    "description": meta,
                    "texte_court": f"{titre} {meta}",
                })

            except Exception as e:
                print(f"   ⚠️ parsing: {e}")

    except requests.RequestException as e:
        print(f"❌ Erreur Craigslist: {e}")

    return annonces


# ═══════════════════════════════════════════════════════════════
# DÉTAILS D'UNE ANNONCE
# ═══════════════════════════════════════════════════════════════


def obtenir_details(annonce: dict) -> str:
    """
    Récupère la vraie description de l'annonce.
    Retourne "" si on ne trouve pas le bloc description — on ne retombe
    JAMAIS sur le texte complet de la page, car les menus/pieds de page
    de Kijiji contiennent 'kijiji.ca', 'www.', etc. et déclencheraient
    à tort le filtre concessionnaire.
    """
    if not annonce.get("lien"):
        return ""

    try:
        time.sleep(1)
        resp = requests.get(annonce["lien"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for sel in [
            "[class*='descriptionContainer']",
            "[itemprop='description']",
            "div[class*='vip-body']",
            "#postingbody",
        ]:
            el = soup.select_one(sel)
            if el:
                texte = el.get_text(" ", strip=True)
                if len(texte) > 20:
                    return texte[:4000]

        return ""

    except Exception as e:
        print(f"   ⚠️ détails indisponibles: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════


def envoyer_telegram(message: str):
    token = CONFIG["telegram_bot_token"]
    chat_id = CONFIG["telegram_chat_id"]

    if not token or not chat_id:
        print("⚠️  Telegram non configuré — affichage console")
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
        print("   ✅ Notification envoyée")
    except requests.RequestException as e:
        print(f"   ❌ Erreur Telegram: {e}")


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
            print("   ✅ Email envoyé")
    except Exception as e:
        print(f"   ❌ Erreur email: {e}")


def echapper_html(texte: str) -> str:
    """Échappe les caractères qui casseraient le parse_mode HTML de Telegram."""
    return (texte.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;"))


def formater_notification(annonce: dict, analyse: dict) -> str:
    prix = f"${annonce['prix']:,}" if annonce["prix"] else "Prix non indiqué"
    km = f"{annonce['km']:,} km" if annonce["km"] else "KM non indiqué"

    mineurs_uniques = list(dict.fromkeys(analyse.get("mineurs", [])))[:5]
    mineurs = ", ".join(mineurs_uniques) if mineurs_uniques else "Aucun détecté"

    texte = annonce["texte_court"]
    marque = detecter_marque(texte)
    marque_display = marque.upper() if marque else "AUTRE"
    annee = extraire_annee(annonce["titre"])
    annee_display = str(annee) if annee else "?"

    prioritaire = est_marque_prioritaire(texte)
    etoile = "⭐ " if prioritaire else ""

    titre_safe = echapper_html(annonce["titre"])
    mineurs_safe = echapper_html(mineurs)

    return (
        f"🚗 <b>{etoile}NOUVELLE ANNONCE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{titre_safe}</b>\n"
        f"🏷️ {marque_display} | Année: {annee_display}\n"
        f"💰 Prix: <b>{prix}</b>\n"
        f"📏 Kilométrage: <b>{km}</b>\n"
        f"📍 Source: {annonce['source']}\n"
        f"🔧 Problèmes mineurs: {mineurs_safe}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 {annonce['lien']}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


# ═══════════════════════════════════════════════════════════════
# FILTRAGE
# ═══════════════════════════════════════════════════════════════


def chercher_patterns(patterns, texte):
    """Retourne le premier pattern qui matche, ou None."""
    for p in patterns:
        m = re.search(p, texte)
        if m:
            return m.group().strip()
    return None


def filtrer_annonce(annonce: dict):
    """Retourne (acceptée: bool, infos: dict)."""

    # 1. Prix obligatoire
    if annonce["prix"] is None:
        return False, {"raison": "Aucun prix indiqué"}

    if annonce["prix"] > CONFIG["prix_max"]:
        return False, {"raison": f"Prix trop élevé: ${annonce['prix']}"}

    if annonce["prix"] < CONFIG["prix_min"]:
        return False, {"raison": f"Prix suspect: ${annonce['prix']}"}

    # 2. Kilométrage
    if annonce["km"] and annonce["km"] > CONFIG["km_max"]:
        return False, {"raison": f"Trop de km: {annonce['km']:,}"}

    texte_court = normaliser(annonce["texte_court"])

    # 3. Année
    annee = extraire_annee(annonce["titre"])
    if annee and annee > CONFIG["annee_max"]:
        return False, {"raison": f"Trop récente ({annee})"}

    # 4. Pas une voiture
    hit = chercher_patterns(NON_VOITURE, texte_court)
    if hit:
        return False, {"raison": f"Pas une voiture ({hit})"}

    # 4b. Une vraie annonce de voiture a soit une marque reconnue, soit une année.
    #     Sans les deux, c'est presque toujours un accessoire ou une pièce.
    if not detecter_marque(annonce["texte_court"]) and not annee:
        return False, {"raison": "Ni marque ni année identifiée"}

    # 5. Concessionnaire — patterns URL sur le texte COURT seulement
    hit = chercher_patterns(CONCESSIONNAIRE_URL, texte_court)
    if hit:
        return False, {"raison": f"Concessionnaire ({hit})"}

    # 6. Concessionnaire — patterns stricts sur le texte court
    hit = chercher_patterns(CONCESSIONNAIRE_STRICT, texte_court)
    if hit:
        return False, {"raison": f"Concessionnaire ({hit})"}

    # 7. Description complète
    details = obtenir_details(annonce)
    texte_complet = f"{annonce['texte_court']} {details}"

    # Sur la vraie description: patterns stricts uniquement
    hit = chercher_patterns(CONCESSIONNAIRE_STRICT, normaliser(details))
    if hit:
        return False, {"raison": f"Concessionnaire dans description ({hit})"}

    # 8. Problèmes majeurs
    analyse = analyser_problemes(texte_complet)
    if analyse["verdict"] == "REJETÉ":
        return False, analyse

    # 9. Km trouvé dans les détails
    if annonce["km"] is None and details:
        km = extraire_km(details)
        if km:
            annonce["km"] = km
            if km > CONFIG["km_max"]:
                return False, {"raison": f"Trop de km: {km:,}"}

    return True, analyse


# ═══════════════════════════════════════════════════════════════
# EXÉCUTION
# ═══════════════════════════════════════════════════════════════


def executer():
    print(f"\n{'='*60}")
    print(f"🚗 Moniteur Auto — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Prix: ${CONFIG['prix_min']}–${CONFIG['prix_max']} | "
          f"KM max: {CONFIG['km_max']:,} | Année ≤ {CONFIG['annee_max']}")
    print(f"   Rayon: {CONFIG['rayon_km']} km autour de Montréal")
    print(f"   ⭐ Prioritaires: {', '.join(CONFIG['marques_prioritaires'])}")
    print(f"{'='*60}\n")

    historique = charger_historique()
    nouvelles = 0
    prioritaires = 0
    rejets = {}

    toutes = []
    toutes.extend(chercher_kijiji())
    time.sleep(2)
    toutes.extend(chercher_craigslist())

    # Dédoublonnage par id
    vues = set()
    uniques = []
    for a in toutes:
        if a["id"] not in vues:
            vues.add(a["id"])
            uniques.append(a)

    print(f"\n📊 {len(uniques)} annonces uniques récupérées")

    nouvelles_a_traiter = [a for a in uniques if a["id"] not in historique]
    print(f"   dont {len(nouvelles_a_traiter)} jamais vues\n")

    for annonce in nouvelles_a_traiter:
        print(f"🔎 {annonce['titre'][:55]}")

        acceptee, infos = filtrer_annonce(annonce)
        historique.add(annonce["id"])

        if acceptee:
            nouvelles += 1
            if est_marque_prioritaire(annonce["texte_court"]):
                prioritaires += 1
            message = formater_notification(annonce, infos)
            print(f"   ✅ ACCEPTÉE")
            envoyer_telegram(message)
            if CONFIG["email_actif"]:
                envoyer_email(f"🚗 Voiture — {annonce['prix']}$",
                              message.replace("\n", "<br>"))
            time.sleep(1)
        else:
            raison = infos.get("raison", "")
            if infos.get("majeurs"):
                raison = f"Problème majeur: {infos['majeurs'][0]}"
            cle = raison.split(":")[0].split("(")[0].strip()
            rejets[cle] = rejets.get(cle, 0) + 1
            print(f"   ❌ {raison}")

    sauvegarder_historique(historique)

    print(f"\n{'='*60}")
    print(f"✅ {nouvelles} annonce(s) envoyée(s), dont {prioritaires} ⭐")
    if rejets:
        print(f"\n   Rejets par catégorie:")
        for r, n in sorted(rejets.items(), key=lambda x: -x[1]):
            print(f"     {n:3}× {r}")
    print(f"\n   {len(historique)} annonces en historique")
    print(f"{'='*60}\n")


def tester_telegram():
    print("📤 Test Telegram...")
    marques = ", ".join(CONFIG["marques_prioritaires"])
    envoyer_telegram(
        "🧪 <b>TEST — Moniteur Auto Montréal</b>\n\n"
        "✅ Connexion Telegram fonctionnelle\n"
        f"🔍 Voitures ≤ ${CONFIG['prix_max']} / ≤ {CONFIG['km_max']:,} km\n"
        f"📍 Rayon {CONFIG['rayon_km']} km autour de Montréal\n"
        f"⭐ Prioritaires: {marques}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


if __name__ == "__main__":
    if "--test" in sys.argv:
        tester_telegram()
    elif "--reset" in sys.argv:
        if HISTORIQUE_PATH.exists():
            HISTORIQUE_PATH.unlink()
            print("🗑️  Historique effacé")
        else:
            print("ℹ️  Pas d'historique")
    else:
        executer()
