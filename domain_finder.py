"""
Domain finder — discover domains associated with companies.

Strategies (in order of reliability):
1. Pappers API (SIREN → website) — most reliable
2. Google search via Serper API — finds real company websites
3. DNS probing on candidate domains — only for multi-word names (avoid false positives)
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

# Generic short words that produce false positive DNS matches
# (e.g. "DOG" → dog.com exists but isn't owned by a small French company)
GENERIC_WORDS = {
    "dog", "cat", "art", "air", "car", "pro", "web", "net", "box",
    "top", "one", "big", "new", "sun", "sky", "red", "blue", "gold",
    "logo", "diva", "star", "film", "tech", "media", "sport", "micro",
    "video", "photo", "audio", "music", "radio", "light", "smart",
    "centre", "central", "comptoir", "liberty", "lumiere", "dominique",
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

    # Strategy 2: Serper (Google search — finds real company websites)
    if use_serper and _serper_key():
        serper_domains = _from_serper(company["name"], company.get("city", ""))
        for d in serper_domains:
            if d not in seen:
                seen.add(d)
                results.append({"domain": d, "source": "serper", "resolves": _dns_check(d)})

    # Strategy 3: DNS probing — only if name is specific enough (avoid false positives)
    name_words = _clean_name_words(company["name"])
    is_generic = len(name_words) == 1 and name_words[0] in GENERIC_WORDS
    is_too_short = len(name_words) == 1 and len(name_words[0]) <= 4

    if not is_generic and not is_too_short:
        candidates = _generate_candidates(company["name"])
        for d in candidates:
            if d not in seen:
                seen.add(d)
                resolves = _dns_check(d)
                if resolves:
                    results.append({"domain": d, "source": "dns_probe", "resolves": True})

    return results


def _clean_name_words(company_name: str) -> list[str]:
    """Extract meaningful words from a company name."""
    name = company_name.lower().strip()
    name = unicode_normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    return [w for w in name.split() if w not in STOP_WORDS and len(w) > 1]


def _generate_candidates(company_name: str) -> list[str]:
    """Generate likely domain names from a company name."""
    words = _clean_name_words(company_name)

    if not words:
        return []

    candidates = []

    # Full name joined with hyphens: "mon-entreprise.fr"
    full_hyphen = "-".join(words)
    # Full name joined: "monentreprise.fr"
    full_joined = "".join(words)
    # First two words hyphenated
    two_words = "-".join(words[:2]) if len(words) >= 2 else None

    base_names = list(filter(None, [full_hyphen, full_joined, two_words]))
    base_names = list(dict.fromkeys(base_names))

    for base in base_names:
        for tld in TLDS:
            candidates.append(f"{base}{tld}")

    return candidates


def _dns_check(domain: str) -> bool:
    """Check if a domain resolves via DNS."""
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

        website = data.get("site_web", "")
        if website:
            domain = _extract_domain(website)
            if domain:
                domains.append(domain)

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

        # Large skip list: directories, aggregators, social media, government, big sites
        skip = [
            # French business directories
            "societe.com", "pappers.fr", "infogreffe.fr", "bodacc.fr",
            "verif.com", "manageo.fr", "societe.ninja", "score3.fr",
            "entreprises.lefigaro.fr", "infonet.fr", "docubiz.fr",
            "lagazettefrance.fr", "e-pro.fr", "dirigeant.societe.com",
            "annuaire-entreprises.data.gouv.fr", "data.gouv.fr",
            "tribunal-de-commerce.fr", "euridile.inpi.fr", "insee.fr",
            "service-public.gouv.fr", "sanitaire-social.com",
            # International directories
            "radaris.com", "trademarkia.com", "opencorporates.com",
            "dnb.com", "crunchbase.com", "zoominfo.com", "kompass.com",
            "ised-isde.canada.ca", "brant.ca",
            # Social media
            "linkedin.com", "facebook.com", "twitter.com", "x.com",
            "instagram.com", "youtube.com", "tiktok.com", "pinterest.com",
            # Big sites (never the company's own domain)
            "google.com", "wikipedia.org", "reddit.com", "amazon.com",
            "linternaute.com", "copainsdavant", "tripadvisor",
            "indeed.com", "glassdoor.com", "pole-emploi.fr",
            "bringfido", "travelnuity", "emmenetonchien",
            "lefigaro.fr", "lemonde.fr", "liberation.fr",
            "b-europe.com", "raileurope.com", "centralesupelec.fr",
            "agroparistech.fr", "idref.fr", "sortiraparis.com",
            "heqco.ca", "visiteurope.com",
            # Yellow pages / maps
            "pagesjaunes.fr", "mappy.com", "yelp.com",
            # Government / health
            "ars.sante.fr", "gouv.fr",
        ]

        for result in data.get("organic", []):
            link = result.get("link", "")
            domain = _extract_domain(link)
            if domain and not any(s in domain for s in skip):
                # Extra check: domain should plausibly belong to this company
                # Skip if it's a subdomain of a known large site
                parts = domain.split(".")
                root = ".".join(parts[-2:]) if len(parts) >= 2 else domain
                if root not in _KNOWN_LARGE_SITES:
                    domains.append(domain)

        return list(set(domains))
    except Exception:
        return []


# Root domains of well-known large sites that are never a small company's domain
_KNOWN_LARGE_SITES = {
    "google.com", "google.fr", "facebook.com", "youtube.com", "twitter.com",
    "linkedin.com", "instagram.com", "reddit.com", "amazon.com", "amazon.fr",
    "wikipedia.org", "lemonde.fr", "lefigaro.fr", "liberation.fr",
    "tripadvisor.com", "tripadvisor.fr", "tripadvisor.com.au",
    "indeed.com", "indeed.fr", "glassdoor.com", "glassdoor.fr",
    "pole-emploi.fr", "francetravail.fr",
    "insee.fr", "gouv.fr", "service-public.fr",
    "pagesjaunes.fr", "mappy.com", "yelp.com", "yelp.fr",
}


def _extract_domain(url: str) -> str | None:
    """Extract bare domain from a URL."""
    url = url.strip().lower()
    for prefix in ["https://", "http://", "www."]:
        url = url.removeprefix(prefix)
    domain = url.split("/")[0].split("?")[0].split("#")[0]
    if "." in domain and len(domain) > 3:
        return domain
    return None
