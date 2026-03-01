"""
Content generation with prompt rotation and structured schema markup.

Supports two modes:
  - MOCK (default, no API key): generates fully structured articles with
    correct HTML, schema markup, H1–H3 hierarchy, and internal/external links.
  - REAL: calls OpenAI with a randomly selected prompt template.

Template selection uses weighted random sampling to prevent detectable patterns.
After generation, a SHA-256 hash is computed for deduplication.
"""
import json
import random
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

ARTICLE_TYPES = ("pillar", "commercial", "faq")

EXTERNAL_LINKS = [
    ("Google Search Central", "https://developers.google.com/search/docs"),
    ("Schema.org", "https://schema.org/"),
    ("Moz Learn SEO", "https://moz.com/learn/seo"),
    ("Ahrefs Blog", "https://ahrefs.com/blog/"),
    ("Search Engine Journal", "https://www.searchenginejournal.com/"),
]


@dataclass
class GeneratedArticle:
    article_type: str
    title: str
    meta_title: str
    meta_description: str
    h1: str
    content_html: str
    schema_markup: dict
    keywords_used: list = field(default_factory=list)
    anchor_text: str = ""
    target_url: str = ""
    template_used: str = ""
    content_hash: str = ""

    def __post_init__(self):
        raw = f"{self.title}||{self.content_html}"
        self.content_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def schema_json(self) -> str:
        return json.dumps(self.schema_markup, ensure_ascii=False, indent=2)


# ── Template loading ─────────────────────────────────────────────────────────

def _load_templates(article_type: str) -> list:
    path = PROMPTS_DIR / f"{article_type}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["templates"]


def _select_template(templates: list) -> dict:
    """Weighted random selection — prevents uniform frequency patterns."""
    weights = [t.get("weight", 1.0) for t in templates]
    return random.choices(templates, weights=weights, k=1)[0]


# ── Mock HTML builders ───────────────────────────────────────────────────────

def _ext_link() -> tuple:
    return random.choice(EXTERNAL_LINKS)


def _mock_pillar(title: str, keyword: str, anchor: str, url: str, tone: str) -> str:
    ext_name, ext_url = _ext_link()
    return f"""<h1>{keyword.capitalize()}: guía completa para profesionales</h1>

<p>En el entorno actual, <strong>{keyword}</strong> representa uno de los pilares
clave para cualquier estrategia de crecimiento sostenible. Esta guía reúne lo
esencial para que puedas implementarlo con resultados medibles.</p>

<h2>¿Qué es {keyword}?</h2>
<p>{keyword.capitalize()} es un conjunto de metodologías orientadas a maximizar
resultados de forma escalable y reproducible. Su adopción correcta reduce costos
operativos y aumenta la previsibilidad del crecimiento.</p>

<h2>Principales beneficios</h2>
<ul>
  <li><strong>Eficiencia operativa:</strong> reducción de procesos redundantes.</li>
  <li><strong>Escalabilidad:</strong> el modelo crece sin degradar la calidad.</li>
  <li><strong>Medición:</strong> KPIs claros desde la primera semana.</li>
  <li><strong>Sostenibilidad:</strong> resultados estables a 6–12 meses.</li>
</ul>

<h2>Cómo implementar {keyword} paso a paso</h2>

<h3>Fase 1 — Diagnóstico inicial</h3>
<p>Antes de actuar, audita el estado actual con datos reales. Sin diagnóstico,
cualquier intervención es especulativa.</p>

<h3>Fase 2 — Diseño de la estrategia</h3>
<p>Define objetivos SMART, plazos y responsables. La claridad aquí determina
el 80% del éxito posterior.</p>

<h3>Fase 3 — Implementación y medición</h3>
<p>Ejecuta en ciclos cortos (2–4 semanas), mide y ajusta. La iteración es el
mecanismo de mejora, no la planificación perfecta.</p>

<h2>Recursos y herramientas recomendadas</h2>
<p>Para implementar {keyword} con garantías, puedes apoyarte en recursos como
<a href="{url}" rel="dofollow">{anchor}</a>, que ofrece servicios y documentación
especializada con casos de éxito documentados.</p>

<p>Complementariamente, la
<a href="{ext_url}" rel="nofollow" target="_blank">{ext_name}</a>
publica criterios de calidad actualizados que son referencia obligada en el sector.</p>

<figure>
  <img src="placeholder-{keyword.replace(' ', '-')}.webp"
       alt="Diagrama de implementación de {keyword} con fases y resultados esperados"
       width="800" height="450" loading="lazy" />
  <figcaption>Figura 1. Ciclo de implementación de {keyword}.</figcaption>
</figure>"""


