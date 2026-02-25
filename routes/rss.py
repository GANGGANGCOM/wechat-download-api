#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 tmwgsicp
# Licensed under the GNU Affero General Public License v3.0
# See LICENSE file in the project root for full license text.
# SPDX-License-Identifier: AGPL-3.0-only
"""
RSS 订阅路由
订阅管理 + RSS XML 输出
"""

import time
import logging
from datetime import datetime, timezone
from html import escape as html_escape
from urllib.parse import quote
from xml.etree.ElementTree import Element, SubElement, tostring
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from utils import rss_store
from utils.rss_poller import rss_poller, POLL_INTERVAL

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic models ──────────────────────────────────────

class SubscribeRequest(BaseModel):
    fakeid: str = Field(..., description="公众号 FakeID")
    nickname: str = Field("", description="公众号名称")
    alias: str = Field("", description="公众号微信号")
    head_img: str = Field("", description="头像 URL")


class SubscribeResponse(BaseModel):
    success: bool
    message: str = ""


class SubscriptionItem(BaseModel):
    fakeid: str
    nickname: str
    alias: str
    head_img: str
    created_at: int
    last_poll: int
    article_count: int = 0
    rss_url: str = ""


class SubscriptionListResponse(BaseModel):
    success: bool
    data: list = []


class PollerStatusResponse(BaseModel):
    success: bool
    data: dict = {}


# ── 订阅管理 ─────────────────────────────────────────────

@router.post("/rss/subscribe", response_model=SubscribeResponse, summary="添加 RSS 订阅")
async def subscribe(req: SubscribeRequest, request: Request):
    """
    添加一个公众号到 RSS 订阅列表。

    添加后，后台轮询器会定时拉取该公众号的最新文章。

    **请求体参数：**
    - **fakeid** (必填): 公众号 FakeID，通过搜索接口获取
    - **nickname** (可选): 公众号名称
    - **alias** (可选): 公众号微信号
    - **head_img** (可选): 公众号头像 URL
    """
    added = rss_store.add_subscription(
        fakeid=req.fakeid,
        nickname=req.nickname,
        alias=req.alias,
        head_img=req.head_img,
    )
    if added:
        logger.info("RSS subscription added: %s (%s)", req.nickname, req.fakeid[:8])
        return SubscribeResponse(success=True, message="订阅成功")
    return SubscribeResponse(success=True, message="已订阅，无需重复添加")


@router.delete("/rss/subscribe/{fakeid}", response_model=SubscribeResponse,
               summary="取消 RSS 订阅")
async def unsubscribe(fakeid: str):
    """
    取消订阅一个公众号，同时删除该公众号的缓存文章。

    **路径参数：**
    - **fakeid**: 公众号 FakeID
    """
    removed = rss_store.remove_subscription(fakeid)
    if removed:
        logger.info("RSS subscription removed: %s", fakeid[:8])
        return SubscribeResponse(success=True, message="已取消订阅")
    return SubscribeResponse(success=False, message="未找到该订阅")


@router.get("/rss/subscriptions", response_model=SubscriptionListResponse,
            summary="获取订阅列表")
async def get_subscriptions(request: Request):
    """
    获取当前所有 RSS 订阅的公众号列表。

    返回每个订阅的基本信息、缓存文章数和 RSS 地址。
    """
    subs = rss_store.list_subscriptions()
    base_url = str(request.base_url).rstrip("/")

    items = []
    for s in subs:
        items.append({
            **s,
            "rss_url": f"{base_url}/api/rss/{s['fakeid']}",
        })

    return SubscriptionListResponse(success=True, data=items)


@router.post("/rss/poll", response_model=PollerStatusResponse,
             summary="手动触发轮询")
async def trigger_poll():
    """
    手动触发一次轮询，立即拉取所有订阅公众号的最新文章。

    通常用于首次订阅后立即获取文章，无需等待下一个轮询周期。
    """
    if not rss_poller.is_running:
        return PollerStatusResponse(
            success=False,
            data={"message": "轮询器未启动"}
        )
    try:
        await rss_poller.poll_now()
        return PollerStatusResponse(
            success=True,
            data={"message": "轮询完成"}
        )
    except Exception as e:
        return PollerStatusResponse(
            success=False,
            data={"message": f"轮询出错: {str(e)}"}
        )


@router.get("/rss/status", response_model=PollerStatusResponse,
            summary="轮询器状态")
