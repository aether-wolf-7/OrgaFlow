"""
Keyword generation and intent-based clustering.
Includes TF-IDF cosine similarity cannibalization detection.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "el", "la", "los", "las", "de", "del", "en", "y", "a", "para",
    "con", "por", "un", "una", "unos", "unas", "su", "sus", "al",
    "que", "es", "se", "lo", "le", "les", "más", "pero", "si",
    "no", "ya", "hay", "ser", "han", "son", "fue", "era",
}

INTENT_MODIFIERS: dict[str, list[str]] = {
    "informacional": [
        "qué es", "cómo funciona", "guía completa de", "todo sobre",
        "tipos de", "ventajas de", "historia de", "para qué sirve",
    ],
    "comercial": [
        "mejor servicio de", "precio de", "contratar", "empresa de",
        "comparativa de", "cómo elegir", "cuánto cuesta", "alternativas a",
    ],
    "local": [
        "en España", "en México", "cerca de mí",
        "servicio local de", "empresas de", "en tu ciudad",
    ],
}

LONG_TAIL_TEMPLATES: list[str] = [
    "{kw} para pequeñas empresas",
    "{kw} paso a paso",
    "cómo implementar {kw}",
    "{kw} en 2025",
    "{kw} sin experiencia previa",
    "errores comunes en {kw}",
    "{kw} para principiantes",
]


@dataclass
class KeywordCluster:
    primary: str
    secondary: List[str] = field(default_factory=list)
    long_tail: List[str] = field(default_factory=list)
    intent: str = "informacional"


def _extract_base_keyword(title: str, theme: str) -> str:
    """Pull the 2–3 most relevant content words from the page title."""
    words = [
        w.lower()
        for w in re.split(r"[\s\-|–·:,]+", title)
        if len(w) > 3 and w.lower() not in STOP_WORDS
    ]
    base = " ".join(words[:3]) if words else theme
    return base


def generate_clusters(theme: str, title: str, text_sample: str) -> List[KeywordCluster]:
    """Return one KeywordCluster per intent type, built from the crawled page."""
    base = _extract_base_keyword(title, theme)
    clusters: List[KeywordCluster] = []

    for intent, modifiers in INTENT_MODIFIERS.items():
        primary = f"{modifiers[0]} {base}"
        secondary = [f"{mod} {base}" for mod in modifiers[1:4]]
        long_tail = [t.format(kw=base) for t in LONG_TAIL_TEMPLATES[:4]]

        clusters.append(KeywordCluster(
            primary=primary,
            secondary=secondary,
            long_tail=long_tail,
            intent=intent,
        ))

    return clusters


def check_cannibalization(articles: List[str], threshold: float = 0.85) -> List[tuple]:
    """
    Detect cannibalization risk between articles using TF-IDF cosine similarity.
    Returns list of (index_a, index_b, score) tuples where score > threshold.
    """
    if len(articles) < 2:
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(max_features=500, min_df=1)
        tfidf_matrix = vectorizer.fit_transform(articles)
        sim_matrix = cosine_similarity(tfidf_matrix)

        conflicts = []
        n = len(articles)
        for i in range(n):
            for j in range(i + 1, n):
                score = float(sim_matrix[i][j])
                if score > threshold:
                    conflicts.append((i, j, round(score, 3)))
        return conflicts

    except Exception as e:
        logger.warning("Cannibalization check failed: %s", e)
        return []
