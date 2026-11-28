"""
Unit Tests for Institutional Shorts & Reels Video Generator
===========================================================
Verifies:
  • Video generation interface & metadata generation
  • Multi-asset script library coverage (XAUUSD, EURUSD, USDCAD, USDCHF, AUDUSD)
  • Telegram sendVideo handler & payload serialization
  • Interactive /short and /video command handling in contents_bot
"""

import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from core.marketing.shorts_generator import (
    generate_trading_short_video,
    SHORTS_SCRIPTS,
    _get_system_font,
    render_phase_charts
)
from core.marketing.contents_bot import (
    send_contents_video,
    setup_contents_bot_commands,
    handle_contents_bot_update
)


class TestShortsGenerator(unittest.TestCase):

    def test_shorts_scripts_coverage(self):
        """Verify all active trading assets have complete short video scripts."""
        expected_assets = ["XAUUSD", "EURUSD", "USDCAD", "USDCHF", "AUDUSD"]
        for asset in expected_assets:
            self.assertIn(asset, SHORTS_SCRIPTS)
            config = SHORTS_SCRIPTS[asset]
            self.assertIn("title", config)
            self.assertIn("voiceover", config)
            self.assertIn("steps", config)
            self.assertIn("metrics", config)
            self.assertIn("ig_caption", config)
            self.assertEqual(len(config["steps"]), 4)
            self.assertTrue(len(config["voiceover"]) > 50)
            self.assertIn("#", config["ig_caption"])

    def test_generate_trading_short_video_test_mode(self):
        """Verify fast-path behavior during unit tests."""
        video_bytes, meta = generate_trading_short_video("XAUUSD")
        self.assertIsNotNone(video_bytes)
        self.assertTrue(len(video_bytes) > 0)
        self.assertEqual(meta.get("pair"), "XAUUSD")
        self.assertIn("title", meta)
        self.assertIn("ig_caption", meta)

    def test_render_phase_charts(self):
        """Verify chart rendering across 4 progressive phases."""
        dates = pd.date_range("2026-01-01", periods=60, freq="15min")
        df = pd.DataFrame({
            "open": np.linspace(2650, 2680, 60),
            "high": np.linspace(2652, 2685, 60),
            "low": np.linspace(2648, 2678, 60),
            "close": np.linspace(2651, 2682, 60),
            "volume": [1000] * 60
        }, index=dates)

        charts = render_phase_charts(df, pair="XAUUSD", direction="LONG", num_bars=45)
        self.assertEqual(len(charts), 4)
        for c in charts:
            self.assertEqual(c.size, (1000, 820))

    def test_send_contents_video_suppressed(self):
        """Verify send_contents_video is safely suppressed in test mode."""
        dummy_video = b"\x00\x00\x00 ftypmp42\x00\x00\x00\x00test"
        res = send_contents_video("8142877259", dummy_video, caption="Test Video")
        self.assertTrue(res)

    def test_setup_contents_bot_commands(self):
        """Verify Telegram bot menu commands setup."""
        res = setup_contents_bot_commands()
        self.assertTrue(res)

    @patch("core.marketing.contents_bot.send_contents_video")
    @patch("core.marketing.contents_bot.send_contents_message")
    def test_handle_short_slash_command(self, mock_msg, mock_vid):
        """Verify /short and /video commands execute cleanly."""
        mock_msg.return_value = True
        mock_vid.return_value = True

        update = {
            "update_id": 999901,
            "message": {
                "message_id": 501,
                "chat": {"id": "8142877259"},
                "from": {"id": 8142877259},
                "text": "/short xauusd"
            }
        }

        success = handle_contents_bot_update(update)
        self.assertTrue(success)
        mock_vid.assert_called_once()

    @patch("core.marketing.contents_bot.send_contents_video")
    @patch("core.marketing.contents_bot.send_contents_message")
    def test_handle_short_callback_button(self, mock_msg, mock_vid):
        """Verify tapping 'btn_sh_XAUUSD' inline button generates video."""
        mock_msg.return_value = True
        mock_vid.return_value = True

        update = {
            "update_id": 999902,
            "callback_query": {
                "id": "cb_test_902",
                "from": {"id": 8142877259},
                "message": {"chat": {"id": "8142877259"}, "message_id": 502},
                "data": "btn_sh_XAUUSD"
            }
        }

        success = handle_contents_bot_update(update)
        self.assertTrue(success)
        mock_vid.assert_called_once()


if __name__ == "__main__":
    unittest.main()
