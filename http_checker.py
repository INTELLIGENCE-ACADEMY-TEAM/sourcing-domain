"""
HTTP content checker — verify if a domain is alive, parked, or relevant.

Fetches the homepage and analyzes:
- HTTP status (alive, redirect, dead)
- Whether it's a domain parking page
- Page title and language
- Content relevance to the company
"""

import re
import requests

# Patterns indicating a parked/for-sale domain
PARKING_PATTERNS = [
    r"domain.*(for sale|à vendre|is for sale|zum verkauf)",
    r"(buy|acheter|kaufen).*this domain",
    r"domain.*parking",
    r"parked.*domain",
    r"this domain.*available",
    r"ce domaine.*disponible",
    r"domain.*expired",
    r"sedoparking",
    r"hugedomains",
    r"dan\.com",
    r"afternic",
    r"godaddy.*auction",
    r"sav\.com",
    r"domainmarket",
    r"undeveloped",
    r"nom de domaine.*vente",
    r"page par défaut",
    r"default.*page",
    r"coming soon",
    r"under construction",
    r"en construction",
    r"site en maintenance",
    r"403 forbidden",
    r"website.*expired",
]

# Known parking/registrar redirect hosts
PARKING_HOSTS = [
    "sedoparking.com", "parkingcrew.net", "bodis.com",
    "hugedomains.com", "dan.com", "afternic.com",
    "godaddy.com", "namecheap.com", "sav.com",
    "domainmarket.com", "undeveloped.com",
]


def check_http(domain: str, timeout: int = 8) -> dict:
    """
    Check HTTP status and content of a domain.

    Returns:
        Dict with keys: status, http_code, title, is_parked, is_redirect,
                        final_url, language, content_snippet
    """
    url = f"https://{domain}"
    result = {
        "status": "unknown",
        "http_code": None,
        "title": None,
        "is_parked": False,
        "is_redirect": False,
        "final_url": None,
        "language": None,
        "content_length": 0,
    }

    # Try HTTPS first, fallback to HTTP
    for scheme in ["https", "http"]:
        try:
            resp = requests.get(
                f"{scheme}://{domain}",
                timeout=timeout,
                allow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; DomainChecker/1.0)",
                    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                },
            )

            result["http_code"] = resp.status_code
            result["final_url"] = resp.url
            result["content_length"] = len(resp.text)

            # Check if redirected to a different domain
            final_domain = _extract_domain(resp.url)
            if final_domain and final_domain != domain:
                result["is_redirect"] = True
                # Check if redirected to a parking service
                if any(ph in final_domain for ph in PARKING_HOSTS):
                    result["is_parked"] = True

            # Analyze content
            html = resp.text[:10000].lower()  # Only check first 10KB

            # Extract title
            title_match = re.search(r"<title[^>]*>([^<]+)</title>", html)
            if title_match:
                result["title"] = title_match.group(1).strip()[:200]

            # Detect language
            lang_match = re.search(r'<html[^>]*lang="([^"]+)"', html)
            if lang_match:
                result["language"] = lang_match.group(1)

            # Check for parking patterns
            for pattern in PARKING_PATTERNS:
                if re.search(pattern, html, re.IGNORECASE):
                    result["is_parked"] = True
                    break

            # Very short content + no real title = likely parked
            if result["content_length"] < 500 and not result["title"]:
                result["is_parked"] = True

            # Determine status
            if resp.status_code == 200:
                if result["is_parked"]:
                    result["status"] = "parked"
                elif result["is_redirect"]:
                    result["status"] = "redirect"
                else:
                    result["status"] = "alive"
            elif resp.status_code in (301, 302, 307, 308):
                result["status"] = "redirect"
            elif resp.status_code == 403:
                result["status"] = "blocked"
            elif resp.status_code == 404:
                result["status"] = "dead"
            else:
                result["status"] = f"http_{resp.status_code}"

            return result

        except requests.exceptions.SSLError:
            continue  # Try HTTP if HTTPS fails
        except requests.exceptions.ConnectionError:
            result["status"] = "dead"
            return result
        except requests.exceptions.Timeout:
            result["status"] = "timeout"
            return result
        except Exception:
            continue

    result["status"] = "dead"
    return result


def _extract_domain(url: str) -> str | None:
    """Extract domain from URL."""
    url = url.lower()
    for prefix in ["https://", "http://", "www."]:
        url = url.removeprefix(prefix)
    domain = url.split("/")[0].split("?")[0].split("#")[0]
    return domain if "." in domain else None
