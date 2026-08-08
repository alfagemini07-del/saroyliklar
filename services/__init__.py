# services/__init__.py
from .ai_service    import detect_category, enhance_description
from .ad_service    import get_user, create_or_update_user, get_stats
from .place_service import create_place, get_user_place