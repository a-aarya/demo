# gemini_client.py
import os
import json
import functools
import logging
from typing import Dict, Optional


try:
    from google import genai
except Exception:
    genai = None

# Configure logging
logger = logging.getLogger("gemini_client")
logger.setLevel(logging.INFO)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 


_client_available = False
if genai is not None:
    try:
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
        _client_available = True
        logger.info("Gemini SDK available")
    except Exception as e:
        logger.warning("Gemini SDK present but failed to configure: %s", e)
        _client_available = False
else:
    logger.info("google-generative-ai (genai) SDK not installed; Gemini disabled.")


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5")  

@functools.lru_cache(maxsize=512)
def _call_gemini(prompt: str, max_output_tokens: int = 256) -> Optional[str]:
    """
    Internal helper: call the Gemini SDK to generate content.
    Returns string text or None on failure.
    """
    if not _client_available:
        return None

    try:
        
        resp = genai.Client().models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            max_output_tokens=max_output_tokens
        )
   
        text = None
        try:
            text = resp.text
        except Exception:
        
            try:
                text = resp["candidates"][0]["content"][0]["text"]
            except Exception:
                text = str(resp)
        return text
    except Exception as e:
        logger.exception("Gemini call failed: %s", e)
        return None


def rewrite_query(query: str) -> str:
    """
    Return an enriched query optimized for semantic retrieval.
    Uses Gemini when available; otherwise returns a light local rewrite.
    """
    if not query or not query.strip():
        return query

    prompt = (
        "You are a helpful assistant that rewrites short fashion search queries into "
        "concise, descriptive search phrases suitable for semantic product retrieval. "
        "Do NOT invent attributes that are not present (e.g., do not add colors or materials unless asked). "
        "Keep it short (1-2 sentences). Output only the rewritten query.\n\n"
        f"User query: {query}\n\nRewritten:"
    )

    text = _call_gemini(prompt)
    if text:
        # clean result
        return text.strip().replace("\n", " ")
    # fallback: small local rewrite
    q = query.strip()
    if len(q.split()) < 3:
        # if short, expand with simple safe patterns
        return f"{q} for women" if "women" not in q.lower() and "men" not in q.lower() else q
    return q

def extract_intent(query: str) -> Dict:
    """
    Use Gemini to extract structured intent from query.
    Returns a dict with keys possibly: color, category, max_price, min_price, gender, occasion, raw_query.
    values are strings or numbers or None.
    If Gemini not available, fall back to local rule extraction.
    """
    if not query or not query.strip():
        return {"raw_query": query}

    prompt = (
        "Extract JSON from the user's fashion search query with these fields:\n"
        " - color (a simple color name or null)\n"
        " - category (kurti/saree/dress/shirt/belt/jeans/jacket or null)\n"
        " - max_price (number in INR or null)\n"
        " - min_price (number in INR or null)\n"
        " - gender (male/female/unisex/null)\n"
        "Return EXACTLY a single JSON object only (no extra text). Use lowercase color/category, numbers for prices or null.\n\n"
        f"User query: {query}\n\nJSON:"
    )

    text = _call_gemini(prompt, max_output_tokens=200)
    if text:
        # Try to parse JSON from the response
        try:
            # find first '{' to last '}' to be robust if SDK adds surrounding text
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                jtext = text[start:end+1]
                parsed = json.loads(jtext)
                # normalize keys
                return {
                    "color": parsed.get("color"),
                    "category": parsed.get("category"),
                    "max_price": parsed.get("max_price"),
                    "min_price": parsed.get("min_price"),
                    "gender": parsed.get("gender"),
                    "raw_query": query
                }
        except Exception as e:
            logger.warning("Failed to parse Gemini intent JSON: %s ; raw response: %s", e, text)

    # Fallback simple extractor (rule-based)
    q = query.lower()
    # color
    color = None
    for c in ["black","white","red","blue","green","yellow","pink","brown","grey","maroon","beige","orange"]:
        if f" {c}" in f" {q}":
            color = c
            break
    # category
    category = None
    for cat, keys in {
        "kurti": ["kurti", "kurta"],
        "saree": ["saree"],
        "dress": ["dress"],
        "shirt": ["shirt", "t-shirt", "tee"],
        "belt": ["belt"],
        "jeans": ["jean","jeans"],
        "jacket": ["jacket","coat"]
    }.items():
        for k in keys:
            if k in q:
                category = cat
                break
        if category:
            break
    # prices
    import re
    nums = [int(n.replace(",","")) for n in re.findall(r"\b\d{2,7}\b", q)]
    max_price = None
    min_price = None
    if nums:
        # heuristics: if user wrote 'under 3000' or 'below 3000' then set max
        if "under" in q or "below" in q or "less than" in q or "upto" in q or "up to" in q:
            max_price = nums[-1]
        elif "between" in q and len(nums) >= 2:
            min_price, max_price = nums[0], nums[1]
        else:
            # assume max price if single number
            max_price = nums[-1]

    gender = None
    if "women" in q or "female" in q or "girl" in q:
        gender = "female"
    elif "men" in q or "male" in q or "boy" in q:
        gender = "male"

    return {
        "color": color,
        "category": category,
        "max_price": max_price,
        "min_price": min_price,
        "gender": gender,
        "raw_query": query
    }
