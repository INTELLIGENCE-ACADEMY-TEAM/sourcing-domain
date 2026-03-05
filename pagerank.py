"""
OpenPageRank API client — check PageRank for domains.

API: https://openpagerank.com/api/v1.0/getPageRank
Rate limit: 10,000 calls/hour, max 100 domains per call.
"""

import os
import requests

API_URL = "https://openpagerank.com/api/v1.0/getPageRank"


def _get_api_key():
    key = os.getenv("OPENPAGERANK_API_KEY")
    if not key:
        raise ValueError("OPENPAGERANK_API_KEY not set in environment")
    return key


def check_pagerank(domains: list[str]) -> dict[str, dict]:
    """
    Check PageRank for a list of domains.

    Args:
        domains: List of domain names (max 100 per call)

    Returns:
        Dict mapping domain → {page_rank, rank, status}
    """

    results = {}

    # Process in batches of 100
    for i in range(0, len(domains), 100):
        batch = domains[i : i + 100]
        batch_results = _fetch_batch(batch)
        results.update(batch_results)

    return results


def _fetch_batch(domains: list[str]) -> dict[str, dict]:
    """Fetch PageRank for a batch of up to 100 domains."""
    params = [("domains[]", d) for d in domains]

    resp = requests.get(
        API_URL,
        params=params,
        headers={"API-OPR": _get_api_key()},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    results = {}
    for entry in data.get("response", []):
        domain = entry.get("domain", "")
        results[domain] = {
            "page_rank": entry.get("page_rank_integer", 0),
            "page_rank_decimal": entry.get("page_rank_decimal", 0),
            "rank": entry.get("rank"),
            "found": entry.get("status_code") == 200,
        }

    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    from rich import print as rprint

    load_dotenv()

    test_domains = ["google.com", "lemonde.fr", "openclassrooms.com", "the-intelligence-academy.com"]
    results = check_pagerank(test_domains)
    for domain, info in results.items():
        status = "✓" if info["found"] else "✗"
        rprint(f"  {status} {domain}: PR={info['page_rank']} (rank #{info['rank']})")