def _mock_commercial(title: str, keyword: str, anchor: str, url: str, tone: str) -> str:
    ext_name, ext_url = _ext_link()
    return f"""<h1>Servicios de {keyword}: comparativa y guía de decisión 2025</h1>

<p>El mercado de <strong>{keyword}</strong> ha madurado significativamente. Elegir
mal el proveedor puede costar entre un 30% y un 60% más en correcciones. Esta
comparativa te da los criterios objetivos para decidir bien.</p>

<h2>Criterios de evaluación</h2>
<ul>
  <li><strong>Experiencia demostrable:</strong> casos de uso similares al tuyo.</li>
  <li><strong>Transparencia de precios:</strong> sin costos ocultos post-contrato.</li>
  <li><strong>Soporte técnico:</strong> tiempo de respuesta garantizado en SLA.</li>
  <li><strong>Escalabilidad:</strong> puede crecer contigo sin fricción contractual.</li>
</ul>

<h2>Tabla comparativa de opciones</h2>
<table>
  <thead>
    <tr>
      <th>Criterio</th>
      <th>Opción premium</th>
      <th>Opción media</th>
      <th>Opción básica</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Precio mensual</td><td>€€€€</td><td>€€€</td><td>€€</td></tr>
    <tr><td>Soporte</td><td>24/7 dedicado</td><td>Laboral</td><td>Email</td></tr>
    <tr><td>Onboarding</td><td>Personalizado</td><td>Guiado</td><td>Autoservicio</td></tr>
    <tr><td>Integraciones</td><td>Ilimitadas</td><td>Hasta 20</td><td>Básicas</td></tr>
    <tr><td>Garantía SLA</td><td>99,9%</td><td>99,5%</td><td>No incluida</td></tr>
  </tbody>
</table>

<h2>Señales de alerta al contratar</h2>
<ul>
  <li>Promesas de resultados garantizados sin datos de respaldo.</li>
  <li>Contratos de larga duración sin cláusula de salida.</li>
  <li>Ausencia de reportes de desempeño mensuales.</li>
</ul>

<h2>Veredicto y recomendación</h2>
<p>Para la mayoría de organizaciones medianas, la combinación óptima es un
proveedor mid-tier con SLA documentado. Empresas como
<a href="{url}" rel="dofollow">{anchor}</a> ofrecen un equilibrio comprobado
entre capacidad técnica y accesibilidad económica.</p>

<p>Para benchmarks independientes del sector, consulta
<a href="{ext_url}" rel="nofollow" target="_blank">{ext_name}</a>.</p>

<figure>
  <img src="placeholder-comparativa-{keyword.replace(' ', '-')}.webp"
       alt="Comparativa visual de opciones de {keyword} por precio y funcionalidades"
       width="800" height="400" loading="lazy" />
  <figcaption>Figura 1. Mapa de posicionamiento de opciones en {keyword}.</figcaption>
</figure>"""


def _mock_faq(title: str, keyword: str, anchor: str, url: str, tone: str) -> str:
    ext_name, ext_url = _ext_link()
    return f"""<h1>Preguntas frecuentes sobre {keyword}: respuestas de expertos</h1>

<p>Compilamos las dudas más consultadas sobre <strong>{keyword}</strong>
con respuestas directas, verificadas y orientadas a la acción.</p>

<div itemscope itemtype="https://schema.org/FAQPage">

  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h2 itemprop="name">¿Qué es {keyword} y para qué sirve?</h2>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
      <p itemprop="text"><strong>{keyword.capitalize()}</strong> es una metodología
      que permite a las organizaciones optimizar sus procesos y obtener resultados
      medibles. Su aplicación correcta genera beneficios sostenibles en plazos
      de 3 a 6 meses según el contexto de implementación.</p>
    </div>
  </div>

  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h2 itemprop="name">¿Cuánto tiempo tarda en verse resultados con {keyword}?</h2>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
      <p itemprop="text">Los primeros indicadores suelen aparecer entre las semanas
      4 y 8. Los resultados consolidados, entre los meses 3 y 6. La consistencia
      en la ejecución es el factor más determinante del plazo.</p>
    </div>
  </div>

  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h2 itemprop="name">¿Cuánto cuesta implementar {keyword}?</h2>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
      <p itemprop="text">El rango varía ampliamente según el alcance: desde
      soluciones básicas de bajo costo hasta implementaciones enterprise de varios
      miles de euros al mes. Obtén un presupuesto personalizado en
      <a href="{url}">{anchor}</a>.</p>
    </div>
  </div>

  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h2 itemprop="name">¿{keyword.capitalize()} es adecuado para pequeñas empresas?</h2>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
      <p itemprop="text">Sí, siempre que se elija una implementación proporcional
      al tamaño de la operación. Existen enfoques escalables que permiten empezar
      con presupuestos reducidos y crecer gradualmente.</p>
    </div>
  </div>

  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h2 itemprop="name">¿Qué diferencia a un buen proveedor de {keyword}?</h2>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
      <p itemprop="text">Tres factores: casos de éxito verificables en tu sector,
      transparencia en metodología y métricas, y un SLA de soporte claro. Evita
      proveedores que garantizan resultados sin datos de respaldo.</p>
    </div>
  </div>

</div>

<p>Para profundizar, consulta también
<a href="{ext_url}" rel="nofollow" target="_blank">{ext_name}</a>.</p>"""


