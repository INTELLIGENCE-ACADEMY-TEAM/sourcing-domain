#!/usr/bin/env python3
"""
Domain Sourcing Tool — Find expired/expiring domains from French companies in liquidation.

Pipeline:
  1. BODACC API → companies in liquidation judiciaire
  2. Domain discovery (DNS probe + Serper + Pappers)
  3. PageRank check (OpenPageRank API) + DA estimation
  4. HTTP content check (alive/parked/dead)
  5. WHOIS expiration check
  6. Ranked output → CSV + terminal

  Bonus: --expired-domains flag to also search ExpiredDomains.net

Usage:
  python main.py                              # All sectors, last 90 days
  python main.py --sectors formation tech     # Filter by sector
  python main.py --days 30                    # Last 30 days only
  python main.py --min-da 15                  # Only estimated DA >= 15
  python main.py --check-whois                # Also check WHOIS (slower)
  python main.py --check-http                 # Also check if site is alive/parked
  python main.py --expired-domains            # Also search ExpiredDomains.net
  python main.py --full                       # All checks enabled
"""

import argparse
import csv
import os
from datetime import datetime

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from bodacc import fetch_liquidations
from domain_finder import find_domains
from pagerank import check_pagerank
from whois_checker import check_whois
from http_checker import check_http
from expired_domains import search_expired, FORMATION_KEYWORDS, TECH_KEYWORDS, EMPLOI_KEYWORDS

load_dotenv()

console = Console()

AVAILABLE_SECTORS = ["formation", "tech", "emploi", "conseil"]

# PageRank (0-10) → estimated Domain Authority (0-100) mapping
# Based on correlation analysis between PR and Moz DA
PR_TO_DA = {
    0: (0, 10),
    1: (10, 20),
    2: (20, 30),
    3: (30, 40),
    4: (40, 55),
    5: (55, 65),
    6: (65, 75),
    7: (75, 85),
    8: (85, 92),
    9: (92, 97),
    10: (97, 100),
}


def estimate_da(page_rank: int) -> tuple[int, int]:
    """Estimate DA range from PageRank."""
    return PR_TO_DA.get(page_rank, (0, 10))