async def poller_status():
    """
    获取 RSS 轮询器运行状态。
    """
    subs = rss_store.list_subscriptions()
    return PollerStatusResponse(
        success=True,
        data={
            "running": rss_poller.is_running,
            "poll_interval": POLL_INTERVAL,
            "subscription_count": len(subs),
        },
    )


# ── RSS XML 输出 ──────────────────────────────────────────

def _proxy_cover(url: str, base_url: str) -> str:
    """将微信 CDN 封面图地址替换为本服务的图片代理地址"""
    if url and "mmbiz.qpic.cn" in url:
        return base_url + "/api/image?url=" + quote(url, safe="")
    return url


def _rfc822(ts: int) -> str:
    """Unix 时间戳 → RFC 822 日期字符串"""
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _build_rss_xml(fakeid: str, sub: dict, articles: list,
                   base_url: str) -> str:
    rss = Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = sub.get("nickname") or fakeid
    SubElement(channel, "link").text = "https://mp.weixin.qq.com"
    SubElement(channel, "description").text = (
        f'{sub.get("nickname", "")} 的微信公众号文章 RSS 订阅'
    )
    SubElement(channel, "language").text = "zh-CN"
    SubElement(channel, "lastBuildDate").text = _rfc822(int(time.time()))
    SubElement(channel, "generator").text = "WeChat Download API"

    atom_link = SubElement(channel, "atom:link")
    atom_link.set("href", f"{base_url}/api/rss/{fakeid}")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    if sub.get("head_img"):
        image = SubElement(channel, "image")
        SubElement(image, "url").text = sub["head_img"]
        SubElement(image, "title").text = sub.get("nickname", "")
        SubElement(image, "link").text = "https://mp.weixin.qq.com"

    for a in articles:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = a.get("title", "")

        link = a.get("link", "")
        SubElement(item, "link").text = link

        guid = SubElement(item, "guid")
        guid.text = link
        guid.set("isPermaLink", "true")

        if a.get("publish_time"):
            SubElement(item, "pubDate").text = _rfc822(a["publish_time"])

        if a.get("author"):
            SubElement(item, "author").text = a["author"]

        cover = _proxy_cover(a.get("cover", ""), base_url)
        digest = html_escape(a.get("digest", "")) if a.get("digest") else ""
        author = html_escape(a.get("author", "")) if a.get("author") else ""
        title_escaped = html_escape(a.get("title", ""))

        html_parts = []
        if cover:
            html_parts.append(
                f'<div style="margin-bottom:12px">'
                f'<a href="{html_escape(link)}">'
                f'<img src="{html_escape(cover)}" alt="{title_escaped}" '
                f'style="max-width:100%;height:auto;border-radius:8px" />'
                f'</a></div>'
            )
        if digest:
            html_parts.append(
                f'<p style="color:#333;font-size:15px;line-height:1.8;'
                f'margin:0 0 16px">{digest}</p>'
            )
        if author:
            html_parts.append(
                f'<p style="color:#888;font-size:13px;margin:0 0 12px">'
                f'作者: {author}</p>'
            )
        html_parts.append(
            f'<p style="margin:0"><a href="{html_escape(link)}" '
            f'style="color:#1890ff;text-decoration:none;font-size:14px">'
            f'阅读原文 &rarr;</a></p>'
        )

        SubElement(item, "description").text = "\n".join(html_parts)

    xml_bytes = tostring(rss, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes


@router.get("/rss/{fakeid}", summary="获取 RSS 订阅源",
            response_class=Response)
async def get_rss_feed(fakeid: str, request: Request,
                       limit: int = Query(20, ge=1, le=100,
                                          description="文章数量上限")):
    """
    获取指定公众号的 RSS 2.0 订阅源（XML 格式）。

    将此地址添加到任何 RSS 阅读器即可订阅公众号文章。

    **路径参数：**
    - **fakeid**: 公众号 FakeID

    **查询参数：**
    - **limit** (可选): 返回文章数量上限，默认 20
    """
    sub = rss_store.get_subscription(fakeid)
    if not sub:
        raise HTTPException(status_code=404, detail="未找到该订阅，请先添加订阅")

    articles = rss_store.get_articles(fakeid, limit=limit)
    base_url = str(request.base_url).rstrip("/")
    xml = _build_rss_xml(fakeid, sub, articles, base_url)

    return Response(
        content=xml,
        media_type="application/rss+xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=600"},
    )
