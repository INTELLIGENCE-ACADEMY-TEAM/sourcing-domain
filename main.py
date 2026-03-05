#!/usr/bin/env python3
"""
Domain Sourcing Tool — Find expired/expiring domains from French companies in liquidation.

Pipeline:
  1. BODACC API → companies in liquidation judiciaire
  2. Domain discovery (DNS probe + Pappers + Serper)
  3. PageRank check (OpenPageRank API)
  4. WHOIS expiration check
  5. Ranked output → CSV + terminal

Usage:
  python main.py                          # All sectors, last 90 days
  python main.py --sectors formation tech # Filter by sector
  python main.py --days 30                # Last 30 days only
  python main.py --min-pr 3              # Only PR >= 3
  python main.py --check-whois            # Also check WHOIS (slower)
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from bodacc import fetch_liquidations
from domain_finder import find_domains
from pagerank import check_pagerank
from whois_checker import check_whois

load_dotenv()

console = Console()

AVAILABLE_SECTORS = ["formation", "tech", "emploi", "conseil"]


def main():
    parser = argparse.ArgumentParser(description="Source domains from companies in liquidation")
    parser.add_argument("--sectors", nargs="+", choices=AVAILABLE_SECTORS, help="Filter by sector")
    parser.add_argument("--days", type=int, default=90, help="How far back to search (default: 90)")
    parser.add_argument("--max-companies", type=int, default=200, help="Max companies to fetch (default: 200)")
    parser.add_argument("--min-pr", type=int, default=0, help="Minimum PageRank to include (default: 0)")
    parser.add_argument("--check-whois", action="store_true", help="Check WHOIS for each domain (slower)")
    parser.add_argument("--no-serper", action="store_true", help="Disable Google search for domain discovery")
    parser.add_argument("--no-pappers", action="store_true", help="Disable Pappers API for domain discovery")
    parser.add_argument("--output", type=str, default=None, help="Output CSV file path")
    args = parser.parse_args()

    console.print("\n[bold cyan]🔍 Domain Sourcing Tool[/bold cyan]")
    console.print(f"   Sectors: {', '.join(args.sectors) if args.sectors else 'all'}")
    console.print(f"   Period: last {args.days} days")
    console.print(f"   Min PageRank: {args.min_pr}")
    console.print()

    # Step 1: Fetch liquidations from BODACC
    with console.status("[bold green]Fetching liquidations from BODACC..."):
        companies = fetch_liquidations(
            days_back=args.days,
            sectors=args.sectors,
            max_results=args.max_companies,
        )
    console.print(f"[green]✓[/green] Found {len(companies)} companies in liquidation")

    if not companies:
        console.print("[yellow]No companies found. Try broadening your search.[/yellow]")
        return

    # Step 2: Find domains
    all_domains = []
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

    console.print(f"[green]✓[/green] Found {len(all_domains)} candidate domains")

    if not all_domains:
        console.print("[yellow]No domains found. Try with --sectors or increase --days.[/yellow]")
        return

    # Step 3: Check PageRank
    unique_domains = list({d["domain"] for d in all_domains})
    with console.status(f"[bold green]Checking PageRank for {len(unique_domains)} domains..."):
        pr_results = check_pagerank(unique_domains)

    # Merge PageRank into domain results
    for d in all_domains:
        pr = pr_results.get(d["domain"], {})
        d["page_rank"] = pr.get("page_rank", 0)
        d["rank"] = pr.get("rank")

    # Step 4: Optional WHOIS check
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

    # Filter by min PageRank
    if args.min_pr > 0:
        all_domains = [d for d in all_domains if d["page_rank"] >= args.min_pr]

    # Sort by PageRank descending
    all_domains.sort(key=lambda d: d["page_rank"], reverse=True)

    # Display results
    _display_results(all_domains, args.check_whois)

    # Save to CSV
    output_path = args.output or f"output/sourcing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    _save_csv(all_domains, output_path, args.check_whois)
    console.print(f"\n[green]✓[/green] Results saved to [bold]{output_path}[/bold]")


def _display_results(domains: list[dict], show_whois: bool = False):
    """Display results in a rich table."""
    table = Table(title=f"\n🏆 Domain Sourcing Results ({len(domains)} domains)")

    table.add_column("Domain", style="cyan", no_wrap=True)
    table.add_column("PR", justify="center", style="bold")
    table.add_column("Company", style="white", max_width=30)
    table.add_column("Activity", style="dim", max_width=25)
    table.add_column("City", style="dim")
    table.add_column("Source", style="dim")
    table.add_column("DNS", justify="center")
    if show_whois:
        table.add_column("WHOIS", style="dim")
        table.add_column("Expires", style="dim")

    for d in domains[:50]:  # Show top 50
        pr = d["page_rank"]
        pr_style = "bold green" if pr >= 5 else "bold yellow" if pr >= 3 else "dim"
        dns_icon = "✓" if d.get("resolves") else "✗"

        row = [
            d["domain"],
            f"[{pr_style}]{pr}[/{pr_style}]",
            d["company"]["name"][:30],
            (d["company"].get("activity") or "")[:25],
            d["company"].get("city", ""),
            d["source"],
            dns_icon,
        ]
        if show_whois:
            row.append(d.get("whois_status", "?"))
            row.append(d.get("expiration_date", "?") or "?")

        table.add_row(*row)

    console.print(table)

    # Summary
    with_pr = [d for d in domains if d["page_rank"] > 0]
    console.print(f"\n  Domains with PR > 0: {len(with_pr)}")
    if with_pr:
        avg_pr = sum(d["page_rank"] for d in with_pr) / len(with_pr)
        max_pr = max(d["page_rank"] for d in with_pr)
        console.print(f"  Average PR: {avg_pr:.1f}")
        console.print(f"  Max PR: {max_pr}")


def _save_csv(domains: list[dict], path: str, include_whois: bool = False):
    """Save results to CSV."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

    fieldnames = [
        "domain", "page_rank", "rank", "company_name", "siren",
        "activity", "city", "department", "region", "date",
        "source", "resolves", "bodacc_url",
    ]
    if include_whois:
        fieldnames.extend(["whois_status", "expiration_date", "days_until_expiry"])

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for d in domains:
            row = {
                "domain": d["domain"],
                "page_rank": d["page_rank"],
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
            if include_whois:
                row["whois_status"] = d.get("whois_status", "")
                row["expiration_date"] = d.get("expiration_date", "")
                row["days_until_expiry"] = d.get("days_until_expiry", "")
            writer.writerow(row)


if __name__ == "__main__":
    main()
