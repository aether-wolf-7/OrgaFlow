# OrgaFlow — Dependencias externas (APIs, servicios, proveedores)

Documento de referencia para la capa operativa del sistema. Todas las dependencias externas están concentradas aquí; el código usa variables de entorno (`.env`) y no incluye claves ni datos sensibles.

---

## 1. APIs externas

| Dependencia | Uso en el sistema | Requerido | Configuración | Coste / límites |
|-------------|-------------------|-----------|---------------|-----------------|
| **OpenAI API** | Generación de artículos (pilar, comercial, FAQ) cuando no se usa modo mock | No (opcional en piloto) | `OPENAI_API_KEY`, `OPENAI_MODEL` (default: `gpt-4o-mini`) en `.env` | ~USD 0.01–0.03 por artículo según modelo; límites según cuenta OpenAI |
| **WordPress REST API** | Publicación de artículos en cada hub (crear post como borrador) | Sí (en producción) | Por hub: `HUBn_WP_URL`, `HUBn_WP_USER`, `HUBn_WP_PASSWORD` (Application Password) en `.env` | Sin coste; límites por servidor WP |
| **Google Search Console API** | (Producción) Métricas de indexación, impresiones, CTR para dashboard y triggers de rollback | Opcional | OAuth2 o Service Account; documentado en runbook de producción | Sin coste; cuotas estándar de Google APIs |
| **Google Sheets API** | (Producción) Entrada de URLs desde hoja de cálculo en lugar de CSV | Opcional | OAuth2 o Service Account; integración vía n8n o script | Sin coste; cuotas estándar |

---

## 2. Servicios y runtimes

| Servicio | Uso | Requerido | Notas |
|----------|-----|-----------|--------|
| **Python 3.11+** | Ejecución del pipeline y del servidor demo | Sí | Recomendado 3.11 o 3.12; probado con 3.13 |
| **SQLite** | Base de datos en piloto/demo (persistencia de runs, idempotencia, content hashes) | Sí (piloto) | Incluido en Python; archivo `data/pipeline.db` |
| **PostgreSQL** | Base de datos en producción (reemplazo de SQLite para concurrencia y Metabase) | Sí (producción) | Cliente: `psycopg2` o `asyncpg`; no incluido en `requirements.txt` del piloto |
| **n8n** | Orquestación en producción: programación de ejecuciones, lectura de Sheets, llamadas al backend, colas por hub | Sí (producción) | Self-hosted o n8n Cloud; workflow export en `workflows/orgaflow_pipeline_export.json` |
| **Metabase** | Dashboard de monitoreo (indexación, CTR, anchors, logs, anomalías) sobre PostgreSQL | Sí (producción) | Self-hosted o Metabase Cloud; conexión solo a PostgreSQL |

---

## 3. Librerías y paquetes Python (pip)

Todas las dependencias están en `requirements.txt` con versiones. Resumen por propósito:

| Paquete | Versión | Uso |
|---------|---------|-----|
| requests | 2.31.0 | HTTP para crawl y WordPress REST API |
| beautifulsoup4 | 4.12.3 | Parseo HTML en crawler |
| lxml | 5.3.0 | Parser XML/HTML rápido para BS4 |
| numpy | ≥2.0.0 | Modelo Dirichlet (anchors) |
| pandas | ≥2.2.0 | Carga de CSV y manipulación de lotes |
| scikit-learn | ≥1.5.0 | TF-IDF y similitud coseno (canibalización) |
| python-dotenv | 1.0.1 | Carga de `.env` |
| rich | 13.7.1 | Salida en consola (tablas, progreso, paneles) |
| openai | ≥1.12.0 | Cliente OpenAI para generación de contenido |
| fastapi | ≥0.110.0 | Servidor demo (API y SSE) |
| uvicorn | ≥0.27.0 | Servidor ASGI para FastAPI |

No se usan APIs de terceros dentro del código salvo OpenAI y WordPress; el resto son librerías estándar o de código abierto.

---

## 4. Infraestructura por hub (producción)

Cada hub tiene configuración independiente. Los proveedores son solo sugerencias; el cliente puede sustituirlos.

| Recurso | Proveedores de ejemplo | Configuración |
|---------|------------------------|---------------|
| Hosting / VPS | SiteGround, DigitalOcean, Kinsta, OVHcloud, Linode (uno distinto por hub) | URL del sitio en `HUBn_WP_URL` |
| DNS | Cloudflare, Namecheap, Porkbun, Dynadot, etc. (uno distinto por hub) | Nameservers en el registrador del dominio |
| Dominio | Cualquier registrador (uno por hub) | Dominio apuntando al hosting del hub |
| WordPress | Instalación estándar en cada hosting | Tema y plugins distintos por hub (ver blueprint) |

No hay dependencia de un único proveedor; el sistema está pensado para diversificación (ASN/DNS distintos) según el documento de arquitectura.

---

## 5. Proxies (escalado)

| Recurso | Uso | Cuándo |
|---------|-----|--------|
| Proxies residenciales (rotación) | Crawl de URLs a gran escala para evitar bloqueos y dispersar origen | Fase de escalado (cientos/miles de URLs); no obligatorio en piloto |

Configuración típica vía variables de entorno o parámetros del módulo `crawler` (ej. `HTTP_PROXY`, `HTTPS_PROXY` o integración en n8n). Proveedores: Bright Data, Oxylabs, Smartproxy, etc.; coste variable por GB o por sesión.

---

## 6. Resumen: qué necesita el cliente para operar

- **Piloto (20–50 URLs):** Python, `requirements.txt`, `.env` con opcional `OPENAI_API_KEY` y credenciales de 1 WordPress (hub piloto). Sin PostgreSQL ni n8n obligatorios.
- **Producción (2.000+ URLs):** Todo lo anterior + PostgreSQL, n8n, Metabase, 5 hostings/DNS/dominios (uno por hub), opcional Google Sheets y GSC API, opcional servicio de proxies.

Ninguna dependencia externa está embebida en el código con valores por defecto sensibles; todo se inyecta por entorno o por configuración documentada.
