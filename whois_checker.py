"""
WHOIS checker — check domain expiration and availability.
"""

import whois
from datetime import datetime, timezone


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
            # Make both datetimes naive for comparison
            if exp_date.tzinfo is not None:
                exp_date = exp_date.replace(tzinfo=None)
            days_until = (exp_date - datetime.now()).days

        # Determine status
        if not w.domain_name:
            status = "available"
        elif days_until is not None and days_until < 0:
            status = "expired"
        elif days_until is not None and days_until < 30:
            status = "expiring_soon"
        elif days_until is not None and days_until < 90:
            status = "expiring_3m"
        else:
            status = "active"

        return {
            "registered": bool(w.domain_name),
            "expiration_date": exp_date.strftime("%Y-%m-%d") if isinstance(exp_date, datetime) else None,
            "registrar": w.registrar,
            "days_until_expiry": days_until,
            "status": status,
            "name_servers": w.name_servers if w.name_servers else [],
        }
    except Exception:
        return {
            "registered": None,
            "expiration_date": None,
            "registrar": None,
            "days_until_expiry": None,
            "status": "unknown",
            "name_servers": [],
        }


def batch_check_whois(domains: list[str]) -> dict[str, dict]:
    """Check WHOIS for multiple domains."""
    results = {}
    for domain in domains:
        results[domain] = check_whois(domain)
    return results
