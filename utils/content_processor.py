#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图文内容处理器 - 完美还原微信文章的图文混合内容
"""

import re
import logging
from typing import Dict, List
from urllib.parse import quote

logger = logging.getLogger(__name__)


def process_article_content(html: str, proxy_base_url: str = None) -> Dict:
    """
    处理文章内容，保持图文顺序并代理图片
    """
    # 1. 提取正文内容（保持原始 HTML 结构）
    content = extract_content(html)
    
    if not content:
        return {
            'content': '',
            'plain_content': '',
            'images': [],
            'has_images': False
        }
    
    # 2. 提取所有图片 URL（按顺序）
    images = extract_images_in_order(content)
    
    # 3. 代理图片 URL（保持 HTML 中的图片顺序）
    if proxy_base_url:
        content = proxy_all_images(content, proxy_base_url)
    
    # 4. 清理和优化 HTML (包含头像拦截和页脚剔除)
    content = clean_html(content)
    
    # 5. 移除 HTML 注释
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    # 6. 添加后端标记容器 (V8)，确保全量刷新
    content = f'<div class="wechat-backend-mark-v8" style="display:none;"></div><div class="wechat-backend-mark-container">{content}</div>'

    # 7. 生成纯文本 (供 AI 分析使用)
    plain_content = html_to_text(content)
    
    # 纯图片文章处理
    if not plain_content.strip() and images:
        plain_content = f"[纯图片文章，共 {len(images)} 张图片]"
    
    return {
        'content': content,
        'plain_content': plain_content,
        'images': images,
        'has_images': len(images) > 0
    }


def _extract_div_inner(html: str, open_tag_pattern: str) -> str:
    """
    Extract the inner HTML of a <div> matched by open_tag_pattern,
    correctly handling nested <div> tags by counting open/close depth.
    """
    m = re.search(open_tag_pattern, html, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""

    start = m.end()
    depth = 1
    pos = start
    open_re = re.compile(r'<div[\s>/]', re.IGNORECASE)
    close_re = re.compile(r'</div\s*>', re.IGNORECASE)

    while depth > 0 and pos < len(html):
        next_open = open_re.search(html, pos)
        next_close = close_re.search(html, pos)

        if next_close is None:
            break

        if next_open and next_open.start() < next_close.start():
            depth += 1
            pos = next_open.end()
        else:
            depth -= 1
            if depth == 0:
                return html[start:next_close.start()].strip()
            pos = next_close.end()

    return html[start:].strip()


def extract_content(html: str) -> str:
    """
    Extract article body, trying multiple container patterns.
    Different WeChat account types (government, media, personal) use
    different HTML structures. We try them in order of specificity.
    For image-text messages (item_show_type=8), short posts (item_show_type=10),
    and audio share pages (item_show_type=7), delegates to helpers.
    """
    try:
        from utils.helpers import (
            is_image_text_message, _extract_image_text_content,
            is_short_content_message, _extract_short_content,
            is_audio_message, _extract_audio_content,
            get_item_show_type, _extract_audio_share_content,
        )
    except ImportError:
        # Fallback if helpers are missing or broken
        def get_item_show_type(_): return None
        def is_image_text_message(_): return False
        def is_short_content_message(_): return False
        def is_audio_message(_): return False

    # Helper to wrap result with backend mark
    def wrap_with_mark(content):
        if not content: return ""
        return f'<div class="wechat-backend-mark" style="display:none;"></div>{content}'

    if get_item_show_type(html) == '7':
        result = _extract_audio_share_content(html)
        return wrap_with_mark(result.get('content', ''))

    if is_image_text_message(html):
        result = _extract_image_text_content(html)
        return wrap_with_mark(result.get('content', ''))

    if is_short_content_message(html):
        result = _extract_short_content(html)
        return wrap_with_mark(result.get('content', ''))

    if is_audio_message(html):
        result = _extract_audio_content(html)
        return wrap_with_mark(result.get('content', ''))

    # Pattern 1: id="js_content" (most common)
    content = _extract_div_inner(html, r'<div[^>]*\bid=["\']js_content["\'][^>]*>')

    # Pattern 2: class contains rich_media_content
    if not content:
        content = _extract_div_inner(html, r'<div[^>]*\bclass=["\'][^"\']*rich_media_content[^"\']*["\'][^>]*>')

    # Pattern 3: id="page-content" (government/institutional accounts)
    if not content:
        content = _extract_div_inner(html, r'<div[^>]*\bid=["\']page-content["\'][^>]*>')

    # Pattern 4: class contains rich_media_area_primary_inner
    if not content:
        content = _extract_div_inner(html, r'<div[^>]*\bclass=["\'][^"\']*rich_media_area_primary_inner[^"\']*["\'][^>]*>')

    # Pattern 5: Any div with id containing 'content'
    if not content:
        content = _extract_div_inner(html, r'<div[^>]*\bid=["\'][^"\']*content[^"\']*["\'][^>]*>')

    if content:
        return content

    logger.warning("Failed to extract article body from any known container")
    return ""


def extract_images_in_order(content: str) -> List[str]:
    """
    按顺序提取所有图片 URL
    
    微信文章的图片有两种属性：
    1. data-src（主要）- 懒加载图片
    2. src（备用）- 直接加载图片
    """
    images = []
    
    # 提取所有 <img> 标签（按 HTML 中的顺序）
    img_pattern = re.compile(r'<img[^>]*>', re.IGNORECASE)
    
    for img_tag in img_pattern.finditer(content):
        img_html = img_tag.group(0)
        
        # 优先提取 data-src
        data_src_match = re.search(r'data-src="([^"]+)"', img_html)
        if data_src_match:
            img_url = data_src_match.group(1)
            if is_valid_image_url(img_url) and img_url not in images:
                images.append(img_url)
            continue
        
        # 备用：提取 src
        src_match = re.search(r'src="([^"]+)"', img_html)
        if src_match:
            img_url = src_match.group(1)
            if is_valid_image_url(img_url) and img_url not in images:
                images.append(img_url)
    
    logger.info(f"提取到 {len(images)} 张图片（按顺序）")
    return images


def proxy_all_images(content: str, proxy_base_url: str) -> str:
    """
    代理所有图片 URL（保持 HTML 中的图片顺序）
    
    替换策略：
    1. 提取图片URL（data-src 或 src）
    2. 替换为代理URL
    3. 确保同时有 data-src 和 src 属性（RSS阅读器需要src）
    
    重要: RSS 阅读器需要 src 属性才能显示图片
    """
    
    def replace_img_tag(match):
        """替换单个 <img> 标签"""
        img_html = match.group(0)
        
        # 提取原始图片 URL（优先data-src，其次src）
        data_src_match = re.search(r'data-src="([^"]+)"', img_html, re.IGNORECASE)
        src_match = re.search(r'\ssrc="([^"]+)"', img_html, re.IGNORECASE)
        
        original_url = None
        if data_src_match:
            original_url = data_src_match.group(1)
        elif src_match:
            original_url = src_match.group(1)
        
        if not original_url or not is_valid_image_url(original_url):
            # [FIX] 如果是头像、图标或无效图片，直接返回空字符串，即从 HTML 中删除该标签
            return ""
        
        # 生成代理 URL
        proxy_url = f"{proxy_base_url}/api/image?url={quote(original_url, safe='')}"
        
        new_html = img_html
        
        # 第一步：替换 data-src（如果有）
        if data_src_match:
            new_html = re.sub(
                r'data-src="[^"]+"',
                f'data-src="{proxy_url}"',
                new_html,
                count=1,
                flags=re.IGNORECASE
            )
        
        # 第二步：处理 src 属性
        if src_match:
            # 已有 src，直接替换
            new_html = re.sub(
                r'\ssrc="[^"]+"',
                f' src="{proxy_url}"',
                new_html,
                count=1,
                flags=re.IGNORECASE
            )
        else:
            # 没有 src，必须添加（使用最简单可靠的方法）
            new_html = new_html.replace('<img', f'<img src="{proxy_url}"', 1)
            # 处理大写
            if 'src=' not in new_html:
                new_html = new_html.replace('<IMG', f'<IMG src="{proxy_url}"', 1)
        
        return new_html
    
    # 替换所有 <img> 标签
    content = re.sub(
        r'<img[^>]*>',
        replace_img_tag,
        content,
        flags=re.IGNORECASE
    )
    
    logger.info("图片 URL 已代理")
    return content


def is_valid_image_url(url: str) -> bool:
    """判断是否为有效的正文图片 URL，过滤掉头像和图标"""
    if not url:
        return False
    
    # 排除 base64 和无效 URL
    if url.startswith('data:'):
        return False
    
    # [NEW] 屏蔽头像域名和常见头像路径 (包括默认 SVG 头像)
    blacklist = ['qlogo.cn', 'mmhead', 'headimg', 'avatar', 'qrcode', 'logo', 'icon', 'avatar_default.svg']
    if any(b in url.lower() for b in blacklist):
        return False

    # 微信 CDN 域名
    wechat_cdn_domains = [
        'mmbiz.qpic.cn',
        'mmbiz.qlogo.cn',
        'wx.qlogo.cn',
        'res.wx.qq.com'
    ]
    return any(domain in url for domain in wechat_cdn_domains)


def clean_html(content: str) -> str:
    """清理和优化 HTML 结构，移除无关干扰项"""
    if not content:
        return ""
        
    # 1. 移除 <script> 标签
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. 移除常见的文章页脚、名片、关注区域、评论区（这些区域通常包含头像和二维码）
    footer_patterns = [
        r'<div[^>]*class=["\'][^"\']*(?:profile_container|author_profile-info|discuss_container|rich_media_extra|js_profile_qrcode|rich_media_tool|discuss_list)[^"\']*["\'][^>]*>.*?</div>',
        r'<div[^>]*id=["\'](?:js_pc_qr_code|js_author_profile|js_discuss_list|js_cmt_area)["\'][^>]*>.*?</div>',
        r'<span[^>]*class=["\'][^"\']*discuss_form_avatar[^"\']*["\'][^>]*>.*?</span>'
    ]
    for pattern in footer_patterns:
        content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)

    # 3. 拦截特定的默认 SVG 头像
    content = content.replace('https://res.wx.qq.com/t/fed_upload/937b4aa0-2cc5-42ec-81d7-e641da427fff/avatar_default.svg', '')
    
    # 4. 移除 HTML 标签中的 JavaScript 事件处理器 (如 onerror, onload, onclick)
    # 这类属性在 React 的 dangerouslySetInnerHTML 中可能会执行并导致崩溃或白屏
    content = re.sub(r'\son\w+=(["\']).*?\1', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\son\w+=[^\s>]+', '', content, flags=re.IGNORECASE)

    # 3. 移除 <style> 标签（可选，保留样式通常更好，除非样式冲突）
    # content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # 移除空段落
    content = re.sub(r'<p[^>]*>\s*</p>', '', content, flags=re.IGNORECASE)
    
    # 移除多余空白
    content = re.sub(r'\n\s*\n', '\n', content)
    
    return content.strip()


def html_to_text(html: str) -> str:
    """将 HTML 转为纯文本（移除图片，只保留文字）"""
    import html as html_module
    
    # 移除图片标签
    text = re.sub(r'<img[^>]*>', '', html, flags=re.IGNORECASE)
    
    # 移除其他标签
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(?:p|div|section|h[1-6])>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    
    # HTML 实体解码
    text = html_module.unescape(text)
    
    # 清理空白
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


# ==================== 使用示例 ====================

def example_usage():
    """使用示例"""
    
    # 假设这是从微信获取的原始 HTML
    original_html = """
    <html>
    <body>
    <div id="js_content">
        <p>这是第一段文字</p>
        <p><img data-src="https://mmbiz.qpic.cn/image1.jpg" /></p>
        <p>这是第二段文字</p>
        <p><img data-src="https://mmbiz.qpic.cn/image2.jpg" /></p>
        <p>这是第三段文字</p>
    </div>
    </body>
    </html>
    """
    
    # 处理内容
    result = process_article_content(
        html=original_html,
        proxy_base_url="https://wechatrss.waytomaster.com"
    )
    
    print("处理后的 HTML:")
    print(result['content'])
    print("\n图片列表（按顺序）:")
    for i, img in enumerate(result['images'], 1):
        print(f"  {i}. {img}")
    
    print("\n纯文本:")
    print(result['plain_content'])


if __name__ == "__main__":
    example_usage()
