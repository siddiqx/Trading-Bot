#!/usr/bin/env python3
"""Institutional cTrader Live Position Immediate Close Utility.

Allows immediate, manual or programmatic closing of any active or orphaned cTrader position.
Usage:
    python scripts/close_live_position.py --position 16303045 --pair USDCAD --units 86000
    python scripts/close_live_position.py --position 16303045 --lots 0.86
"""

import sys
import argparse
import logging
from pathlib import Path

# Set up project root
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from core.ctrader_executor import close_ctrader_position

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("cTraderCloseUtility")


def main():
    parser = argparse.ArgumentParser(description="Close a cTrader Open Position at market")
    parser.add_argument("--position", type=int, required=True, help="cTrader integer position ID")
    parser.add_argument("--pair", type=str, default="USDCAD", help="Currency pair (e.g., USDCAD)")
    parser.add_argument("--units", type=int, default=None, help="Position volume in currency units (e.g. 86000)")
    parser.add_argument("--lots", type=float, default=None, help="Position volume in lots (e.g. 0.86)")
    parser.add_argument("--cents", type=int, default=None, help="Position volume in cTrader cents (subunits)")

    args = parser.parse_args()

    print(f"\n=======================================================")
    print(f"cTrader Market Close Dispatcher")
    print(f"Position ID: {args.position} | Symbol: {args.pair}")
    print(f"=======================================================")

    res = close_ctrader_position(
        position_id=args.position,
        volume_cents=args.cents,
        volume_units=args.units,
        lots=args.lots,
        pair=args.pair
    )

    print(f"\nExecution Result: {res.get('status')}")
    print(f"Mode:             {res.get('mode')}")
    print(f"Volume (cents):   {res.get('volume_cents')}")
    print(f"Account:          {res.get('account_id')}")
    if res.get("error"):
        print(f"Error Description: {res.get('error')}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    main()