def main():
    parser = argparse.ArgumentParser(description="Source domains from companies in liquidation")
    parser.add_argument("--sectors", nargs="+", choices=AVAILABLE_SECTORS, help="Filter by sector")
    parser.add_argument("--days", type=int, default=90, help="How far back to search (default: 90)")
    parser.add_argument("--max-companies", type=int, default=200, help="Max companies to fetch (default: 200)")
    parser.add_argument("--min-pr", type=int, default=0, help="Minimum PageRank to include (default: 0)")
    parser.add_argument("--min-da", type=int, default=0, help="Minimum estimated DA to include (default: 0)")
    parser.add_argument("--check-whois", action="store_true", help="Check WHOIS for each domain (slower)")
    parser.add_argument("--check-http", action="store_true", help="Check HTTP status (alive/parked/dead)")
    parser.add_argument("--expired-domains", action="store_true", help="Also search ExpiredDomains.net")
    parser.add_argument("--full", action="store_true", help="Enable all checks (WHOIS + HTTP + ExpiredDomains)")
    parser.add_argument("--no-serper", action="store_true", help="Disable Google search for domain discovery")
    parser.add_argument("--no-pappers", action="store_true", help="Disable Pappers API for domain discovery")
    parser.add_argument("--output", type=str, default=None, help="Output CSV file path")
    args = parser.parse_args()

    # --full enables everything
    if args.full:
        args.check_whois = True
        args.check_http = True
        args.expired_domains = True

    console.print("\n[bold cyan]🔍 Domain Sourcing Tool[/bold cyan]")
    console.print(f"   Sectors: {', '.join(args.sectors) if args.sectors else 'all'}")
    console.print(f"   Period: last {args.days} days")
    console.print(f"   Min DA: {args.min_da}" if args.min_da else f"   Min PR: {args.min_pr}")
    checks = []
    if args.check_whois:
        checks.append("WHOIS")
    if args.check_http:
        checks.append("HTTP")
    if args.expired_domains:
        checks.append("ExpiredDomains.net")
    if checks:
        console.print(f"   Checks: {', '.join(checks)}")
    console.print()

    all_domains = []

    # ── Step 1: Fetch liquidations from BODACC ──
    with console.status("[bold green]Fetching liquidations from BODACC..."):
        companies = fetch_liquidations(
            days_back=args.days,
            sectors=args.sectors,
            max_results=args.max_companies,
        )
    console.print(f"[green]✓[/green] Found {len(companies)} companies in liquidation")

    # ── Step 2: Find domains for each company ──
    if companies:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Finding domains...", total=len(companies))
            for company in companies:
                domains = find_domains(
                    company,
                    use_serper=not args.no_serper,
                    use_pappers=not args.no_pappers,
                )
                for d in domains:
                    d["company"] = company
                all_domains.extend(domains)
                progress.advance(task)

        console.print(f"[green]✓[/green] Found {len(all_domains)} candidate domains from BODACC")

    # ── Step 2b: ExpiredDomains.net (optional) ──
    if args.expired_domains:
        with console.status("[bold green]Searching ExpiredDomains.net..."):
            sector_keywords = []
            sectors = args.sectors or AVAILABLE_SECTORS
            if "formation" in sectors:
                sector_keywords.extend(FORMATION_KEYWORDS[:5])
            if "tech" in sectors:
                sector_keywords.extend(TECH_KEYWORDS[:5])
            if "emploi" in sectors:
                sector_keywords.extend(EMPLOI_KEYWORDS[:5])

            ed_results = search_expired(
                keywords=sector_keywords or ["formation", "digital", "tech"],
                tlds=[".fr", ".com"],
                max_results=100,
            )

        if ed_results:
            for r in ed_results:
                r["company"] = {
                    "name": "(ExpiredDomains.net)",
                    "siren": "",
                    "activity": "",
                    "city": "",
                    "postal_code": "",
                    "date": "",
                    "tribunal": "",
                    "bodacc_url": "",
                    "department": "",
                    "region": "",
                    "original_name": "",
                }
                r["resolves"] = False  # Expired domains typically don't resolve
            all_domains.extend(ed_results)
            console.print(f"[green]✓[/green] Found {len(ed_results)} domains from ExpiredDomains.net")

    if not all_domains:
        console.print("[yellow]No domains found. Try broadening your search.[/yellow]")
        return

    # ── Step 3: Check PageRank + estimate DA ──
    unique_domains = list({d["domain"] for d in all_domains})
    with console.status(f"[bold green]Checking PageRank for {len(unique_domains)} domains..."):
        pr_results = check_pagerank(unique_domains)

    for d in all_domains:
        pr = pr_results.get(d["domain"], {})
        d["page_rank"] = pr.get("page_rank", 0)
        d["rank"] = pr.get("rank")
        da_low, da_high = estimate_da(d["page_rank"])
        d["da_estimate"] = f"{da_low}-{da_high}"
        d["da_low"] = da_low

    # ── Step 4: HTTP content check (optional) ──
    if args.check_http:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Checking HTTP...", total=len(all_domains))
            for d in all_domains:
                http_info = check_http(d["domain"])
                d["http_status"] = http_info["status"]
                d["http_title"] = http_info["title"]
                d["is_parked"] = http_info["is_parked"]
                progress.advance(task)
        console.print(f"[green]✓[/green] HTTP check complete")

    # ── Step 5: WHOIS check (optional) ──
    if args.check_whois:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Checking WHOIS...", total=len(all_domains))
            for d in all_domains:
                whois_info = check_whois(d["domain"])
                d["whois_status"] = whois_info["status"]
                d["expiration_date"] = whois_info["expiration_date"]
                d["days_until_expiry"] = whois_info["days_until_expiry"]
                progress.advance(task)

    # ── Filtering ──
    if args.min_pr > 0:
        all_domains = [d for d in all_domains if d["page_rank"] >= args.min_pr]
    if args.min_da > 0:
        all_domains = [d for d in all_domains if d.get("da_low", 0) >= args.min_da]

    # Sort by PageRank descending
    all_domains.sort(key=lambda d: d["page_rank"], reverse=True)

    # ── Display ──
    _display_results(all_domains, args.check_whois, args.check_http)

    # ── Save CSV ──
    output_path = args.output or f"output/sourcing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    _save_csv(all_domains, output_path, args.check_whois, args.check_http)
    console.print(f"\n[green]✓[/green] Results saved to [bold]{output_path}[/bold]")


