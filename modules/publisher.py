"""
WordPress publisher with Poisson-process scheduling.

Publication timing uses an exponential inter-arrival distribution
(inverse of Poisson rate) with business-hours bias and day-of-week
weighting to mimic human editorial patterns. No two hubs ever
publish at the exact same moment.
"""
import base64
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import requests

logger = logging.getLogger(__name__)

# Business-hour weight by clock hour (0–23). Peaks at 10 and 15.
_HOUR_WEIGHTS = [
    0, 0, 0, 0, 0, 0, 0, 0,   # 00–07
    1, 3, 5, 4, 3, 2, 3, 5,   # 08–15
    4, 3, 2, 1, 1, 0, 0, 0,   # 16–23
]
# Weekday weights: Mon–Sun (higher mid-week)
_DAY_WEIGHTS = [4, 5, 5, 4, 3, 2, 1]


@dataclass
class PublishResult:
    success: bool
    post_id: Optional[int] = None
    scheduled_at: Optional[str] = None
    error: str = ""
    mock: bool = False


class PublishScheduler:
    """
    Generates staggered publication schedules using a Poisson process.

    Inter-arrival times are drawn from Exponential(1/lambda_per_day),
    then mapped to the nearest valid business hour. The result is a
    schedule that looks organic in GSC crawl logs.
    """

    def __init__(self, lambda_per_week: float = 3.0):
        self.lambda_per_day = lambda_per_week / 7.0

    def _next_dt(self, from_dt: datetime) -> datetime:
        wait_days = np.random.exponential(1.0 / self.lambda_per_day)
        candidate = from_dt + timedelta(days=float(wait_days))

        # Bias toward valid publishing hours
        hour = random.choices(range(24), weights=_HOUR_WEIGHTS, k=1)[0]
        minute = random.randint(0, 59)
        return candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def generate_schedule(self, n: int, start: Optional[datetime] = None) -> list[datetime]:
        schedule: list[datetime] = []
        current = start or datetime.now()
        for _ in range(n):
            current = self._next_dt(current)
            schedule.append(current)
        return schedule


def publish_to_wordpress(
    wp_url: str,
    wp_user: str,
    wp_password: str,
    title: str,
    content: str,
    schema_json: str,
    categories: list[str],
    tags: list[str],
    scheduled_at: Optional[str] = None,
) -> PublishResult:
    """
    Publish (or schedule) a post via the WordPress REST API.

    All articles are published as 'draft' by default so a human can
    review before going live. Set scheduled_at (ISO 8601) to auto-schedule.
    If wp_url is empty the call is mocked — useful for dry-run and demo.
    """
    if not wp_url:
        mock_id = random.randint(1000, 99999)
        logger.info("Mock publish: post_id=%s scheduled=%s", mock_id, scheduled_at)
        return PublishResult(
            success=True,
            post_id=mock_id,
            scheduled_at=scheduled_at,
            mock=True,
        )

    credentials = base64.b64encode(f"{wp_user}:{wp_password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
    }

    # Inject schema markup at the end of content
    full_content = (
        f"{content}\n\n"
        f'<script type="application/ld+json">\n{schema_json}\n</script>'
    )

    payload: dict = {
        "title":   title,
        "content": full_content,
        "status":  "future" if scheduled_at else "draft",
        "tags":    tags,
    }
    if scheduled_at:
        payload["date"] = scheduled_at

    try:
        resp = requests.post(
            f"{wp_url.rstrip('/')}/wp-json/wp/v2/posts",
            headers=headers,
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return PublishResult(
            success=True,
            post_id=data.get("id"),
            scheduled_at=scheduled_at,
        )
    except requests.exceptions.HTTPError as e:
        err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        logger.error("WP publish error: %s", err)
        return PublishResult(success=False, error=err)
    except Exception as e:
        logger.error("WP publish exception: %s", e)
        return PublishResult(success=False, error=str(e)[:200])
