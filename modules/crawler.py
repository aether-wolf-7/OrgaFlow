"""
Web crawler: fetches URL content and extracts semantic metadata.
Detects topic theme and primary search intent for hub assignment.
"""
import re
import logging
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

THEME_KEYWORDS: dict[str, list[str]] = {
    "negocios":    ["empresa", "negocio", "finanzas", "inversión", "startup",
                    "emprendimiento", "gestión", "estrategia", "pyme", "comercio"],
    "tecnología":  ["software", "tecnología", "digital", "app", "ia",
                    "inteligencia artificial", "programación", "datos", "cloud", "api"],
    "marketing":   ["marketing", "seo", "publicidad", "branding", "ventas",
                    "conversión", "email", "redes sociales", "campaña", "leads"],
    "educación":   ["curso", "formación", "aprendizaje", "educación",
                    "certificación", "habilidades", "tutorial", "masterclass"],
    "industria":   ["manufactura", "logística", "producción", "operaciones",
                    "supply chain", "industria", "fábrica", "calidad", "proceso"],
}

INTENT_KEYWORDS: dict[str, list[str]] = {
    "informacional": ["qué es", "cómo", "guía", "tutorial", "explicación",
                      "definición", "tipos de", "ventajas", "para qué sirve"],
    "comercial":     ["mejor", "precio", "comprar", "servicio", "empresa",
                      "agencia", "profesional", "contratar", "cotizar", "oferta"],
    "local":         ["ciudad", "españa", "méxico", "argentina", "cerca",
                      "local", "zona", "provincia", "madrid", "barcelona"],
}


@dataclass
class CrawlResult:
    url: str
    title: str = ""
    meta_description: str = ""
    h1: str = ""
    text_sample: str = ""
    theme: str = "negocios"
    intent: str = "informacional"
    word_count: int = 0
    success: bool = False
    error: str = ""


def _score_map(text: str, keyword_map: dict[str, list[str]]) -> str:
    text_lower = text.lower()
    scores = {
        category: sum(1 for kw in kws if kw in text_lower)
        for category, kws in keyword_map.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else list(keyword_map.keys())[0]


def crawl(url: str, timeout: int = 12) -> CrawlResult:
    result = CrawlResult(url=url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        title_tag = soup.find("title")
        result.title = title_tag.get_text(strip=True)[:200] if title_tag else url

        meta = soup.find("meta", attrs={"name": "description"})
        result.meta_description = (meta.get("content", "")[:300] if meta else "")

        h1_tag = soup.find("h1")
        result.h1 = (h1_tag.get_text(strip=True)[:200] if h1_tag else result.title)

        raw_text = soup.get_text(separator=" ", strip=True)
        raw_text = re.sub(r"\s+", " ", raw_text)
        result.text_sample = raw_text[:3000]
        result.word_count = len(raw_text.split())

        combined = f"{result.title} {result.h1} {result.text_sample}"
        result.theme = _score_map(combined, THEME_KEYWORDS)
        result.intent = _score_map(combined, INTENT_KEYWORDS)
        result.success = True

    except requests.exceptions.Timeout:
        result.error = "Timeout"
        logger.warning("Timeout crawling %s", url)
    except requests.exceptions.HTTPError as e:
        result.error = f"HTTP {e.response.status_code}"
        logger.warning("HTTP error crawling %s: %s", url, e)
    except Exception as e:
        result.error = str(e)[:120]
        logger.warning("Crawl failed %s: %s", url, e)

    return result
