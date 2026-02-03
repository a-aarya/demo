# search.py
import os
import re
import psycopg2
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from llm_client import rewrite_query, extract_intent
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
    "saree": ["saree", "sari", "drape", "pleats", "pallu", "zari", "border", "banarasi", "kanjeevaram", "silk saree"],
    "kurti": ["kurti","kurta","tunic"],
    "dress": ["dress","gown","one piece","anarkali"],
    "shirt": ["shirt","top","tee","blouse"],
    "jeans": ["jean","jeans","denim"],
    "jacket": ["jacket","coat"],
}

def clean_description(text: str, max_len: int = 300) -> str:
    if not text: return ""
    text = re.sub(r"<.*?>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."
    return text

@functools.lru_cache(maxsize=1)
def get_distinct_colours_from_db() -> List[str]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT TRIM(LOWER(colour)) FROM myntra_products WHERE COALESCE(colour,'') <> ''")
            return [r[0] for r in cur.fetchall() if r and r[0]]
    finally:
        conn.close()

def resolve_color_values(user_color: Optional[str]) -> Optional[List[str]]:
    if not user_color: return None
    uc = user_color.strip().lower()
    db_colors = get_distinct_colours_from_db()
    if uc in COLOR_FAMILY_MAP:
        return [c for c in COLOR_FAMILY_MAP[uc] if c in db_colors] or COLOR_FAMILY_MAP[uc]
    if uc in db_colors: return [uc]
    matches = difflib.get_close_matches(uc, db_colors, n=6, cutoff=0.6)
    return matches if matches else [uc]

def resolve_category_keywords(user_category: Optional[str]) -> List[str]:
    if not user_category: return []
    uc = user_category.strip().lower()
    return CATEGORY_ALIAS_MAP.get(uc, [uc])

def build_price_clause(max_price, min_price) -> Tuple[str, List]:
    parts = []
    params = []
    
    # Check if max_price exists and is actually a number/digit string
    if max_price is not None and str(max_price).isdigit():
        parts.append("price <= %s")
        params.append(int(max_price))
        
    # Check if min_price exists and is actually a number/digit string
    if min_price is not None and str(min_price).isdigit():
        parts.append("price >= %s")
        params.append(int(min_price))
        
    return (" AND " + " AND ".join(parts), params) if parts else ("", [])

def search_products(user_query: str, top_k: int = 8):
    try:
        intent = extract_intent(user_query) or {}
        rewritten = rewrite_query(user_query) or user_query
    except:
        intent, rewritten = {}, user_query

    color_intent = intent.get("color") or intent.get("colour")
    category_intent = intent.get("category")
    max_price, min_price = intent.get("max_price"), intent.get("min_price")

    query_embedding = get_model().encode(f"{user_query}. {rewritten}").tolist()
    color_values = resolve_color_values(color_intent)
    category_keywords = resolve_category_keywords(category_intent)

    conn = get_db()
    rows = []
    exact_filters_used = False
    relaxed_notice = None

    try:
        with conn.cursor() as cur:
            # 1. Strict Search
            if color_values and category_keywords:
                price_clause, price_params = build_price_clause(max_price, min_price)
                name_like = [f"%{kw}%" for kw in category_keywords]
                desc_like = [f"%{kw}%" for kw in category_keywords]
                sql = f"""
                   SELECT product_id, name, price, colour, brand, img, description, avg_rating, rating_count,
                   1 - (embedding <=> %s::vector) AS similarity,
                   (CASE WHEN ({" OR ".join(["LOWER(name) LIKE %s" for _ in name_like])} OR {" OR ".join(["LOWER(description) LIKE %s" for _ in desc_like])}) THEN 1 ELSE 0 END) AS category_match
                   FROM myntra_products WHERE colour = ANY(%s) {price_clause}
                   ORDER BY embedding <=> %s::vector LIMIT %s;
                """
                cur.execute(sql, [query_embedding] + name_like + desc_like + [color_values] + price_params + [query_embedding, top_k])
                rows = cur.fetchall()
                if rows: exact_filters_used = True

            # 2. Category Only
            if not rows and category_keywords:
                price_clause, price_params = build_price_clause(max_price, min_price)
                name_like = [f"%{kw}%" for kw in category_keywords]
                desc_like = [f"%{kw}%" for kw in category_keywords]
                sql = f"""
                   SELECT product_id, name, price, colour, brand, img, description, avg_rating, rating_count,
                   1 - (embedding <=> %s::vector) AS similarity,
                   (CASE WHEN ({" OR ".join(["LOWER(name) LIKE %s" for _ in name_like])} OR {" OR ".join(["LOWER(description) LIKE %s" for _ in desc_like])}) THEN 1 ELSE 0 END) AS category_match
                   FROM myntra_products WHERE TRUE {price_clause}
                   ORDER BY embedding <=> %s::vector LIMIT %s;
                """
                cur.execute(sql, [query_embedding] + name_like + desc_like + price_params + [query_embedding, top_k])
                rows = cur.fetchall()
                if rows: relaxed_notice = "No exact color matches—showing results for the style."

            # 3. Color Only
            if not rows and color_values:
                price_clause, price_params = build_price_clause(max_price, min_price)
                sql = f"""
                    SELECT product_id, name, price, colour, brand, img, description, avg_rating, rating_count,
                    1 - (embedding <=> %s::vector) AS similarity, 0 as category_match
                    FROM myntra_products WHERE colour = ANY(%s) {price_clause}
                    ORDER BY embedding <=> %s::vector LIMIT %s;
                """
                cur.execute(sql, [query_embedding, color_values] + price_params + [query_embedding, top_k])
                rows = cur.fetchall()

            # 4. Fallback
            if not rows:
                price_clause, price_params = build_price_clause(max_price, min_price)
                sql = f"""
                    SELECT product_id, name, price, colour, brand, img, description, avg_rating, rating_count,
                    1 - (embedding <=> %s::vector) AS similarity, 0 as category_match
                    FROM myntra_products WHERE TRUE {price_clause}
                    ORDER BY embedding <=> %s::vector LIMIT %s;
                """
                cur.execute(sql, [query_embedding] + price_params + [query_embedding, top_k])
                rows = cur.fetchall()
                relaxed_notice = "Showing the closest items I could find."

    finally:
        conn.close()

    results = []
    for r in rows:
        pid, name, price, col, brand, img, desc, avg_r, r_cnt, sim, cat_m = r
        sim = float(sim or 0.0)
        score = (0.6 * sim) + (0.3 * (1.0 if cat_m else 0.0)) + (0.1 * (min(float(r_cnt or 0)/500, 1.0)))
        results.append({
            "product_id": pid, "name": name, "price": price, "colour": col, "brand": brand,
            "image": img, "avg_rating": avg_r, "rating_count": r_cnt, "similarity": round(sim, 4),
            "score": round(score, 4), "exact_match": exact_filters_used,
            "relaxed_notice": relaxed_notice, "description": clean_description(desc)
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results