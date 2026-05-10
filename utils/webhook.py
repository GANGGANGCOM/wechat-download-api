#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 tmwgsicp
# Licensed under the GNU Affero General Public License v3.0
# See LICENSE file in the project root for full license text.
# SPDX-License-Identifier: AGPL-3.0-only
"""
Webhook 閫氱煡妯″潡
鏀寔浼佷笟寰俊缇ゆ満鍣ㄤ汉鍜岄€氱敤 Webhook
"""

import httpx
import time
import os
import logging
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger("webhook")

EVENT_LABELS = {
    "login_success": "鐧诲綍鎴愬姛",
    "login_expired": "鐧诲綍杩囨湡",
    "login_expiring_soon": "鐧诲綍鍗冲皢杩囨湡",
    "login_expiring_critical": "鐧诲綍鍗冲皢杩囨湡锛堢揣鎬ワ級",
    "verification_required": "瑙﹀彂楠岃瘉",
    "content_fetch_failed": "鏂囩珷鍐呭鑾峰彇澶辫触",
}


class WebhookNotifier:

    def __init__(self):
        self._last_notification: Dict[str, float] = {}
        self._notification_interval = int(
            os.getenv("WEBHOOK_NOTIFICATION_INTERVAL", "300")
        )

    @property
    def webhook_url(self) -> str:
        """姣忔璇诲彇鏃朵粠 .env 鍒锋柊锛岀‘淇濊繍琛屼腑淇敼閰嶇疆涔熻兘鐢熸晥"""
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            from dotenv import dotenv_values
            vals = dotenv_values(env_path)
            url = vals.get("WEBHOOK_URL", "")
        else:
            url = os.getenv("WEBHOOK_URL", "")
        return (url or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def _is_wecom(self, url: str) -> bool:
        return "qyapi.weixin.qq.com" in url

    def _build_payload(self, url: str, event: str, data: Dict) -> dict:
        """鏍规嵁 webhook 绫诲瀷鏋勯€犳秷鎭綋"""
        label = EVENT_LABELS.get(event, event)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [f"**{label}**", f"> {ts}"]
        for k, v in (data or {}).items():
            if v:
                lines.append(f"> {k}: {v}")

        if self._is_wecom(url):
            return {
                "msgtype": "markdown",
                "markdown": {"content": "\n".join(lines)},
            }

        return {
            "event": event,
            "timestamp": int(time.time()),
            "timestamp_str": ts,
            "message": "\n".join(lines),
            "data": data or {},
        }

    async def notify(self, event: str, data: Optional[Dict] = None) -> bool:
        url = self.webhook_url
        if not url:
            return False

        now = time.time()
        last = self._last_notification.get(event, 0)
        if now - last < self._notification_interval:
            logger.debug("Skip duplicate webhook: %s (%ds since last)", event, int(now - last))
            return False

        payload = self._build_payload(url, event, data or {})

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()

                ct = resp.headers.get("content-type", "")
                body = resp.json() if "json" in ct else {}
                errcode = body.get("errcode", 0)
                if errcode != 0:
                    errmsg = body.get("errmsg", "unknown")
                    logger.error("Webhook errcode=%s: %s", errcode, errmsg)
                    return False

            self._last_notification[event] = now
            logger.info("Webhook sent: %s", event)
            return True
        except Exception as e:
            logger.error("Webhook failed: %s - %s", event, e)
            return False


webhook = WebhookNotifier()

