# SEO Content Pipeline — Demo

Proof-of-concept for a scalable SEO content generation and editorial hub
distribution system. Demonstrates the core architecture before full
production deployment.

---

## What this demo proves

| Capability | Implementation |
|---|---|
| Automated URL crawling | `requests` + `BeautifulSoup`, semantic theme/intent detection |
| Hub assignment | Topic-keyword matching across 5 thematic hubs |
| Keyword clustering | Intent-based clusters (informacional / comercial / local) |
| Anchor distribution model | Dirichlet(α=[6,4,6,4]) stochastic sampling per URL |
| Cannibalization detection | TF-IDF cosine similarity with configurable threshold |
| Prompt rotation | 5 weighted templates per article type (15 total) |
| Content generation | Mock (default) or real OpenAI with schema markup |
| Schema markup | Article / FAQPage / HowTo per article type |
| Publication scheduling | Poisson process (λ=3/week) with business-hour bias |
| Idempotency | SQLite deduplication — re-running never re-publishes |
| Content deduplication | SHA-256 hash registry — identical content blocked |
| WordPress publishing | REST API with draft-first safety flow (mock if no creds) |
| HTML monitoring report | Auto-generated dark-theme dashboard with full log |

---

## Quick start (no API keys needed)

```bash
# 1. Clone / download the demo folder
cd demo

# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment config (leave blank = mock mode)
copy .env.example .env

# 5. Run on the included sample URLs
python pipeline.py

# 6. Open the generated HTML report
#    reports/report_YYYYMMDD_HHMMSS.html
```

---

## Running with your own URLs

Create a CSV with at minimum a `url` column:

```csv
url,brand,notes
https://yourdomain.com/,Brand Name,optional notes
```

Then run:

```bash
python pipeline.py path/to/your_urls.csv
python pipeline.py path/to/your_urls.csv --dry-run   # skip publishing
python pipeline.py path/to/your_urls.csv --full       # remove 50-URL cap
```

---

## Enabling real content generation (OpenAI)

Edit `.env`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Cost estimate: ~$0.01–0.03 per article at gpt-4o-mini pricing.

---

## Connecting WordPress hubs

Edit `.env`:

```env
HUB1_WP_URL=https://hub-negocios.com
HUB1_WP_USER=admin
HUB1_WP_PASSWORD=your-application-password
```

WordPress → Users → Application Passwords to generate the password.
Articles are published as **draft** by default for human review.

---

## Project structure

```
demo/
├── pipeline.py          ← Main orchestrator (run this)
├── config.py            ← Central config from .env
├── requirements.txt
├── .env.example
├── modules/
│   ├── crawler.py       ← HTTP crawl + semantic extraction
│   ├── keywords.py      ← Keyword clustering + cannibalization check
│   ├── content.py       ← Article generation with prompt rotation
│   ├── anchor_model.py  ← Dirichlet anchor distribution model
│   ├── monitor.py       ← SQLite logging, dedup, HTML report
│   └── publisher.py     ← WordPress REST API + Poisson scheduler
├── prompts/
│   ├── pillar.json      ← 5 pillar article templates
│   ├── commercial.json  ← 5 commercial article templates
│   └── faq.json         ← 5 FAQ/AEO templates
├── data/
│   └── sample_urls.csv  ← Demo URLs (replace with yours)
└── reports/
    └── *.html           ← Auto-generated monitoring reports
```

---

## Architecture overview

```
CSV / Google Sheets
        │
        ▼
  [Crawler] ─── HTTP + BeautifulSoup ──→ CrawlResult
        │            (theme, intent, title, text)
        ▼
  [Hub Router] ──── topic matching ────→ hub_id
        │
        ▼
  [Keyword Generator] ─ intent clusters ─→ primary / secondary / long-tail
        │
        ▼
  [Anchor Model] ─── Dirichlet sample ──→ AnchorDistribution
        │
        ▼
  [Content Generator] ─ prompt rotation → 3 × GeneratedArticle
        │                (pillar, commercial, faq)
        │                + schema markup (Article / FAQPage)
        ▼
  [Publisher] ──── Poisson schedule ────→ WordPress REST API (draft)
        │
        ▼
  [Monitor] ──── SQLite + hash check ───→ idempotency + HTML report
```

---

## Scaling to 2,000+ sites

The demo processes URLs sequentially for simplicity.
Production version uses:

- **n8n** workflow with parallel branches per hub (or Celery for Python-native)
- **Randomized batch ordering** — no sequential processing that creates
  temporal correlation patterns
- **Per-hub rate limits** — 2–4 posts/week, never simultaneous across hubs
- **Residential proxy rotation** for crawling at scale
- **PostgreSQL** instead of SQLite for concurrent access

Full n8n workflow JSON export is included in the production deliverable.

---

## Anti-footprint measures in this demo

1. **Separate infrastructure per hub** — documented in Infrastructure Manifest
2. **Dirichlet anchor model** — each URL gets a different distribution draw;
   aggregate profile matches organic backlink patterns
3. **Poisson scheduling** — publication times are statistically independent
   across hubs; no burst patterns visible in GSC crawl logs
4. **Prompt rotation** — 15 templates × variable injection = no two articles
   share structural fingerprint; monthly template rotation in production
5. **Draft-first publishing** — human review layer before any article goes live

---

## Rollback protocol

If GSC shows ranking drops >20% across ≥3 articles from the same hub
within 7 days, the production system:
1. Automatically pauses that hub's publication queue
2. Sets scheduled articles back to draft
3. Sends alert to the dashboard
4. Operator investigates and approves resume from dashboard

Manual override available in <2 minutes via the monitoring dashboard.
