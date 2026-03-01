#!/usr/bin/env python3
"""
SEO Content Pipeline — Main Orchestrator
=========================================
Usage:
  python pipeline.py                            # runs on data/sample_urls.csv (pilot mode)
  python pipeline.py path/to/urls.csv           # custom CSV
  python pipeline.py --full                     # remove 50-URL pilot cap
  python pipeline.py --dry-run                  # skip actual WP publishing

The pipeline:
  1. Loads URLs from a CSV file (column header: "url" or "URL")
  2. Crawls each URL to extract semantic metadata
  3. Assigns each URL to the most relevant editorial hub
  4. Generates keyword clusters by search intent
  5. Samples a stochastic anchor distribution (Dirichlet model)
  6. Generates 3 articles per URL (pillar, commercial, faq)
  7. Schedules publication via Poisson process
  8. Publishes to WordPress (or mocks if no credentials)
  9. Logs everything to SQLite with full idempotency
  10. Exports an HTML monitoring report
"""
import sys
import csv
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Ensure project root is on sys.path before any local imports
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.rule import Rule

from config import DB_PATH, PILOT_MAX_URLS, HUBS, USE_MOCK_LLM, OPENAI_API_KEY, OPENAI_MODEL
from modules.crawler import crawl
from modules.keywords import generate_clusters, check_cannibalization
from modules.content import generate_article
from modules.anchor_model import sample_anchor_distribution, get_anchor_for_article
from modules.monitor import init_db, is_already_processed, is_duplicate_content, log_run, generate_html_report
from modules.publisher import publish_to_wordpress, PublishScheduler

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
console = Console(highlight=False)

ARTICLE_TYPES = ("pillar", "commercial", "faq")
ARTICLE_TYPE_LABELS = {
    "pillar":     "[Pillar]    ",
    "commercial": "[Commercial]",
    "faq":        "[FAQ/AEO]   ",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_urls(csv_path: Path) -> list[str]:
    urls: list[str] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or row.get("URL") or "").strip()
            if url and url.startswith("http"):
                urls.append(url)
    return urls


def assign_hub(theme: str) -> str:
    """Return the hub whose topic list best matches the detected page theme."""
    for hub_id, cfg in HUBS.items():
        if theme in cfg["topics"]:
            return hub_id
    return list(HUBS.keys())[0]


