class ProxyPool:
    def __init__(self): self.count = 0
    def next(self): return None
    def mark_ok(self, p): pass
    def mark_failed(self, p): pass
    def get_status(self): return {"count": 0}
proxy_pool = ProxyPool()
