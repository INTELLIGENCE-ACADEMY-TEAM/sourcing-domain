"""
Free SIREN lookup via annuaire-entreprises.data.gouv.fr API.

100% free, no API key needed, no rate limit published.
Returns company details: NAF code, address, status, creation date, etc.
Does NOT return website URL — use Serper or Pappers for that.
"""

import requests

API_BASE = "https://recherche-entreprises.api.gouv.fr"


def lookup_siren(siren: str) -> dict | None:
    """
    Look up company info by SIREN.

    Returns dict with: name, naf, naf_label, address, status, date_creation, date_fermeture
    """
    if not siren or len(siren.replace(" ", "")) < 9:
        return None

    siren = siren.replace(" ", "")

    try:
        resp = requests.get(
            f"{API_BASE}/search",
            params={"q": siren, "page": 1, "per_page": 1},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        company = results[0]
        siege = company.get("siege", {})

        return {
            "siren": company.get("siren"),
            "name": company.get("nom_complet"),
            "naf_code": company.get("activite_principale"),
            "status": company.get("etat_administratif"),  # A=active, F=fermée
            "date_creation": company.get("date_creation"),
            "date_fermeture": company.get("date_fermeture"),
            "address": siege.get("adresse", ""),
            "postal_code": siege.get("code_postal", ""),
            "city": siege.get("libelle_commune", ""),
            "department": siege.get("departement", ""),
            "is_employer": siege.get("caractere_employeur") == "O",
            "nb_etablissements": company.get("nombre_etablissements", 0),
            "nb_open": company.get("nombre_etablissements_ouverts", 0),
        }
    except Exception:
        return None


def batch_lookup(sirens: list[str]) -> dict[str, dict]:
    """Look up multiple SIRENs. Returns dict mapping SIREN → info."""
    results = {}
    for siren in sirens:
        info = lookup_siren(siren)
        if info:
            results[siren] = info
    return results


# NAF codes relevant to our sectors
FORMATION_NAF = {"8559A", "8559B", "8560Z", "8541Z", "8542Z"}
TECH_NAF = {"6201Z", "6202A", "6202B", "6209Z", "6311Z", "6312Z", "5829A", "5829B", "5829C", "6110Z", "6120Z"}
EMPLOI_NAF = {"7810Z", "7820Z", "7830Z"}
CONSEIL_NAF = {"7022Z", "7021Z", "7010Z", "7311Z", "7312Z", "7320Z"}


def classify_naf(naf_code: str) -> str | None:
    """Classify a NAF code into a sector."""
    if not naf_code:
        return None
    if naf_code in FORMATION_NAF:
        return "formation"
    if naf_code in TECH_NAF:
        return "tech"
    if naf_code in EMPLOI_NAF:
        return "emploi"
    if naf_code in CONSEIL_NAF:
        return "conseil"
    return None


if __name__ == "__main__":
    from rich import print as rprint

    # Test with a known SIREN
    info = lookup_siren("448071449")
    rprint(info)
