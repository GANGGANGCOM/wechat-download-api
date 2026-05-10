def proxy_image_url(url: str, base_url: str) -> str:
    if not url: return ""
    from urllib.parse import quote
    return f"{base_url}/api/image?url={quote(url)}"
