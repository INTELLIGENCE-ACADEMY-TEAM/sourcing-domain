"""
WHOIS checker — check domain expiration and availability.
"""

import whois
from datetime import datetime


def check_whois(domain: str) -> dict:
    """
    Check WHOIS data for a domain.

    Returns:
        Dict with keys: registered, expiration_date, registrar, days_until_expiry, status
    """
    try:
        w = whois.whois(domain)

        # Handle expiration date (can be a list or single value)
        exp_date = w.expiration_date
        if isinstance(exp_date, list):
            exp_date = exp_date[0]

        days_until = None
        if exp_date and isinstance(exp_date, datetime):
            days_until = (exp_date - datetime.now()).days

        # Determine status
        if not w.domain_name:
            status = "available"
        elif days_until is not None and days_until < 0:
            status = "expired"
        elif days_until is not None and days_until < 30:
            status = "expiring_soon"
        else:
            status = "active"

        return {
            "registered": bool(w.domain_name),
            "expiration_date": exp_date.isoformat() if exp_date else None,
            "registrar": w.registrar,
            "days_until_expiry": days_until,
            "status": status,
            "name_servers": w.name_servers if w.name_servers else [],
        }
    except whois.parser.PywhoisError:
        return {
            "registered": False,
            "expiration_date": None,
            "registrar": None,
            "days_until_expiry": None,
            "status": "available",
            "name_servers": [],
        }
    except Exception as e:
        return {
            "registered": None,
            "expiration_date": None,
            "registrar": None,
            "days_until_expiry": None,
            "status": "error",
            "error": str(e),
            "name_servers": [],
        }


def batch_check_whois(domains: list[str]) -> dict[str, dict]:
    """Check WHOIS for multiple domains."""
    results = {}
    for domain in domains:
        results[domain] = check_whois(domain)
    return results


if __name__ == "__main__":
    from rich import print as rprint

    test = ["google.com", "xyznotexist12345.fr", "expired-test-domain.com"]
    for domain in test:
        info = check_whois(domain)
        rprint(f"  {domain}: {info['status']} — expires: {info['expiration_date']} — registrar: {info['registrar']}")
