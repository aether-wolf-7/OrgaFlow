"""
Central configuration. Reads from .env file or environment variables.
Copy .env.example to .env and fill in your values.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).parent

# ── LLM ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
USE_MOCK_LLM: bool = not bool(OPENAI_API_KEY)

# ── Database ────────────────────────────────────────────────────────────────
DB_PATH: Path = BASE_DIR / os.getenv("DB_PATH", "data/pipeline.db")

# ── Pipeline ────────────────────────────────────────────────────────────────
BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "10"))
PILOT_MAX_URLS: int = int(os.getenv("PILOT_MAX_URLS", "50"))
MIN_POSTS_PER_WEEK: int = int(os.getenv("MIN_POSTS_PER_WEEK", "2"))
MAX_POSTS_PER_WEEK: int = int(os.getenv("MAX_POSTS_PER_WEEK", "4"))

# ── Hub definitions ─────────────────────────────────────────────────────────
HUBS: dict = {
    "hub_negocios": {
        "name": "Estrategia & Negocios",
        "topics": ["negocios", "empresa", "finanzas", "estrategia", "gestión", "emprendimiento"],
        "tone": "ejecutivo",
        "wp_url":      os.getenv("HUB1_WP_URL", ""),
        "wp_user":     os.getenv("HUB1_WP_USER", ""),
        "wp_password": os.getenv("HUB1_WP_PASSWORD", ""),
    },
    "hub_tecnologia": {
        "name": "Tecnología & Innovación",
        "topics": ["tecnología", "software", "digital", "ia", "automatización", "datos"],
        "tone": "técnico",
        "wp_url":      os.getenv("HUB2_WP_URL", ""),
        "wp_user":     os.getenv("HUB2_WP_USER", ""),
        "wp_password": os.getenv("HUB2_WP_PASSWORD", ""),
    },
    "hub_marketing": {
        "name": "Marketing Digital",
        "topics": ["marketing", "seo", "publicidad", "branding", "conversión", "contenido"],
        "tone": "práctico",
        "wp_url":      os.getenv("HUB3_WP_URL", ""),
        "wp_user":     os.getenv("HUB3_WP_USER", ""),
        "wp_password": os.getenv("HUB3_WP_PASSWORD", ""),
    },
    "hub_educacion": {
        "name": "Educación & Formación",
        "topics": ["educación", "formación", "cursos", "aprendizaje", "habilidades", "certificación"],
        "tone": "didáctico",
        "wp_url":      os.getenv("HUB4_WP_URL", ""),
        "wp_user":     os.getenv("HUB4_WP_USER", ""),
        "wp_password": os.getenv("HUB4_WP_PASSWORD", ""),
    },
    "hub_industria": {
        "name": "Industria & Operaciones",
        "topics": ["industria", "manufactura", "logística", "operaciones", "producción", "supply chain"],
        "tone": "especializado",
        "wp_url":      os.getenv("HUB5_WP_URL", ""),
        "wp_user":     os.getenv("HUB5_WP_USER", ""),
        "wp_password": os.getenv("HUB5_WP_PASSWORD", ""),
    },
}