_MOCK_BUILDERS = {
    "pillar":     _mock_pillar,
    "commercial": _mock_commercial,
    "faq":        _mock_faq,
}


# ── Schema builders ──────────────────────────────────────────────────────────

def _build_schema(article_type: str, title: str, keyword: str, brand: str) -> dict:
    base = {
        "@context": "https://schema.org",
        "author": {"@type": "Organization", "name": brand},
        "headline": title,
        "description": f"Contenido especializado sobre {keyword}.",
        "inLanguage": "es",
    }
    if article_type == "pillar":
        return {**base, "@type": "Article"}
    if article_type == "commercial":
        return {**base, "@type": "Article", "articleSection": "Comparativa"}
    # faq
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f"¿Qué es {keyword}?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"{keyword.capitalize()} es una metodología clave en el sector.",
                },
            }
        ],
    }


# ── Public API ───────────────────────────────────────────────────────────────

def generate_article(
    article_type: str,
    crawl_data: dict,
    keywords: dict,
    anchor_text: str,
    target_url: str,
    use_real_llm: bool = False,
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
) -> GeneratedArticle:
    """
    Generate one article. Selects a random template, builds content, attaches schema.
    Falls back to mock if LLM call fails.
    """
    templates = _load_templates(article_type)
    template = _select_template(templates)

    theme = crawl_data.get("theme", "general")
    title_text = crawl_data.get("title", "Guía completa")
    brand = crawl_data.get("brand", "Hub Editorial")
    keyword = keywords.get("primary", theme)
    tone = template.get("tone", "neutral")

    if use_real_llm and openai_api_key:
        article = _generate_with_llm(
            article_type, template, crawl_data, keywords,
            anchor_text, target_url, openai_api_key, openai_model,
        )
        if article:
            return article

    # Mock generation
    builder = _MOCK_BUILDERS[article_type]
    html = builder(title_text, keyword, anchor_text, target_url, tone)

    title_map = {
        "pillar":     f"Guía Completa de {title_text}: Todo lo que Necesitas Saber",
        "commercial": f"Servicios de {title_text}: Comparativa y Precios 2025",
        "faq":        f"Preguntas Frecuentes sobre {title_text}: Respuestas de Expertos",
    }
    article_title = title_map[article_type]
    meta_title = f"{article_title} | {brand}"[:70]
    meta_desc = (
        f"Descubre todo sobre {keyword}. "
        f"Guía práctica con ejemplos, beneficios y recomendaciones de expertos."
    )[:160]

    schema = _build_schema(article_type, article_title, keyword, brand)

    return GeneratedArticle(
        article_type=article_type,
        title=article_title,
        meta_title=meta_title,
        meta_description=meta_desc,
        h1=f"{keyword.capitalize()}: guía completa para profesionales",
        content_html=html,
        schema_markup=schema,
        keywords_used=[keyword] + keywords.get("secondary", []),
        anchor_text=anchor_text,
        target_url=target_url,
        template_used=template.get("name", "default"),
    )


def _generate_with_llm(
    article_type: str,
    template: dict,
    crawl_data: dict,
    keywords: dict,
    anchor_text: str,
    target_url: str,
    api_key: str,
    model: str,
) -> Optional["GeneratedArticle"]:
    """Real LLM generation — only called when OPENAI_API_KEY is set."""
    try:
        import random as _rnd
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt_tpl = template.get("prompt", "")
        prompt = prompt_tpl.format(
            theme=crawl_data.get("theme", "general"),
            title=crawl_data.get("title", ""),
            primary_kw=keywords.get("primary", ""),
            secondary_kws=", ".join(keywords.get("secondary", [])),
            anchor_text=anchor_text,
            target_url=target_url,
            tone=template.get("tone", "neutral"),
            length=template.get("length", 900),
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un redactor SEO senior especializado en hubs editoriales. "
                        "Escribe en español, con estructura HTML semántica (H1, H2, H3), "
                        "schema markup integrado y enlaces naturales. "
                        "Devuelve ÚNICAMENTE el HTML del artículo, sin explicaciones."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=_rnd.uniform(0.72, 0.90),
            max_tokens=2200,
        )
        html = resp.choices[0].message.content
        brand = crawl_data.get("brand", "Hub Editorial")
        keyword = keywords.get("primary", "")
        title = f"Artículo sobre {keyword}"
        schema = _build_schema(article_type, title, keyword, brand)

        return GeneratedArticle(
            article_type=article_type,
            title=title,
            meta_title=f"{title} | {brand}"[:70],
            meta_description=f"Guía completa sobre {keyword}."[:160],
            h1=title,
            content_html=html,
            schema_markup=schema,
            keywords_used=[keyword] + keywords.get("secondary", []),
            anchor_text=anchor_text,
            target_url=target_url,
            template_used=template.get("name", "llm"),
        )

    except Exception as e:
        logger.warning("LLM generation failed (%s), falling back to mock.", e)
        return None
