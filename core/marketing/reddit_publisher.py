"""
Reddit Marketing & Growth Publisher
===================================
Autonomous dispatcher for institutional trade case studies to Reddit communities.

Features:
  - Direct lightweight Reddit OAuth API integration via `httpx` (zero external dependencies).
  - Anti-Spam Guardrails: Strictly enforces a 12-hour minimum cooldown between automated posts.
  - Safe Local Archiver: If Reddit API credentials are not yet configured in environment/secrets,
    saves the formatted case study to `marketing_drafts/` for immediate 1-click manual sharing.
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

import httpx

logger = logging.getLogger("RedditPublisher")

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "").strip()
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
REDDIT_USERNAME = os.environ.get("REDDIT_USERNAME", "").strip()
REDDIT_PASSWORD = os.environ.get("REDDIT_PASSWORD", "").strip()
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", f"QuantFlowBot/1.0 (by /u/{REDDIT_USERNAME or 'anonymous'})")

DRAFTS_DIR = Path("marketing_drafts")
HISTORY_FILE = DRAFTS_DIR / "reddit_post_history.json"


def _is_reddit_configured() -> bool:
    """Checks whether valid Reddit API credentials are set."""
    return bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET and REDDIT_USERNAME and REDDIT_PASSWORD)


def _load_post_history() -> list:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_post_history(history: list) -> None:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist Reddit history: {e}")


def is_on_cooldown(cooldown_hours: float = 12.0) -> bool:
    """Prevents spam by checking if a post was published recently."""
    history = _load_post_history()
    if not history:
        return False
    last_post = history[-1]
    ts_str = last_post.get("timestamp")
    if not ts_str:
        return False
    try:
        last_dt = datetime.fromisoformat(ts_str)
        now_dt = datetime.now(timezone.utc)
        elapsed = (now_dt - last_dt).total_seconds() / 3600.0
        return elapsed < cooldown_hours
    except Exception:
        return False


def save_local_draft(title: str, body: str, subreddit: str) -> Path:
    """Saves a formatted Reddit case study locally for preview or manual posting."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if c.isalnum() else "_" for c in title[:40]).strip("_").lower()
    draft_file = DRAFTS_DIR / f"reddit_{slug}.md"
    content = (
        f"# TARGET SUBREDDIT: {subreddit}\n"
        f"# GENERATED AT: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"# TITLE: {title}\n\n"
        f"{body}\n"
    )
    with open(draft_file, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Reddit case study draft archived locally: {draft_file}")
    return draft_file


def publish_reddit_case_study(
    case_study: Dict[str, str],
    enforce_cooldown: bool = True
) -> Dict[str, Any]:
    """
    Submits a case study to Reddit using the official OAuth API.
    If credentials are not present, gracefully saves to local drafts.
    """
    title = case_study.get("title", "")
    body = case_study.get("body", "")
    sub = case_study.get("subreddit", "r/Forex").replace("r/", "").strip()

    # Always save a local draft copy
    draft_path = save_local_draft(title, body, sub)

    if not _is_reddit_configured():
        logger.info(
            f"Reddit API credentials not set. Case study saved to {draft_path} for manual sharing."
        )
        return {
            "status": "DRAFT_SAVED",
            "url": str(draft_path),
            "message": "Saved locally. Configure REDDIT_CLIENT_ID & REDDIT_USERNAME to enable auto-publish."
        }

    if enforce_cooldown and is_on_cooldown(cooldown_hours=12.0):
        logger.info(f"Reddit post cooldown active (max 1 post per 12 hours). Draft saved to {draft_path}.")
        return {
            "status": "COOLDOWN_ACTIVE",
            "url": str(draft_path),
            "message": "Cooldown active to protect account authority."
        }

    # Authenticate via Reddit OAuth
    token_url = "https://www.reddit.com/api/v1/access_token"
    auth = (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
    data = {
        "grant_type": "password",
        "username": REDDIT_USERNAME,
        "password": REDDIT_PASSWORD
    }
    headers = {"User-Agent": REDDIT_USER_AGENT}

    try:
        with httpx.Client(timeout=15.0) as client:
            auth_resp = client.post(token_url, auth=auth, data=data, headers=headers)
            if auth_resp.status_code != 200:
                logger.error(f"Reddit OAuth authentication failed: HTTP {auth_resp.status_code} - {auth_resp.text}")
                return {"status": "AUTH_ERROR", "error": auth_resp.text}

            auth_data = auth_resp.json()
            access_token = auth_data.get("access_token")
            if not access_token:
                logger.error(f"No access token in Reddit response: {auth_data}")
                return {"status": "AUTH_ERROR", "error": "Missing access_token"}

            # Submit the post
            submit_url = "https://oauth.reddit.com/api/submit"
            submit_headers = {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": REDDIT_USER_AGENT
            }
            submit_payload = {
                "sr": sub,
                "kind": "self",
                "title": title,
                "text": body,
                "sendreplies": True
            }

            post_resp = client.post(submit_url, headers=submit_headers, data=submit_payload)
            if post_resp.status_code != 200:
                logger.error(f"Reddit post submission failed: HTTP {post_resp.status_code} - {post_resp.text}")
                return {"status": "SUBMIT_ERROR", "error": post_resp.text}

            res_json = post_resp.json()
            post_url = res_json.get("json", {}).get("data", {}).get("url")

            # Record in history for cooldown tracking
            history = _load_post_history()
            history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "title": title,
                "subreddit": sub,
                "url": post_url or ""
            })
            _save_post_history(history)

            logger.info(f"Reddit case study successfully published to r/{sub}: {post_url}")
            return {
                "status": "PUBLISHED",
                "url": post_url,
                "subreddit": sub,
                "title": title
            }

    except Exception as e:
        logger.error(f"Unexpected error publishing to Reddit: {e}", exc_info=True)
        return {"status": "ERROR", "error": str(e)}
