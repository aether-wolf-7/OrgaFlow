"""
Monitoring module: SQLite-based logging, idempotency enforcement,
semantic deduplication, and HTML report generation.

All writes are idempotent: re-running the pipeline on the same URLs
will skip already-published articles without creating duplicates.
"""
import sqlite3
import hashlib
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT    NOT NULL,
    url_hash     TEXT    NOT NULL,
    article_type TEXT    NOT NULL,
    hub          TEXT    DEFAULT '',
    article_title TEXT   DEFAULT '',
    status       TEXT    DEFAULT 'pending',
    content_hash TEXT    DEFAULT '',
    wp_post_id   INTEGER DEFAULT 0,
    anchor_text  TEXT    DEFAULT '',
    scheduled_at TEXT    DEFAULT '',
    error        TEXT    DEFAULT '',
    created_at   TEXT    DEFAULT (datetime('now')),
    UNIQUE(url_hash, article_type)
);

CREATE TABLE IF NOT EXISTS content_hashes (
    hash       TEXT PRIMARY KEY,
    url        TEXT NOT NULL,
    article_type TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.executescript(_DDL)
    conn.commit()
    return conn


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def is_already_processed(conn: sqlite3.Connection, url: str, article_type: str) -> bool:
    """Idempotency: True if this URL+type was already published successfully."""
    cur = conn.execute(
        "SELECT id FROM pipeline_runs WHERE url_hash=? AND article_type=? AND status='published'",
        (_url_hash(url), article_type),
    )
    return cur.fetchone() is not None


def is_duplicate_content(conn: sqlite3.Connection, content_hash: str) -> bool:
    """Dedup: True if identical content was already stored."""
    cur = conn.execute(
        "SELECT hash FROM content_hashes WHERE hash=?", (content_hash,)
    )
    return cur.fetchone() is not None


def log_run(
    conn: sqlite3.Connection,
    url: str,
    article_type: str,
    status: str,
    hub: str = "",
    title: str = "",
    content_hash: str = "",
    anchor_text: str = "",
    scheduled_at: str = "",
    error: str = "",
    wp_post_id: int = 0,
) -> None:
    h = _url_hash(url)
    try:
        conn.execute(
            """
            INSERT INTO pipeline_runs
                (url, url_hash, article_type, hub, article_title, status,
                 content_hash, anchor_text, scheduled_at, error, wp_post_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(url_hash, article_type) DO UPDATE SET
                status        = excluded.status,
                hub           = excluded.hub,
                article_title = excluded.article_title,
                content_hash  = excluded.content_hash,
                anchor_text   = excluded.anchor_text,
                scheduled_at  = excluded.scheduled_at,
                error         = excluded.error,
                wp_post_id    = excluded.wp_post_id
            """,
            (url, h, article_type, hub, title, status,
             content_hash, anchor_text, scheduled_at, error, wp_post_id),
        )
        if status == "published" and content_hash:
            conn.execute(
                "INSERT OR IGNORE INTO content_hashes (hash, url, article_type) VALUES (?,?,?)",
                (content_hash, url, article_type),
            )
        conn.commit()
    except Exception as e:
        logger.error("DB log error: %s", e)


def generate_html_report(conn: sqlite3.Connection, output_path: Path) -> None:
    """Generate a self-contained dark-themed HTML monitoring dashboard."""
    runs = conn.execute(
        """SELECT url, article_type, hub, article_title, status,
                  anchor_text, scheduled_at, created_at, error
           FROM pipeline_runs ORDER BY created_at DESC"""
    ).fetchall()

    stats = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT status, COUNT(*) FROM pipeline_runs GROUP BY status"
        ).fetchall()
    }
    total = sum(stats.values())

    status_color = {"published": "#22c55e", "pending": "#f59e0b",
                    "dry_run": "#3b82f6", "error": "#ef4444",
                    "skipped_duplicate": "#a855f7"}

    rows_html = ""
    for url, atype, hub, atitle, status, anchor, scheduled, created, error in runs:
        color = status_color.get(status, "#6b7280")
        short_url = (url[:45] + "…") if len(url) > 45 else url
        short_title = (atitle[:50] + "…") if atitle and len(atitle) > 50 else (atitle or "—")
        rows_html += f"""
        <tr>
          <td><a href="{url}" target="_blank" style="color:#7eb8f7">{short_url}</a></td>
          <td><span style="background:#1e3a5f;padding:2px 6px;border-radius:4px">{atype}</span></td>
          <td>{hub or "—"}</td>
          <td title="{atitle or ''}">{short_title}</td>
          <td><span style="color:{color};font-weight:600">{status}</span></td>
          <td>{anchor or "—"}</td>
          <td>{scheduled[:10] if scheduled else "—"}</td>
          <td style="color:#ef4444">{error[:60] if error else ""}</td>
        </tr>"""

    stat_cards = ""
    for label, (key, color) in {
        "Total": ("__total__", "#7eb8f7"),
        "Publicados": ("published", "#22c55e"),
        "Pendientes": ("pending", "#f59e0b"),
        "Errores": ("error", "#ef4444"),
    }.items():
        count = total if key == "__total__" else stats.get(key, 0)
        stat_cards += f"""
        <div style="background:#1a1d27;border:1px solid #2d3148;border-radius:8px;
                    padding:20px;text-align:center;flex:1;min-width:120px">
          <div style="font-size:2rem;font-weight:700;color:{color}">{count}</div>
          <div style="color:#9ca3af;font-size:.85rem">{label}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SEO Pipeline — Dashboard</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background:#0f1117; color:#e0e0e0; font-family:system-ui,sans-serif;
            font-size:14px; padding:24px; }}
    h1 {{ color:#7eb8f7; margin-bottom:4px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ padding:8px 10px; text-align:left; border-bottom:1px solid #2d3148; }}
    th {{ background:#1a2035; color:#7eb8f7; font-weight:600; }}
    tr:hover {{ background:#1a1d27; }}
    .card {{ background:#1a1d27; border:1px solid #2d3148; border-radius:8px; overflow:hidden; }}
    .card-header {{ padding:14px 16px; border-bottom:1px solid #2d3148; font-weight:600; color:#c9d1d9; }}
    .table-wrap {{ overflow-x:auto; }}
  </style>
</head>
<body>
  <h1>SEO Pipeline — Dashboard de Monitoreo</h1>
  <p style="color:#6b7280;margin-bottom:24px">
    Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
  </p>

  <div style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap">
    {stat_cards}
  </div>

  <div class="card">
    <div class="card-header">Registro de ejecuciones</div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>URL</th><th>Tipo</th><th>Hub</th><th>Título</th>
            <th>Estado</th><th>Anchor</th><th>Programado</th><th>Error</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </div>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info("Report written to %s", output_path)
