# search.py
import os
import re
import psycopg2
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from gemini_client import rewrite_query, extract_intent
import streamlit as st
import difflib
import functools
from typing import List, Tuple, Optional

load_dotenv()

DB_NAME = os.getenv("DB_NAME", "testdb")
DB_USER = os.getenv("DB_USER", "aaryagodbole")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

@st.cache_resource(show_spinner=False)
def get_model():
    return SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

def get_db():
    return psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
    )

# --- alias maps (tune these to your dataset after you run diagnostics) ---
COLOR_FAMILY_MAP = {
    "red": ["red","maroon","magenta","rust","coral","peach"],
    "blue": ["blue","navy blue","turquoise blue","teal","sea green"],
    "green": ["green","olive","lime green","fluorescent green"],
    "white": ["white","off white"],
    "black": ["black","charcoal"],
    "grey": ["grey","gray"],
    "pink": ["pink","peach","lavender"],
    "purple": ["purple","magenta"],
    "orange": ["orange","rust"],
}

CATEGORY_ALIAS_MAP = {
    "saree": [
    "saree", "sari",
    "drape", "pleats", "pallu",
    "zari", "border",
    "banarasi", "kanjeevaram", "silk saree"
],

    "kurti": ["kurti","kurta","tunic"],
    "dress": ["dress","gown","one piece","anarkali"],
    "shirt": ["shirt","top","tee","blouse"],
    "jeans": ["jean","jeans","denim"],
    "jacket": ["jacket","coat"],
}

def clean_description(text: str, max_len: int = 300) -> str:
    if not text:
        return ""

    # remove HTML tags
    text = re.sub(r"<.*?>", " ", text)

    # normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # truncate for UI
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."

    return text



# cache DB distinct colours list (small)
@functools.lru_cache(maxsize=1)
def get_distinct_colours_from_db() -> List[str]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT TRIM(LOWER(colour)) FROM myntra_products WHERE COALESCE(colour,'') <> ''")
            rows = cur.fetchall()
            return [r[0] for r in rows if r and r[0]]
    finally:
        conn.close()

def normalize_keyword_list(keywords: List[str]) -> List[str]:
    return [re.sub(r'[^a-z0-9\s]', ' ', k.lower()).strip() for k in keywords if k]

def resolve_color_values(user_color: Optional[str]) -> Optional[List[str]]:
    if not user_color:
        return None
    uc = user_color.strip().lower()
    # if family name present
    if uc in COLOR_FAMILY_MAP:
        # return intersection with DB colours if available
        db_colors = get_distinct_colours_from_db()
        vals = [c for c in COLOR_FAMILY_MAP[uc] if c in db_colors]
        return vals or COLOR_FAMILY_MAP[uc]
    # if exact present in DB
    db_colors = get_distinct_colours_from_db()
    if uc in db_colors:
        return [uc]
    # fuzzy match to DB colours
    matches = difflib.get_close_matches(uc, db_colors, n=6, cutoff=0.6)
    if matches:
        return matches
    # try family membership
    for fam, members in COLOR_FAMILY_MAP.items():
        if any(uc == m or uc in m or m in uc for m in members):
            return [m for m in members if m in db_colors] or members
    return [uc]

def resolve_category_keywords(user_category: Optional[str]) -> List[str]:
    if not user_category:
        return []
    uc = user_category.strip().lower()
    if uc in CATEGORY_ALIAS_MAP:
        return CATEGORY_ALIAS_MAP[uc]
    # else return split tokens
    tokens = [t.strip() for t in re.split(r'[,/\s]+', uc) if t.strip()]
    return tokens or [uc]

def build_price_clause(max_price, min_price) -> Tuple[str, List]:
    parts = []
    params = []
    if max_price is not None:
        parts.append("price <= %s"); params.append(int(max_price))
    if min_price is not None:
        parts.append("price >= %s"); params.append(int(min_price))
    return (" AND " + " AND ".join(parts), params) if parts else ("", [])

