import os
import json
import logging
import re
import asyncio

try:
    from config import GEMINI_API_KEY, GEMINI_MODELS, CATEGORIES, CATEGORY_NAMES_FOR_AI
except ImportError:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-pro"]
    CATEGORIES = {}
    CATEGORY_NAMES_FOR_AI = {}

logger = logging.getLogger(__name__)

HAS_GEMINI = False
ai_client = None

try:
    if GEMINI_API_KEY:
        from google import genai
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        HAS_GEMINI = True
        logger.info("✅ Gemini AI ulanди!")
except ImportError:
    logger.warning("google-genai kutubxonasi topilmadi.")


# =====================================================
# KATEGORIYA ANIQLASH PROMPT
# =====================================================
def _build_category_prompt(text: str) -> str:
    cats_desc = "\n".join([f'- "{k}": {v}' for k, v in CATEGORY_NAMES_FOR_AI.items()])
    return f"""Siz O'zbekistondagi mahalla e'lonlar botining AI yordamchisisiz.
Quyidagi e'lon matnini o'qib, unga eng mos kategoriyani aniqlang.

KATEGORIYALAR:
{cats_desc}

E'LON MATNI: "{text}"

QOIDALAR:
1. FAQAT JSON qaytaring: {{"category": "...", "confidence": 0.95}}
2. "category" — yuqoridagi ro'yxatdan BITTA kalit (housing, food, grocery, hardware, services, entertainment, other)
3. "confidence" — 0.0 dan 1.0 gacha aniqlik darajasi
4. Agar aniq bo'lmasa "other" kategoriyasini bering

Javob (faqat JSON):"""


# =====================================================
# AI KATEGORIYA ANIQLASH (ASOSIY FUNKSIYA)
# =====================================================
async def detect_category(text: str) -> tuple[str, float]:
    """
    E'lon matnidan kategoriya aniqlaydи.
    Returns: (category_key, confidence)
    """
    if not text or not text.strip():
        return "other", 0.0

    if not HAS_GEMINI or not ai_client:
        return _simple_category_detect(text), 0.6

    prompt = _build_category_prompt(text)

    for model_name in GEMINI_MODELS:
        try:
            response = await asyncio.to_thread(
                ai_client.models.generate_content,
                model=model_name,
                contents=prompt
            )
            raw = response.text.strip()

            json_match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                category = result.get("category", "other")
                confidence = float(result.get("confidence", 0.7))

                if category not in CATEGORIES:
                    category = "other"

                logger.info(f"AI kategoriya: {category} (ishonch: {confidence:.0%})")
                return category, confidence

        except Exception as e:
            logger.warning(f"AI kategoriya ({model_name}): {e}")
            continue

    return _simple_category_detect(text), 0.5


# =====================================================
# AI TAVSIF YOZISH (KENGAYTIRISH)
# =====================================================
async def enhance_description(title: str, description: str, category: str) -> str:
    """
    Qisqa tavsifni AI yordamida kengaytiradi.
    """
    if not HAS_GEMINI or not ai_client:
        return description

    cat_name = CATEGORIES.get(category, {}).get("name", "")
    prompt = (
        f"E'lon sarlavhasi: '{title}'\n"
        f"Kategoriya: {cat_name}\n"
        f"Foydalanuvchi tavsifi: '{description}'\n\n"
        f"Ushbu mahalla e'loni uchun 2-3 jumladan iborat qisqa, aniq va jozibali tavsif yoz. "
        f"Faqat toza matn. Emoji ishlatma."
    )

    for model_name in GEMINI_MODELS[:2]:
        try:
            response = await asyncio.to_thread(
                ai_client.models.generate_content,
                model=model_name,
                contents=prompt
            )
            enhanced = response.text.strip()
            if enhanced and len(enhanced) > 10:
                return enhanced
        except Exception as e:
            logger.warning(f"Tavsif kengaytirish ({model_name}): {e}")
            continue

    return description


# =====================================================
# AI TAKLIF QO'SHIMCHA MA'LUMOT (SARLAVHA TAKLIF)
# =====================================================
async def suggest_title(description: str, category: str) -> str:
    """
    Tavsifdan qisqa sarlavha taklif qiladi.
    """
    if not HAS_GEMINI or not ai_client or not description:
        return ""

    cat_name = CATEGORIES.get(category, {}).get("name", "")
    prompt = (
        f"E'lon tavsifi: '{description}'\n"
        f"Kategoriya: {cat_name}\n\n"
        f"Ushbu e'lon uchun qisqa (5-8 so'z) sarlavha taklif qil. "
        f"Faqat sarlavhani yoz, boshqa hech narsa yozma."
    )

    for model_name in GEMINI_MODELS[:1]:
        try:
            response = await asyncio.to_thread(
                ai_client.models.generate_content,
                model=model_name,
                contents=prompt
            )
            return response.text.strip()
        except Exception:
            pass

    return ""


# =====================================================
# ODDIY KATEGORIYA ANIQLASH (AI ZAXIRA)
# =====================================================
def _simple_category_detect(text: str) -> str:
    text_lower = text.lower()

    food_keywords = [
        "restoran", "kafe", "choyxona", "taom", "ovqat", "plov",
        "shashlik", "lag'mon", "menyu", "non", "somsa", "dostavka",
        "yemoq", "taomnoma", "narxi", "burger", "pizza"
    ]
    housing_keywords = [
        "kvartira", "xona", "uy", "ijara", "sotuv", "komnata",
        "ijaraga", "sotiladi", "ipoteka", "muljal", "sotib"
    ]
    grocery_keywords = [
        "do'kon", "oziq", "ovqat", "mahsulot", "sabzavot",
        "meva", "sut", "go'sht", "non bakkal", "supermarket", "gipermarket"
    ]
    hardware_keywords = [
        "mebel", "stol", "stul", "divan", "shkaf", "karavot",
        "santexnika", "qurilish", "elektr", "usta", "ta'mirlash",
        "bo'yoq", "temir", "poliz", "yog'och"
    ]
    services_keywords = [
        "sartarosh", "naqqosh", "doch", "tikuv", "kosmetik",
        "shifokor", "tibbiy", "transport", "taksi", "ko'chirish",
        "xizmat", "ta'mir", "kompyuter", "telefon ta'mir"
    ]
    entertainment_keywords = [
        "o'yin", "bolalar", "sport", "kino", "konsert",
        "tennis", "futbol", "o'ynoqi", "bilyard", "karaoke"
    ]

    scores = {
        "food":          sum(1 for k in food_keywords          if k in text_lower),
        "housing":       sum(1 for k in housing_keywords       if k in text_lower),
        "grocery":       sum(1 for k in grocery_keywords       if k in text_lower),
        "hardware":      sum(1 for k in hardware_keywords      if k in text_lower),
        "services":      sum(1 for k in services_keywords      if k in text_lower),
        "entertainment": sum(1 for k in entertainment_keywords if k in text_lower),
    }

    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "other"