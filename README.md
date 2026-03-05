# Domain Sourcing Tool

Find expired/expiring domains from French companies in liquidation. Uses the BODACC (open data) to identify companies, then discovers their domains and checks PageRank.

## Pipeline

```
BODACC (liquidations) → Domain Discovery → PageRank Check → WHOIS → Ranked CSV
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Add your API keys to .env
```

### API Keys

| Key | Required | Free? | Source |
|-----|----------|-------|--------|
| `OPENPAGERANK_API_KEY` | Yes | Yes (10k calls/hour) | [openpagerank.com](https://www.domcop.com/openpagerank/) |
| `SERPER_API_KEY` | No | 2500 free queries | [serper.dev](https://serper.dev) |
| `PAPPERS_API_KEY` | No | 100 free credits | [pappers.fr/api](https://www.pappers.fr/api) |

## Usage

```bash
# All sectors, last 90 days
python main.py

# Filter by sector (formation, tech, emploi, conseil)
python main.py --sectors formation tech

# Last 30 days, min PageRank 3
python main.py --days 30 --min-pr 3

# Include WHOIS expiration check (slower)
python main.py --check-whois

# Full pipeline
python main.py --sectors formation tech emploi --days 60 --min-pr 2 --check-whois
```

## Sectors

- **formation**: Formation, enseignement, éducation, coaching, e-learning
- **tech**: Informatique, logiciel, numérique, IA, SaaS, data
- **emploi**: Recrutement, RH, intérim, placement, carrière
- **conseil**: Consulting, audit, stratégie, management

## Output

Results are saved to `output/sourcing_YYYYMMDD_HHMMSS.csv` with columns:
- domain, page_rank, rank, company_name, siren, activity, city, department, region, date, source, resolves, bodacc_url

## Data Sources

- **BODACC** (bodacc.fr) — Official French bulletin for commercial announcements (liquidations, radiations). Free, no API key needed.
- **OpenPageRank** — Free PageRank API (10k calls/hour).
- **Pappers** (optional) — SIREN → website lookup. 100 free credits on signup.
- **Serper** (optional) — Google search to find company websites.