def search_products(user_query: str, top_k: int = 8):
    # 1) intent
    try:
        intent = extract_intent(user_query) or {}
        rewritten = rewrite_query(user_query) or user_query
    except Exception:
        intent = {}
        rewritten = user_query

    color_intent = (intent.get("color") or intent.get("colour"))
    category_intent = intent.get("category")
    max_price = intent.get("max_price")
    min_price = intent.get("min_price")

    # 2) embedding
    model = get_model()
    query_embedding = model.encode(
    f"{user_query}. {rewritten}"
).tolist()


    # 3) resolve color/category keywords
    color_values = resolve_color_values(color_intent) if color_intent else None
    category_keywords = resolve_category_keywords(category_intent) if category_intent else []

    conn = get_db()
    rows = []
    exact_filters_used = False
    relaxed_notice = None

    try:
        with conn.cursor() as cur:
            # 1) Try strict color + category (if both present)
            if color_values and category_keywords:
                price_clause, price_params = build_price_clause(max_price, min_price)
                # build repeated LIKE params for name and description
                name_like = [f"%{kw}%" for kw in category_keywords]
                desc_like = [f"%{kw}%" for kw in category_keywords]
                like_name_clause = " OR ".join(["LOWER(name) LIKE %s" for _ in name_like])
                like_desc_clause = " OR ".join(["LOWER(description) LIKE %s" for _ in desc_like])

                sql = f"""
                   SELECT product_id, name, price, colour, brand, img, description,
       avg_rating, rating_count,
       1 - (embedding <=> %s::vector) AS similarity,
       (CASE WHEN ({like_name_clause} OR {like_desc_clause}) THEN 1 ELSE 0 END) AS category_match
FROM myntra_products
WHERE colour = ANY(%s)
ORDER BY embedding <=> %s::vector
LIMIT %s;

                """
                params = [query_embedding] + name_like + desc_like + [color_values] + price_params + [query_embedding, top_k]
                cur.execute(sql, params)
                rows = cur.fetchall()
                if rows:
                    exact_filters_used = True

            # 2) category-only (relax color)
            if not rows and category_keywords:
                price_clause, price_params = build_price_clause(max_price, min_price)
                name_like = [f"%{kw}%" for kw in category_keywords]
                desc_like = [f"%{kw}%" for kw in category_keywords]
                like_name_clause = " OR ".join(["LOWER(name) LIKE %s" for _ in name_like])
                like_desc_clause = " OR ".join(["LOWER(description) LIKE %s" for _ in desc_like])

                sql = f"""
                   SELECT product_id, name, price, colour, brand, img, description,
                   avg_rating, rating_count,
                   1 - (embedding <=> %s::vector) AS similarity,
                   (CASE WHEN ({like_name_clause} OR {like_desc_clause}) THEN 1 ELSE 0 END) AS category_match
                   FROM myntra_products
                   ORDER BY embedding <=> %s::vector
                LIMIT %s;

                """
                params = [query_embedding] + name_like + desc_like + price_params + [query_embedding, top_k]
                cur.execute(sql, params)
                rows = cur.fetchall()
                if rows:
                    relaxed_notice = "No exact color+category matches — showing category matches."

            # 3) color-only
            if not rows and color_values:
                price_clause, price_params = build_price_clause(max_price, min_price)
                sql = f"""
                    SELECT product_id, name, price, colour, brand, img, avg_rating, rating_count,
                           1 - (embedding <=> %s::vector) AS similarity,
                           (CASE WHEN (LOWER(name) LIKE %s OR LOWER(description) LIKE %s) THEN 1 ELSE 0 END) as category_match
                    FROM myntra_products
                    WHERE colour = ANY(%s)
                      {price_clause}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                """
                # category_like placeholders (pass something to satisfy select) - use empty patterns if no category
                cat_like_name = f"%{category_keywords[0]}%" if category_keywords else "%"
                cat_like_desc = cat_like_name
                params = [query_embedding, cat_like_name, cat_like_desc, color_values] + price_params + [query_embedding, top_k]
                cur.execute(sql, params)
                rows = cur.fetchall()
                if rows:
                    relaxed_notice = "No category match; showing colour-family matches."

            # 4) semantic fallback
            if not rows:
                price_clause, price_params = build_price_clause(max_price, min_price)
                sql = f"""
                    SELECT product_id, name, price, colour, brand, img, avg_rating, rating_count,
                           1 - (embedding <=> %s::vector) AS similarity,
                           0 as category_match
                    FROM myntra_products
                    WHERE TRUE {price_clause}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                """
                params = [query_embedding] + price_params + [query_embedding, top_k]
                cur.execute(sql, params)
                rows = cur.fetchall()
                if rows:
                    relaxed_notice = relaxed_notice or "No exact matches — showing semantic closest matches."
    finally:
        conn.close()

    # format results
    results = []
    for r in rows:
        # r: product_id, name, price, colour, brand, img, avg_rating, rating_count, similarity, category_match
        product_id, name, price, colour, brand, img, description, avg_rating, rating_count, similarity, category_match = r
        sim = float(similarity or 0.0)
        rating_norm = (float(avg_rating)/5.0) if avg_rating else 0.0
        pop_norm = min(float(rating_count)/500.0, 1.0) if rating_count else 0.0
        # Boost category_match modestly
        final_score = (
    0.60 * sim +
    0.30 * (1.0 if category_match else 0.0) +
    0.10 * (0.6*rating_norm + 0.4*pop_norm)
)
        

        results.append({
            "product_id": product_id,
            "name": name,
            "price": price,
            "colour": colour,
            "brand": brand,
            "image": img,
            "avg_rating": avg_rating,
            "rating_count": rating_count,
            "similarity": round(sim, 4),
            "score": round(final_score, 4),
            "exact_match": exact_filters_used,
            "relaxed_notice": relaxed_notice,
            "description": clean_description(description)

        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