def _extract_brand(title: str) -> str:
    """Pull the brand/site name from the page title."""
    for sep in ["|", "–", "-", "·", ":"]:
        if sep in title:
            return title.split(sep)[-1].strip()[:30]
    return title.strip()[:30] or "Empresa"


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(urls: list[str], dry_run: bool = False, pilot: bool = True) -> list[dict]:
    mode = "PILOT" if pilot else "FULL"
    llm_mode = "MOCK" if USE_MOCK_LLM else f"OpenAI ({OPENAI_MODEL})"

    console.print(Panel.fit(
        f"[bold cyan]SEO Content Pipeline[/bold cyan]\n\n"
        f"  URLs loaded : [white]{len(urls)}[/white]\n"
        f"  Mode        : [yellow]{mode}[/yellow]\n"
        f"  LLM         : [green]{llm_mode}[/green]\n"
        f"  Dry-run     : [magenta]{dry_run}[/magenta]\n"
        f"  DB          : [dim]{DB_PATH}[/dim]",
        border_style="cyan",
        title="Starting",
    ))

    if pilot:
        urls = urls[:PILOT_MAX_URLS]
        console.print(f"[yellow]Pilot cap applied → processing {len(urls)} URLs[/yellow]\n")

    conn = init_db(DB_PATH)
    scheduler = PublishScheduler(lambda_per_week=3.0)
    results: list[dict] = []
    generated_texts: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=28),
        TextColumn("[cyan]{task.completed}/{task.total}[/cyan]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("[cyan]Processing…", total=len(urls))

        for url in urls:
            short_url = url[:55] + ("…" if len(url) > 55 else "")
            progress.update(task, description=f"[cyan]{short_url}")

            # ── Step 1: Crawl ────────────────────────────────────────────────
            crawl_result = crawl(url)
            if not crawl_result.success:
                log_run(conn, url, "all", "error", error=crawl_result.error)
                results.append({"url": url, "status": "crawl_error", "error": crawl_result.error})
                progress.advance(task)
                console.print(f"  [red]✗ Crawl failed:[/red] {crawl_result.error}")
                continue

            # ── Step 2: Hub assignment ───────────────────────────────────────
            hub_id = assign_hub(crawl_result.theme)
            hub_cfg = HUBS[hub_id]
            brand = _extract_brand(crawl_result.title)

            # ── Step 3: Keyword clusters ─────────────────────────────────────
            clusters = generate_clusters(
                crawl_result.theme, crawl_result.title, crawl_result.text_sample
            )
            primary_cluster = clusters[0]
            keywords = {
                "primary":   primary_cluster.primary,
                "secondary": primary_cluster.secondary,
                "long_tail": primary_cluster.long_tail,
            }

            # ── Step 4: Anchor distribution (per-URL Dirichlet draw) ─────────
            anchor_dist = sample_anchor_distribution()

            crawl_data = {
                "theme": crawl_result.theme,
                "title": crawl_result.title,
                "h1":    crawl_result.h1,
                "brand": brand,
            }

            schedule = scheduler.generate_schedule(len(ARTICLE_TYPES))
            url_result: dict = {
                "url":        url,
                "hub":        hub_cfg["name"],
                "theme":      crawl_result.theme,
                "articles":   [],
                "anchor_dist": anchor_dist.to_dict(),
            }

            # ── Step 5: Generate 3 articles ──────────────────────────────────
            for i, article_type in enumerate(ARTICLE_TYPES):

                if is_already_processed(conn, url, article_type):
                    console.print(f"  [dim]↷ {article_type}: already published (idempotency)[/dim]")
                    continue

                anchor_text = get_anchor_for_article(
                    brand, url, keywords["primary"], anchor_dist
                )

                article = generate_article(
                    article_type, crawl_data, keywords,
                    anchor_text, url,
                    use_real_llm=not USE_MOCK_LLM,
                    openai_api_key=OPENAI_API_KEY,
                    openai_model=OPENAI_MODEL,
                )

                if is_duplicate_content(conn, article.content_hash):
                    log_run(conn, url, article_type, "skipped_duplicate",
                            hub=hub_cfg["name"], content_hash=article.content_hash)
                    console.print(f"  [magenta]↷ {article_type}: duplicate content (skipped)[/magenta]")
                    continue

                generated_texts.append(article.content_html)
                scheduled_at = schedule[i].isoformat()

                # ── Step 6: Publish (real or mock) ───────────────────────────
                if not dry_run:
                    pub = publish_to_wordpress(
                        wp_url=hub_cfg.get("wp_url", ""),
                        wp_user=hub_cfg.get("wp_user", ""),
                        wp_password=hub_cfg.get("wp_password", ""),
                        title=article.title,
                        content=article.content_html,
                        schema_json=article.schema_json(),
                        categories=[crawl_result.theme],
                        tags=[keywords["primary"]],
                        scheduled_at=scheduled_at,
                    )
                    status = "published" if pub.success else "error"
                    err = pub.error
                    post_id = pub.post_id or 0
                else:
                    status, err, post_id = "dry_run", "", 0

                log_run(conn, url, article_type, status,
                        hub=hub_cfg["name"], title=article.title,
                        content_hash=article.content_hash,
                        anchor_text=anchor_text,
                        scheduled_at=scheduled_at,
                        error=err, wp_post_id=post_id)

                status_icon = {"published": "OK", "error": "ERR", "dry_run": "DRY"}.get(status, "?")
                status_color = {"published": "green", "error": "red", "dry_run": "blue"}.get(status, "white")
                console.print(
                    f"  [{status_color}]{status_icon}[/{status_color}] "
                    f"[dim]{ARTICLE_TYPE_LABELS[article_type]}[/dim]  "
                    f"[white]{article.title[:60]}[/white]  "
                    f"[dim]anchor=[italic]{anchor_text[:30]}[/italic][/dim]"
                )

                url_result["articles"].append({
                    "type":      article_type,
                    "title":     article.title,
                    "anchor":    anchor_text,
                    "scheduled": scheduled_at,
                    "hash":      article.content_hash,
                    "template":  article.template_used,
                    "status":    status,
                })

            results.append(url_result)
            progress.advance(task)

    # ── Cannibalization check ─────────────────────────────────────────────────
    console.print()
    console.print(Rule("[dim]Post-run analysis[/dim]"))
    if len(generated_texts) >= 2:
        conflicts = check_cannibalization(generated_texts)
        if conflicts:
            console.print(f"[yellow]WARN: {len(conflicts)} potential cannibalization pair(s) detected:[/yellow]")
            for a, b, score in conflicts:
                console.print(f"   Articles #{a} vs #{b}  similarity={score:.3f}")
        else:
            console.print("[green]OK: No cannibalization detected across generated articles.[/green]")

    # ── Summary table ─────────────────────────────────────────────────────────
    _print_summary(results)
    _print_anchor_summary(results)

    # ── HTML report ───────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path("reports") / f"report_{ts}.html"
    generate_html_report(conn, report_path)
    console.print(f"\n[bold green]Report:[/bold green] {report_path.resolve()}")

    conn.close()
    return results


# ── Display helpers ───────────────────────────────────────────────────────────

def _print_summary(results: list[dict]) -> None:
    table = Table(title="Pipeline Summary", header_style="bold cyan", border_style="dim")
    table.add_column("URL",      max_width=44, no_wrap=True)
    table.add_column("Hub",      max_width=22)
    table.add_column("Theme",    max_width=12)
    table.add_column("Articles", justify="center")
    table.add_column("Status")

    for r in results:
        if "articles" not in r:
            table.add_row(r["url"][:44], "-", "-", "0",
                          f"[red]{r.get('status', 'error')}[/red]")
            continue

        arts = r["articles"]
        ok = all(a["status"] in ("published", "dry_run") for a in arts)
        status_str = "[green]OK[/green]" if ok else "[yellow]partial[/yellow]"
        table.add_row(
            r["url"][:44],
            r.get("hub", "—"),
            r.get("theme", "—"),
            str(len(arts)),
            status_str,
        )

    console.print()
    console.print(table)


def _print_anchor_summary(results: list[dict]) -> None:
    total_b = total_e = total_p = total_g = 0.0
    count = 0
    for r in results:
        d = r.get("anchor_dist")
        if d:
            total_b += d["brand"]
            total_e += d["exact_url"]
            total_p += d["partial_match"]
            total_g += d["generic"]
            count += 1
    if not count:
        return

    console.print(Panel(
        f"  Brand:          [cyan]{total_b / count:.1f}%[/cyan]  (target ≈ 30%)\n"
        f"  Exact URL:      [cyan]{total_e / count:.1f}%[/cyan]  (target ≈ 20%)\n"
        f"  Partial match:  [cyan]{total_p / count:.1f}%[/cyan]  (target ≈ 30%)\n"
        f"  Generic:        [cyan]{total_g / count:.1f}%[/cyan]  (target ≈ 20%)\n\n"
        f"  [dim]Sampled via Dirichlet(α=[6,4,6,4]) — {count} URL(s)[/dim]",
        title="[bold]Anchor Distribution Model[/bold]",
        border_style="green",
    ))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SEO Content Pipeline — generates and publishes SEO articles from a URL list."
    )
    parser.add_argument(
        "csv", nargs="?", default="data/sample_urls.csv",
        help="CSV file with a 'url' column (default: data/sample_urls.csv)",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Disable the pilot 50-URL cap and process all URLs",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip WordPress publishing (all other steps run normally)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        console.print(f"[red]Error: CSV not found → {csv_path.resolve()}[/red]")
        sys.exit(1)

    urls = load_urls(csv_path)
    if not urls:
        console.print("[red]No valid URLs found in the CSV.[/red]")
        sys.exit(1)

    console.print(f"[dim]Loaded {len(urls)} URL(s) from {csv_path}[/dim]")
    run_pipeline(urls=urls, dry_run=args.dry_run, pilot=not args.full)


if __name__ == "__main__":
    main()
