"""
ExpiredDomains.net scraper — find expired domains by keyword.

Scrapes the public search (no login needed for basic results).
For full features (backlinks, DA), a free account is recommended.
"""

import re
import requests
from urllib.parse import quote_plus

SEARCH_URL = "https://www.expireddomains.net/domain-name-search/"
DELETED_URL = "https://www.expireddomains.net/deleted-domains/"
EXPIRED_URL = "https://www.expireddomains.net/expired-domains/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def search_expired(
    keywords: list[str],
    tlds: list[str] | None = None,
    max_results: int = 100,
) -> list[dict]:
    """
    Search ExpiredDomains.net for expired domains matching keywords.

    Args:
        keywords: Keywords to search for (e.g., ["formation", "ia", "coaching"])
        tlds: Filter by TLD (e.g., [".fr", ".com"]). None = all TLDs.
        max_results: Max domains to return.

    Returns:
        List of dicts: {domain, tld, length, backlinks, end_date, status}
    """
    all_results = []

    for keyword in keywords:
        results = _scrape_search(keyword, tlds, max_results - len(all_results))
        all_results.extend(results)
        if len(all_results) >= max_results:
            break

    # Deduplicate by domain
    seen = set()
    unique = []
    for r in all_results:
        if r["domain"] not in seen:
            seen.add(r["domain"])
            unique.append(r)

    return unique[:max_results]


def _scrape_search(keyword: str, tlds: list[str] | None, limit: int) -> list[dict]:
    """Scrape ExpiredDomains.net search results for a keyword."""
    results = []

    try:
        # Build search URL with filters
        params = {
            "q": keyword,
        }
        if tlds:
            # ExpiredDomains uses ftld parameter for TLD filtering
            tld_str = ",".join(t.lstrip(".") for t in tlds)
            params["ftld"] = tld_str

        session = requests.Session()
        session.headers.update(HEADERS)

        resp = session.get(
            SEARCH_URL,
            params=params,
            timeout=15,
        )

        if resp.status_code != 200:
            return []

        html = resp.text

        # Parse domain rows from the table
        # ExpiredDomains uses a table with class "base1"
        rows = re.findall(
            r'<td class="field_domain">\s*<a[^>]*>([^<]+)</a>',
            html,
        )

        for domain in rows[:limit]:
            domain = domain.strip().lower()
            if "." in domain:
                tld = "." + domain.split(".")[-1]
                results.append({
                    "domain": domain,
                    "tld": tld,
                    "length": len(domain),
                    "source": "expireddomains.net",
                })

    except Exception:
        pass

    return results


def search_deleted_fr(
    keywords: list[str],
    max_results: int = 100,
) -> list[dict]:
    """
    Search specifically for recently deleted .fr domains.

    Uses the deleted domains section filtered by .fr TLD.
    """
    return search_expired(keywords, tlds=[".fr"], max_results=max_results)


# Predefined keyword lists for Intelligence Academy's sectors
FORMATION_KEYWORDS = [
    "formation", "formateur", "coaching", "certifi", "apprentissage",
    "enseignement", "pedagogie", "elearning", "learn", "academy",
    "education", "cours", "stage", "diplome", "competence",
]

TECH_KEYWORDS = [
    "informatique", "digital", "numerique", "tech", "logiciel",
    "software", "data", "cloud", "saas", "startup", "innovation",
    "developpeur", "developer", "coding", "programmation",
]

EMPLOI_KEYWORDS = [
    "emploi", "recrutement", "interim", "carriere", "talent",
    "rh", "ressources-humaines", "job", "travail", "placement",
]


if __name__ == "__main__":
    from rich import print as rprint

    # Test search
    results = search_expired(["formation ia"], tlds=[".fr", ".com"], max_results=10)
    rprint(f"Found {len(results)} expired domains:")
    for r in results:
        rprint(f"  {r['domain']} ({r['source']})")
