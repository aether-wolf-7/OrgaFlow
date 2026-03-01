"""
Statistical anchor text distribution model using Dirichlet sampling.

Prevents over-optimization by enforcing natural anchor diversity.
Each URL gets its own stochastic draw, making the aggregate distribution
indistinguishable from an organic link profile.

Dirichlet alpha parameters are calibrated so the expected values match
the target distribution while the variance keeps individual anchors
unpredictable.
"""
import random
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class AnchorType(str, Enum):
    BRAND         = "brand"
    EXACT_URL     = "exact_url"
    PARTIAL_MATCH = "partial_match"
    GENERIC       = "generic"


# Higher alpha → tighter concentration around the implied mean.
# Means: Brand≈30%, ExactURL≈20%, Partial≈30%, Generic≈20%
_ALPHA = np.array([6.0, 4.0, 6.0, 4.0])

GENERIC_ANCHORS = [
    "más información",
    "ver más",
    "visitar sitio",
    "conocer más",
    "leer artículo completo",
    "acceder aquí",
    "sitio oficial",
    "página web",
    "recurso recomendado",
    "fuente original",
]

# Safety bounds — distributions outside these are resampled.
_BOUNDS = {
    AnchorType.BRAND:         (0.18, 0.42),
    AnchorType.EXACT_URL:     (0.10, 0.32),
    AnchorType.PARTIAL_MATCH: (0.18, 0.42),
    AnchorType.GENERIC:       (0.10, 0.32),
}


@dataclass
class AnchorDistribution:
    brand: float
    exact_url: float
    partial_match: float
    generic: float

    def to_dict(self) -> dict:
        return {
            "brand":         round(self.brand * 100, 1),
            "exact_url":     round(self.exact_url * 100, 1),
            "partial_match": round(self.partial_match * 100, 1),
            "generic":       round(self.generic * 100, 1),
        }

    def is_safe(self) -> bool:
        values = [self.brand, self.exact_url, self.partial_match, self.generic]
        types = list(AnchorType)
        return all(
            _BOUNDS[t][0] <= v <= _BOUNDS[t][1]
            for t, v in zip(types, values)
        )

    def as_weights(self) -> list:
        return [self.brand, self.exact_url, self.partial_match, self.generic]


def sample_anchor_distribution(seed: Optional[int] = None) -> AnchorDistribution:
    """
    Draw one anchor distribution from the Dirichlet prior.
    Resamples up to 10 times if the draw falls outside safety bounds.
    """
    rng = np.random.default_rng(seed)
    for _ in range(10):
        sample = rng.dirichlet(_ALPHA)
        dist = AnchorDistribution(*sample.tolist())
        if dist.is_safe():
            return dist
    # Fallback: return the mean distribution
    logger.warning("Dirichlet resampling exhausted — using mean distribution.")
    total = _ALPHA.sum()
    return AnchorDistribution(*(_ALPHA / total).tolist())


def assign_anchor(
    anchor_type: AnchorType,
    brand_name: str,
    target_url: str,
    keyword: str,
) -> str:
    """Produce the literal anchor text string for a given type."""
    if anchor_type == AnchorType.BRAND:
        return brand_name
    if anchor_type == AnchorType.EXACT_URL:
        return target_url
    if anchor_type == AnchorType.PARTIAL_MATCH:
        words = keyword.split()
        return " ".join(words[:3]) if words else keyword
    return random.choice(GENERIC_ANCHORS)


def get_anchor_for_article(
    brand_name: str,
    target_url: str,
    keyword: str,
    distribution: AnchorDistribution,
) -> str:
    """Sample an anchor type from the distribution, then build the anchor text."""
    types = list(AnchorType)
    chosen = random.choices(types, weights=distribution.as_weights(), k=1)[0]
    return assign_anchor(chosen, brand_name, target_url, keyword)
