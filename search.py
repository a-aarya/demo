import os
import psycopg2
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import streamlit as st

load_dotenv()


@st.cache_resource(show_spinner=False)
def load_model():
    return SentenceTransformer("sentence-transformers/all-mpnet-base-v2")


@st.cache_resource(show_spinner=False)
def get_db():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )


def extract_color(query: str):
    colors = [
        "black", "white", "red", "blue", "green",
        "yellow", "pink", "maroon", "beige", "brown", "grey"
    ]
    q = query.lower()
    for c in colors:
        if c in q:
            return c
    return None


def extract_category(query: str):
    categories = {
        "kurti": ["kurti", "kurta"],
        "saree": ["saree"],
        "belt": ["belt"],
        "dress": ["dress"]
    }
    q = query.lower()
    for cat, keys in categories.items():
        for k in keys:
            if k in q:
                return cat
    return None


def color_exists(conn, color: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM myntra_products WHERE color = %s;",
            (color,)
        )
        return cur.fetchone()[0] > 0



def search_products(query: str):
    model = load_model()
    conn = get_db()

    query_embedding = model.encode(query).tolist()
    color = extract_color(query)
    category = extract_category(query)

    rows = []
    exact_match = False

    with conn.cursor() as cur:

        
        if color and category and color_exists(conn, color):
            cur.execute("""
                SELECT name, img, price, rating, discount, seller,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM myntra_products
                WHERE color = %s AND LOWER(name) LIKE %s
                ORDER BY embedding <=> %s::vector
                LIMIT 5;
            """, (query_embedding, color, f"%{category}%", query_embedding))
            rows = cur.fetchall()
            exact_match = bool(rows)

        
        if not rows and category:
            cur.execute("""
                SELECT name, img, price, rating, discount, seller,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM myntra_products
                WHERE LOWER(name) LIKE %s
                ORDER BY embedding <=> %s::vector
                LIMIT 5;
            """, (query_embedding, f"%{category}%", query_embedding))
            rows = cur.fetchall()

      
        if not rows:
            cur.execute("""
                SELECT name, img, price, rating, discount, seller,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM myntra_products
                ORDER BY embedding <=> %s::vector
                LIMIT 5;
            """, (query_embedding, query_embedding))
            rows = cur.fetchall()

    results = []
    for r in rows:
        results.append({
            "name": r[0],
            "image": r[1],
            "price": r[2],
            "rating": r[3],
            "discount": r[4],
            "seller": r[5],
            "score": round(float(r[6]), 3),
            "exact_match": exact_match
        })

    return results
