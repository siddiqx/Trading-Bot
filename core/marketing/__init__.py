"""Marketing & Automated Growth Subsystem."""

from core.marketing.case_study_generator import (
    generate_reddit_case_study,
    generate_twitter_thread,
    generate_telegram_share_url,
)
from core.marketing.reddit_publisher import (
    publish_reddit_case_study,
    save_local_draft,
    is_on_cooldown,
)
from core.marketing.telegram_growth import (
    format_viral_share_footer,
    generate_weekly_performance_digest,
)

__all__ = [
    "generate_reddit_case_study",
    "generate_twitter_thread",
    "generate_telegram_share_url",
    "publish_reddit_case_study",
    "save_local_draft",
    "is_on_cooldown",
    "format_viral_share_footer",
    "generate_weekly_performance_digest",
]
