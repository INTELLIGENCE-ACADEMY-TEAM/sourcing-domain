"""
BODACC API client — fetch companies in liquidation judiciaire.

Uses the free OpenDataSoft API from bodacc-datadila.
"""

import json
import requests
from datetime import datetime, timedelta

API_BASE = "https://bodacc-datadila.opendatasoft.com/api/records/1.0/search/"
DATASET = "annonces-commerciales"

# NAF-related keywords to filter by sector
SECTOR_KEYWORDS = {
    "formation": [
        "formation", "enseignement", "éducation", "pédagog", "apprentissage",
        "coaching", "academy", "école", "institut", "learning", "training",
        "certifi", "diplôm",
    ],
    "tech": [
        "informatique", "logiciel", "développ", "numérique", "digital",
        "technolog", "data", "intelligence artificielle", "ia ", " ai ",
        "saas", "cloud", "cyber", "web", "software", "startup", "tech",
        "innovation", "automatisation", "robot",
    ],
    "emploi": [
        "recrutement", "emploi", "ressources humaines", "rh ", "intérim",
        "placement", "carrière", "compétence", "talent", "staffing",
        "travail temporaire", "conseil rh",
    ],
    "conseil": [
        "conseil", "consulting", "consultant", "audit", "stratégie",
        "management", "accompagnement", "expertise",
    ],
}


def fetch_liquidations(
    days_back: int = 90,
    sectors: list[str] | None = None,
    max_results: int = 500,
) -> list[dict]:
    """
    Fetch recent liquidation announcements from BODACC.

    Args:
        days_back: How far back to search (default 90 days)
        sectors: List of sector keys to filter (formation, tech, emploi, conseil)
                 If None, fetches all liquidations.
        max_results: Maximum number of results to return.

    Returns:
        List of company dicts with keys: name, siren, activity, city, date, tribunal, bodacc_url
    """
    date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    params = {
        "dataset": DATASET,
        "q": "liquidation judiciaire",
        "rows": min(max_results, 100),  # API max is 100 per page
        "sort": "-dateparution",
        "where": f"dateparution >= '{date_from}'",
    }

    all_records = []
    offset = 0

    while len(all_records) < max_results:
        params["start"] = offset
        params["rows"] = min(100, max_results - len(all_records))

        resp = requests.get(API_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        records = data.get("records", [])
        if not records:
            break

        all_records.extend(records)
        offset += len(records)

        if offset >= data.get("nhits", 0):
            break

    companies = []
    for record in all_records:
        fields = record.get("fields", {})
        company = _parse_record(fields)
        if company:
            companies.append(company)

    # Filter by sector keywords if specified
    if sectors:
        keywords = []
        for sector in sectors:
            keywords.extend(SECTOR_KEYWORDS.get(sector, []))
        if keywords:
            companies = _filter_by_keywords(companies, keywords)

    return companies


def _parse_record(fields: dict) -> dict | None:
    """Parse a BODACC record into a clean company dict."""
    name = fields.get("commercant", "")
    if not name:
        return None

    # Clean up company name (remove " (société en liquidation)" suffix)
    clean_name = name.split("(")[0].strip()

    # Extract SIREN from registre field
    registre = fields.get("registre", "")
    siren = registre.replace(" ", "").split(",")[0] if registre else ""

    # Try to extract activity from listepersonnes JSON
    activity = ""
    lp = fields.get("listepersonnes", "")
    if lp:
        try:
            lp_data = json.loads(lp) if isinstance(lp, str) else lp
            personne = lp_data.get("personne", {})
            activity = personne.get("activite", "")
        except (json.JSONDecodeError, AttributeError):
            pass

    return {
        "name": clean_name,
        "original_name": name,
        "siren": siren,
        "activity": activity,
        "city": fields.get("ville", ""),
        "postal_code": fields.get("cp", ""),
        "date": fields.get("dateparution", ""),
        "tribunal": fields.get("tribunal", ""),
        "bodacc_url": fields.get("url_complete", ""),
        "department": fields.get("numerodepartement", ""),
        "region": fields.get("region_nom_officiel", ""),
    }


def _filter_by_keywords(companies: list[dict], keywords: list[str]) -> list[dict]:
    """Filter companies by sector keywords in name or activity."""
    filtered = []
    for company in companies:
        searchable = f"{company['name']} {company['activity']}".lower()
        if any(kw.lower() in searchable for kw in keywords):
            filtered.append(company)
    return filtered


if __name__ == "__main__":
    # Quick test
    from rich import print as rprint

    companies = fetch_liquidations(days_back=30, sectors=["formation", "tech"], max_results=50)
    rprint(f"Found {len(companies)} companies in liquidation (formation + tech)")
    for c in companies[:10]:
        rprint(f"  - {c['name']} ({c['siren']}) — {c['city']} — {c['activity'] or 'N/A'}")
