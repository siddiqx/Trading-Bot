"""Marketing & Automated Growth Subsystem."""

from core.marketing.case_study_generator import (
    generate_reddit_case_study,
    generate_twitter_thread,
    generate_telegram_share_url,
    generate_tradingview_idea_post,
    format_tradingview_telegram_pack,
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
from core.marketing.discord_publisher import (
    send_discord_signal,
    send_discord_tp_celebration,
    send_discord_content,
    send_discord_poll,
)
from core.marketing.engagement_engine import (
    generate_daily_news_briefing,
    build_natural_community_poll,
    get_ict_educational_card,
    get_vip_promotion_card,
    check_and_dispatch_engagement_content,
)

__all__ = [
    "generate_reddit_case_study",
    "generate_twitter_thread",
    "generate_telegram_share_url",
    "generate_tradingview_idea_post",
    "format_tradingview_telegram_pack",
    "publish_reddit_case_study",
    "save_local_draft",
    "is_on_cooldown",
    "format_viral_share_footer",
    "generate_weekly_performance_digest",
    "send_discord_signal",
    "send_discord_tp_celebration",
    "send_discord_content",
    "send_discord_poll",
    "generate_daily_news_briefing",
    "build_natural_community_poll",
    "get_ict_educational_card",
    "get_vip_promotion_card",
    "check_and_dispatch_engagement_content",
]
