"""FastAPI endpoint package.

Routers are imported explicitly in web.main_web to avoid circular imports and
stale references when endpoint modules are added or removed.
"""
