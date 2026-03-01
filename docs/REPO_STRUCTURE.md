# OrgaFlow — Estructura del repositorio y modularidad

Este documento describe la estructura del código y la arquitectura modular del sistema para validación técnica sin acceso al repositorio. Una vez iniciada la asignación en Workana, se otorgará acceso de solo lectura al repositorio real.

---

## Estructura de directorios

```
OrgaFlow/
├── config.py              # Configuración central (env, hubs, límites)
├── pipeline.py            # Orquestador principal — punto de entrada CLI
├── demo_server.py        # Servidor web demo (FastAPI) para ejecución en vivo
├── blueprint.html        # Blueprint arquitectónico (diagrama + documentación)
├── requirements.txt      # Dependencias Python con versiones
├── .env.example          # Plantilla de variables de entorno
│
├── modules/              # Módulos reutilizables (capa de negocio)
│   ├── __init__.py
│   ├── crawler.py        # Crawl HTTP + extracción semántica + detección tema/intención
│   ├── keywords.py       # Clustering de keywords + detección de canibalización (TF-IDF)
│   ├── anchor_model.py   # Modelo Dirichlet de distribución de anchors
│   ├── content.py        # Generación de artículos (3 tipos) + rotación de prompts
│   ├── monitor.py        # SQLite, idempotencia, hashes, reporte HTML
│   └── publisher.py      # Scheduler Poisson + WordPress REST API
│
├── prompts/              # Plantillas de prompts (rotación)
│   ├── pillar.json      # 5 plantillas para artículo pilar
│   ├── commercial.json  # 5 plantillas para artículo comercial
│   └── faq.json         # 5 plantillas para artículo FAQ/AEO
│
├── data/                 # Datos de ejecución (no versionado en prod)
│   ├── sample_urls.csv   # URLs de prueba
│   ├── pipeline.db      # SQLite (piloto) — en prod: PostgreSQL
│   └── demo_input.csv   # Entrada temporal desde la demo web
│
├── reports/              # Reportes HTML generados por ejecución
│   └── report_YYYYMMDD_HHMMSS.html
│
├── docs/                 # Documentación entregable
│   ├── REPO_STRUCTURE.md
│   ├── DEPENDENCIES.md
│   ├── pipeline_run_10urls.log
│   └── (manual operativo, runbook — en entregable final)
│
└── workflows/            # Exportes n8n (producción)
    └── orgaflow_pipeline_export.json
```

---

## Modularidad por capas

| Capa | Archivo(s) | Responsabilidad | Acoplamiento |
|------|------------|-----------------|--------------|
| **Entrada** | `pipeline.py` (load_urls) | Carga CSV, normalización URL, dedup inicial | Solo `config`, sin dependencias de módulos de negocio |
| **Crawl** | `modules/crawler.py` | HTTP request, BeautifulSoup, extracción título/H1/meta/texto, clasificador tema e intención | Entrada: URL. Salida: `CrawlResult` dataclass. Sin estado global. |
| **Routing** | `pipeline.py` (assign_hub) + `config.HUBS` | Asignación hub por tema (keyword match) | Depende de `config.HUBS` y salida del crawler. |
| **Keywords** | `modules/keywords.py` | Keywords principal/secundarias/long-tail, clustering por intención, check canibalización (TF-IDF cosine) | Entrada: `CrawlResult`. Salida: clusters. Reutilizable sin pipeline. |
| **Anchors** | `modules/anchor_model.py` | Muestreo Dirichlet(α=[6,4,6,4]), selección de anchor por tipo (brand/URL/partial/generic) | Entrada: URL + tipo artículo. Salida: anchor text. Stateless. |
| **Contenido** | `modules/content.py` | Generación de 3 artículos (pilar/comercial/faq), rotación de prompts, schema markup, mock o OpenAI | Entrada: CrawlResult + keywords + anchor. Salida: `GeneratedArticle`. Depende de `prompts/*.json`. |
| **Publicación** | `modules/publisher.py` | Fechas Poisson por hub, draft-first, WordPress REST API (o mock) | Entrada: artículo + hub. Sin dependencia de otros módulos de negocio. |
| **Monitoreo** | `modules/monitor.py` | Init DB, idempotencia (url_hash + article_type), content hash, log_run, reporte HTML | Entrada/salida: DB y paths. Usado por orquestador. |

El orquestador (`pipeline.py`) solo encadena llamadas a estos módulos; no contiene lógica de crawl, keywords ni generación. Cada módulo puede testearse o reutilizarse de forma aislada.

---

## Flujo de datos (tipos)

- **CrawlResult** (crawler): `url`, `title`, `meta_description`, `h1`, `text_sample`, `theme`, `intent`, `word_count`, `success`, `error`
- **Clusters** (keywords): listas de keywords principal, secundarias, long-tail por intención
- **GeneratedArticle** (content): `article_type`, `title`, `meta_title`, `meta_description`, `body_html`, `schema_json`, `anchor_text`, etc.
- **PublishScheduler** (publisher): genera `scheduled_at` por artículo con distribución Poisson

La base de datos (`pipeline_runs`, `content_hashes`) es el único estado persistente compartido; los módulos no escriben en disco salvo `monitor` (DB + reportes).

---

## Punto de entrada y uso

- **CLI:** `python pipeline.py [ruta.csv] [--dry-run] [--full]`
- **Demo web:** `python -m uvicorn demo_server:app --host 0.0.0.0 --port 8080` → interfaz en `/`, pipeline en `/run`, reporte en `/report`, blueprint en `/blueprint`

---

## Control de versiones y entregable

- Repositorio Git con historial de commits.
- `requirements.txt` con versiones fijas para reproducibilidad.
- Documentación en `docs/` y `README.md` con quick start, arquitectura y medidas anti-footprint.

Una vez aprobada la asignación, se facilitará acceso de solo lectura al repositorio (GitHub/GitLab privado o export en ZIP con historial) para que puedas revisar el código directamente.
