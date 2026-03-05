"""
Domain finder — discover domains associated with companies.

Strategies:
1. Generate candidate domains from company name
2. DNS resolution check
3. Optional: Google search via Serper API
4. Optional: Pappers API (SIREN → website)
"""

import os
import re
import socket
import requests
from unicodedata import normalize as unicode_normalize

def _serper_key():
    return os.getenv("SERPER_API_KEY")

def _pappers_key():
    return os.getenv("PAPPERS_API_KEY")

TLDS = [".fr", ".com", ".io", ".tech", ".org", ".net"]

# Words to strip from company names when generating domain candidates
STOP_WORDS = {
    "sarl", "sas", "sa", "eurl", "sasu", "sci", "snc", "scp",
    "société", "societe", "ste", "groupe", "group", "holding",
    "france", "paris", "lyon", "international", "europe",
    "le", "la", "les", "de", "du", "des", "et", "en", "au", "aux",
}


def find_domains(company: dict, use_serper: bool = True, use_pappers: bool = True) -> list[dict]:
    """
    Find domains associated with a company.

    Returns list of dicts: {domain, source, resolves}
    """
    results = []
    seen = set()

    # Strategy 1: Pappers API (most reliable — gives actual website)
    if use_pappers and _pappers_key() and company.get("siren"):
        pappers_domains = _from_pappers(company["siren"])
        for d in pappers_domains:
            if d not in seen:
                seen.add(d)
                results.append({"domain": d, "source": "pappers", "resolves": _dns_check(d)})

    # Strategy 2: Generate candidates from company name
    candidates = _generate_candidates(company["name"])
    for d in candidates:
        if d not in seen:
            seen.add(d)
            resolves = _dns_check(d)
            if resolves:
                results.append({"domain": d, "source": "dns_probe", "resolves": True})

    # Strategy 3: Google search via Serper (if we found nothing yet)
    if use_serper and _serper_key() and not results:
        serper_domains = _from_serper(company["name"], company.get("city", ""))
        for d in serper_domains:
            if d not in seen:
                seen.add(d)
                results.append({"domain": d, "source": "serper", "resolves": _dns_check(d)})

    return results


def _generate_candidates(company_name: str) -> list[str]:
    """Generate likely domain names from a company name."""
    # Normalize and clean
    name = company_name.lower().strip()
    name = unicode_normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")

    # Remove special chars
    name = re.sub(r"[^a-z0-9\s-]", "", name)

    # Split into words and remove stop words
    words = [w for w in name.split() if w not in STOP_WORDS and len(w) > 1]

    if not words:
        return []

    candidates = []

    # Full name joined with hyphens: "mon-entreprise.fr"
    full_hyphen = "-".join(words)
    # Full name joined: "monentreprise.fr"
    full_joined = "".join(words)
    # First word only if multi-word: "mon.fr"
    first_word = words[0] if len(words[0]) > 3 else None
    # First two words: "mon-entreprise.fr"
    two_words = "-".join(words[:2]) if len(words) >= 2 else None

    base_names = list(filter(None, [full_hyphen, full_joined, first_word, two_words]))
    # Deduplicate while preserving order
    base_names = list(dict.fromkeys(base_names))

    for base in base_names:
        for tld in TLDS:
            candidates.append(f"{base}{tld}")

    return candidates


def _dns_check(domain: str) -> bool:
    """Check if a domain resolves via DNS."""
    # Skip domains with labels too long (max 63 chars per label, 253 total)
    if len(domain) > 253 or any(len(part) > 63 for part in domain.split(".")):
        return False
    try:
        socket.setdefaulttimeout(3)
        socket.getaddrinfo(domain, 80)
        return True
    except (socket.gaierror, socket.timeout, OSError, UnicodeError):
        return False


def _from_pappers(siren: str) -> list[str]:
    """Look up company website via Pappers API."""
    try:
        resp = requests.get(
            "https://api.pappers.fr/v2/entreprise",
            params={"api_token": _pappers_key(), "siren": siren},
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()

        domains = []
        # Pappers returns site_web field
        website = data.get("site_web", "")
        if website:
            domain = _extract_domain(website)
            if domain:
                domains.append(domain)

        # Also check etablissements for websites
        for etab in data.get("etablissements", []):
            site = etab.get("site_web", "")
            if site:
                domain = _extract_domain(site)
                if domain:
                    domains.append(domain)

        return list(set(domains))
    except Exception:
        return []


def _from_serper(company_name: str, city: str = "") -> list[str]:
    """Search Google for the company website via Serper API."""
    try:
        query = f'"{company_name}"'
        if city:
            query += f" {city}"
        query += " site officiel"

        resp = requests.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": _serper_key(),
                "Content-Type": "application/json",
            },
            json={"q": query, "gl": "fr", "hl": "fr", "num": 5},
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        domains = []

        for result in data.get("organic", []):
            link = result.get("link", "")
            domain = _extract_domain(link)
            if domain:
                # Skip known aggregator sites
                skip = ["societe.com", "pappers.fr", "infogreffe.fr", "bodacc.fr",
                         "verif.com", "annuaire-entreprises.data.gouv.fr",
                         "pagesjaunes.fr", "linkedin.com", "facebook.com"]
                if not any(s in domain for s in skip):
                    domains.append(domain)

        return list(set(domains))
    except Exception:
        return []


def _extract_domain(url: str) -> str | None:
    """Extract bare domain from a URL."""
    url = url.strip().lower()
    # Remove protocol
    for prefix in ["https://", "http://", "www."]:
        url = url.removeprefix(prefix)
    # Get domain part
    domain = url.split("/")[0].split("?")[0].split("#")[0]
    if "." in domain and len(domain) > 3:
        return domain
    return None


if __name__ == "__main__":
    from rich import print as rprint

    test_company = {"name": "DIGITAL ACADEMY", "siren": "", "city": "Paris"}
    domains = find_domains(test_company, use_serper=False, use_pappers=False)
    rprint(f"Candidates for '{test_company['name']}':")
    for d in domains:
        rprint(f"  {'✓' if d['resolves'] else '✗'} {d['domain']} ({d['source']})")
