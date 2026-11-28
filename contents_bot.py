#!/usr/bin/env python3
"""
Contents Marketing Bot CLI Entrypoint
====================================
Interactive control for @contents7_bot.
Generates copy-ready content for Twitter/X and Reddit, or runs a 24/7 listener.

Usage:
  python contents_bot.py --loop       # Run live real-time Telegram listener
  python contents_bot.py --signal     # Dispatch clean signal & chart to your chat
  python contents_bot.py --twitter    # Dispatch Twitter/X thread
  python contents_bot.py --reddit     # Dispatch Reddit case study
  python contents_bot.py --chart      # Dispatch high-res ICT/SMC chart
  python contents_bot.py --outlook    # Dispatch 4H trend outlook
"""

import sys
import os

from core.marketing.contents_bot import (
    run_contents_bot_loop,
    process_contents_bot_pending_updates,
    dispatch_automated_market_content,
    get_latest_trade_or_benchmark,
    handle_contents_bot_update,
    TELEGRAM_MARKETING_BOT_TOKEN,
    TELEGRAM_CHAT_ID
)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        run_contents_bot_loop()
        return

    admin_id = TELEGRAM_CHAT_ID.split(",")[0].strip() if TELEGRAM_CHAT_ID else "8142877259"
    trade, pips, r_val = get_latest_trade_or_benchmark()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "--help"

    if cmd in ("--signal", "-s"):
        mock_update = {"message": {"chat": {"id": admin_id}, "text": "/signal"}}
        res = handle_contents_bot_update(mock_update)
        print(f"Dispatched clean trade signal & chart to {admin_id}: {res}")

    elif cmd in ("--twitter", "-t"):
        mock_update = {"message": {"chat": {"id": admin_id}, "text": "/twitter"}}
        res = handle_contents_bot_update(mock_update)
        print(f"Dispatched Twitter / X thread to {admin_id}: {res}")

    elif cmd in ("--reddit", "-r"):
        mock_update = {"message": {"chat": {"id": admin_id}, "text": "/reddit"}}
        res = handle_contents_bot_update(mock_update)
        print(f"Dispatched Reddit case study to {admin_id}: {res}")

    elif cmd in ("--chart", "-c"):
        mock_update = {"message": {"chat": {"id": admin_id}, "text": "/chart"}}
        res = handle_contents_bot_update(mock_update)
        print(f"Dispatched high-res chart to {admin_id}: {res}")

    elif cmd in ("--outlook", "-o"):
        pair = sys.argv[2] if len(sys.argv) > 2 else "EURUSD"
        mock_update = {"message": {"chat": {"id": admin_id}, "text": f"/outlook {pair}"}}
        res = handle_contents_bot_update(mock_update)
        print(f"Dispatched 4H trend outlook ({pair}) to {admin_id}: {res}")

    elif cmd in ("--pack", "--contents"):
        res = dispatch_automated_market_content(trade, realized_pips=pips, realized_r=r_val)
        print(f"Dispatched master content pack to {admin_id}: {res}")

    elif cmd in ("--check", "--poll"):
        offset = process_contents_bot_pending_updates()
        print(f"Processed pending Telegram updates. Next offset: {offset}")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
