import re
import json
import logging

logger = logging.getLogger(__name__)

def clean_html(html: str) -> str:
    if not html: return ""
    text = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    from html import unescape
    return unescape(text).strip()

def extract_params(url: str) -> dict:
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}

def has_article_content(html: str) -> bool:
    """Check if the HTML content looks like a valid WeChat article"""
    if not html: return False
    # Standard article
    if 'id="js_content"' in html or 'rich_media_content' in html:
        return True
    # Share pages / Short content
    if 'item_show_type' in html or 'window.cgiData' in html:
        return True
    return False

def is_article_unavailable(html: str) -> bool:
    """Check if the article is permanently unavailable (deleted, blocked)"""
    if not html: return False
    unavailable_markers = [
        "该内容已被发布者删除",
        "此内容因违规无法查看",
        "由内容质量原因",
        "已经因故无法查看",
        "该内容已过期"
    ]
    return any(marker in html for marker in unavailable_markers)

def get_item_show_type(html: str) -> str:
    """Extract item_show_type from WeChat HTML"""
    m = re.search(r'item_show_type\s*[:=]\s*["\']?(\d+)["\']?', html)
    return m.group(1) if m else None

def is_image_text_message(html: str) -> bool:
    """item_show_type=8 (Image-Text album)"""
    return get_item_show_type(html) == '8'

def is_short_content_message(html: str) -> bool:
    """item_show_type=10 (Short post / video account)"""
    return get_item_show_type(html) == '10'

def is_audio_message(html: str) -> bool:
    """Check if it's an audio message"""
    return 'id="js_audio_msg"' in html or 'voice_area' in html

def _extract_image_text_content(html: str) -> dict:
    """提取图片消息（Type 8）的内容和文字描述"""
    # 1. 提取文字描述
    desc = ""
    # 尝试多种模式提取描述
    patterns = [
        r'var\s+msg_desc\s*=\s*["\']([^"\']+)["\']',
        r'["\']?msg_desc["\']?\s*[:=]\s*JsDecode\(["\'](.*?)["\']\)',
        r'["\']?content_noencode["\']?\s*[:=]\s*JsDecode\(["\'](.*?)["\']\)',
        r'["\']?short_content["\']?\s*[:=]\s*["\']([^"\']+)["\']'
    ]
    for p in patterns:
        m = re.search(p, html, re.DOTALL)
        if m:
            desc = m.group(1)
            break

    # 2. 提取图片列表
    all_imgs = re.findall(r'data-src="([^"]+)"', html)
    if not all_imgs:
        all_imgs = re.findall(r'src="([^"]+)"', html)
    
    images = []
    # 过滤黑名单（头像、图标、二维码、默认占位图等）
    blacklist = [
        'mmhead', 'headimg', 'avatar', 'icon', 'qrcode', 'head_img', 
        'logo', 'menu', 'button', 'loading', 'placeholder', '/0?wx_fmt=',
        'qlogo.cn'
    ]
    for img in all_imgs:
        if not any(b in img.lower() for b in blacklist):
            if img not in images:
                images.append(img)
    # 3. 构造 HTML
    content = ""
    if desc:
        # 处理转义字符
        desc = desc.replace('\\x0a', '<br/>').replace('\\n', '<br/>')
        content += f'<div class="article-desc" style="margin-bottom:20px; font-size:16px; line-height:1.6; color:#333; background:#f9f9f9; padding:15px; border-left:4px solid #C09464;">{desc}</div>'
    
    for img in images:
        if 'mmbiz.qpic.cn' in img:
            content += f'<p style="text-align:center;"><img data-src="{img}" style="max-width:100%; border-radius:8px; margin-bottom:15px;" /></p>'
            
    return {'content': content, 'images': images}

def _extract_short_content(html: str) -> dict:
    """提取短内容/视频号动态（Type 10）的内容"""
    content = ""
    
    # 使用正则表达式直接提取，不依赖 json.loads (微信的 JS 对象不是标准 JSON)
    # 提取正文
    text = ""
    # 按照优先级尝试提取正文：content_noencode -> short_content -> title -> msg_title
    for field in ['content_noencode', 'short_content', 'title', 'msg_title']:
        pattern = rf'["\']?{field}["\']?\s*[:=]\s*(?:JsDecode\()?["\'](.*?)["\']\)?'
        m_text = re.search(pattern, html, re.DOTALL)
        if m_text:
            text = m_text.group(1)
            if text and len(text) > 5:
                break
    
    if text:
        # 处理微信特有的转义
        text = text.replace('\\x0a', '<br/>').replace('\\n', '<br/>')
        content = f'<div class="short-content" style="font-size:16px; line-height:1.8; color:#333; margin-bottom:20px;">{text}</div>'
    
    # 提取图片列表
    # 1. 优先从数据结构中找
    imgs = []
    img_list_match = re.search(r'img_list\s*:\s*\[(.*?)\]', html, re.DOTALL)
    if img_list_match:
        imgs = re.findall(r'["\'](http[^"\']+)["\']', img_list_match.group(1))
    
    # 2. 备选：从全文寻找 mmbiz 链接，但严格过滤黑名单
    if not imgs:
        # 同时匹配 qpic.cn 和 qlogo.cn (后者通常是头像)
        all_potential_imgs = re.findall(r'["\'](https?://(?:mmbiz\.qpic|wx\.qlogo)\.cn/[^"\']+)["\']', html)
        # 增强黑名单：封杀所有头像、图标、二维码相关特征
        blacklist = [
            'mmhead', 'headimg', 'avatar', 'icon', 'qrcode', 'head_img', 
            'logo', 'menu', 'button', 'loading', 'placeholder', '/0?wx_fmt=',
            'qlogo.cn' # 彻底封杀头像域名
        ]
        for img in all_potential_imgs:
            # 排除包含黑名单词汇的图片
            if not any(b in img.lower() for b in blacklist):
                if img not in imgs:
                    imgs.append(img)

    if imgs:
        # 只保留真正像正文图的内容，限制图片数量或进行二次校验
        for img in imgs:
            # 这里的样式可以根据需要调整，去掉多余的边距
            content += f'<p style="text-align:center;"><img data-src="{img}" style="max-width:100%; border-radius:8px; margin-top:15px;" /></p>'
            
    return {'content': content}

def _extract_audio_content(html: str) -> dict:
    """Extract audio message placeholder"""
    return {'content': '<p>[音频内容，暂不支持解析]</p>'}

def _extract_audio_share_content(html: str) -> dict:
    """Extract from audio share page (type 7)"""
    m = re.search(r'msg_title\s*=\s*["\']([^"\']+)["\']', html)
    title = m.group(1) if m else "音频分享"
    return {'content': f'<p>[音频分享: {title}]</p>'}