def _display_results(domains: list[dict], show_whois: bool = False, show_http: bool = False):
    """Display results in a rich table."""
    table = Table(title=f"\n🏆 Domain Sourcing Results ({len(domains)} domains)")

    table.add_column("Domain", style="cyan", no_wrap=True)
    table.add_column("PR", justify="center")
    table.add_column("DA (est.)", justify="center", style="bold")
    table.add_column("Company", style="white", max_width=25)
    table.add_column("Activity", style="dim", max_width=20)
    table.add_column("Source", style="dim")
    if show_http:
        table.add_column("HTTP", style="dim")
        table.add_column("Title", style="dim", max_width=25)
    if show_whois:
        table.add_column("WHOIS", style="dim")
        table.add_column("Expires", style="dim")

    for d in domains[:50]:
        pr = d["page_rank"]
        da_low = d.get("da_low", 0)
        pr_style = "bold green" if pr >= 4 else "bold yellow" if pr >= 2 else "dim"
        da_style = "bold green" if da_low >= 40 else "bold yellow" if da_low >= 20 else "dim"

        row = [
            d["domain"],
            f"[{pr_style}]{pr}[/{pr_style}]",
            f"[{da_style}]{d.get('da_estimate', '?')}[/{da_style}]",
            d["company"]["name"][:25],
            (d["company"].get("activity") or "")[:20],
            d["source"],
        ]
        if show_http:
            status = d.get("http_status", "?")
            if status == "alive":
                row.append("[green]alive[/green]")
            elif status == "parked":
                row.append("[yellow]parked[/yellow]")
            elif status == "dead":
                row.append("[red]dead[/red]")
            else:
                row.append(status)
            row.append((d.get("http_title") or "")[:25])
        if show_whois:
            ws = d.get("whois_status", "?")
            if ws == "expiring_soon":
                row.append("[red bold]EXPIRING![/red bold]")
            elif ws == "expiring_3m":
                row.append("[yellow]exp. 3m[/yellow]")
            elif ws == "expired":
                row.append("[red]expired[/red]")
            else:
                row.append(ws)
            row.append(d.get("expiration_date", "?") or "?")

        table.add_row(*row)

    console.print(table)

    # Summary
    with_pr = [d for d in domains if d["page_rank"] > 0]
    console.print(f"\n  Total domains: {len(domains)}")
    console.print(f"  Domains with PR > 0: {len(with_pr)}")
    if with_pr:
        avg_pr = sum(d["page_rank"] for d in with_pr) / len(with_pr)
        max_pr = max(d["page_rank"] for d in with_pr)
        console.print(f"  Average PR: {avg_pr:.1f} | Max PR: {max_pr}")

    # Highlight interesting finds
    if show_http:
        parked = [d for d in domains if d.get("is_parked")]
        dead = [d for d in domains if d.get("http_status") == "dead"]
        if parked:
            console.print(f"  [yellow]Parked domains: {len(parked)}[/yellow] (potential purchase targets)")
        if dead:
            console.print(f"  [red]Dead domains: {len(dead)}[/red] (may be dropping soon)")

    if show_whois:
        expiring = [d for d in domains if d.get("whois_status") in ("expiring_soon", "expiring_3m")]
        expired = [d for d in domains if d.get("whois_status") == "expired"]
        if expiring:
            console.print(f"  [red bold]Expiring soon: {len(expiring)}[/red bold]")
            for d in expiring:
                console.print(f"    → {d['domain']} (PR={d['page_rank']}, expires {d.get('expiration_date', '?')})")
        if expired:
            console.print(f"  [red]Already expired: {len(expired)}[/red]")
            for d in expired:
                console.print(f"    → {d['domain']} (PR={d['page_rank']})")


def _save_csv(domains: list[dict], path: str, include_whois: bool = False, include_http: bool = False):
    """Save results to CSV."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

    fieldnames = [
        "domain", "page_rank", "da_estimate", "rank", "company_name", "siren",
        "activity", "city", "department", "region", "date",
        "source", "resolves", "bodacc_url",
    ]
    if include_http:
        fieldnames.extend(["http_status", "http_title", "is_parked"])
    if include_whois:
        fieldnames.extend(["whois_status", "expiration_date", "days_until_expiry"])

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for d in domains:
            row = {
                "domain": d["domain"],
                "page_rank": d["page_rank"],
                "da_estimate": d.get("da_estimate", ""),
                "rank": d.get("rank", ""),
                "company_name": d["company"]["name"],
                "siren": d["company"]["siren"],
                "activity": d["company"].get("activity", ""),
                "city": d["company"].get("city", ""),
                "department": d["company"].get("department", ""),
                "region": d["company"].get("region", ""),
                "date": d["company"].get("date", ""),
                "source": d["source"],
                "resolves": d.get("resolves", ""),
                "bodacc_url": d["company"].get("bodacc_url", ""),
            }
            if include_http:
                row["http_status"] = d.get("http_status", "")
                row["http_title"] = d.get("http_title", "")
                row["is_parked"] = d.get("is_parked", "")
            if include_whois:
                row["whois_status"] = d.get("whois_status", "")
                row["expiration_date"] = d.get("expiration_date", "")
                row["days_until_expiry"] = d.get("days_until_expiry", "")
            writer.writerow(row)


if __name__ == "__main__":
    main()
