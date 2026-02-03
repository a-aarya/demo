
import os
import json
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()  # expects your .env or env vars set

# DB config via env
DB_URL = os.getenv("DB_URL") or f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

CSV_PATH = os.getenv("CSV_PATH", "myntra_sample.csv")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", 768))
BATCH = int(os.getenv("INGEST_BATCH", 256))

TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS products (
  id serial PRIMARY KEY,
  product_id TEXT,         -- keep original id if available
  name TEXT,
  description TEXT,
  price NUMERIC,
  rating REAL,
  seller TEXT,
  color TEXT,
  metadata JSONB,
  embedding vector({EMBEDDING_DIM})
);
"""

INDEX_SQL = f"""
-- HNSW index tuned for cosine distance
CREATE INDEX IF NOT EXISTS products_embedding_hnsw
ON products USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);
"""

def infer_color(name: str):
    if not name:
        return None
    s = name.lower()
    for c in ["black","white","red","blue","green","yellow","pink","maroon","beige","brown","grey"]:
        if c in s:
            return c
    return None

def main():
    print("Loading embedding model:", EMBEDDING_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL)

    df = pd.read_csv(CSV_PATH).fillna("")
    n = len(df)
    print(f"Loaded {n} rows from {CSV_PATH}")

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # register vector type so psycopg2 accepts numpy arrays
    register_vector(conn)

    # enable extension + create table
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cur.execute(TABLE_SQL)
    conn.commit()

    inserted = 0
    for start in tqdm(range(0, n, BATCH), desc="ingest batches"):
        batch = df.iloc[start: start + BATCH]
        texts = (batch["name"].astype(str) + " | " + batch.get("category", "").astype(str) + " | " + batch.get("seller", "").astype(str)).tolist()
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        # normalize to unit length (important for cosine)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embeddings = (embeddings / norms).astype(np.float32)

        rows = []
        for i, (_, row) in enumerate(batch.iterrows()):
            meta = {
                "raw": row.to_dict()
            }
            rows.append((
                row.get("product_id", None),
                row.get("name", ""),
                row.get("description", ""),
                float(row["price"]) if str(row.get("price","")).strip() else None,
                float(row["rating"]) if str(row.get("rating","")).strip() else None,
                row.get("seller", ""),
                infer_color(row.get("name", "")),
                json.dumps(meta),
                embeddings[i]
            ))

        execute_values(
            cur,
            """
            INSERT INTO products
            (product_id, name, description, price, rating, seller, color, metadata, embedding)
            VALUES %s
            """,
            rows,
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        inserted += len(rows)

    print(f"Inserted {inserted} rows.")
    print("Creating HNSW index (this may take a while for large tables)...")
    cur.execute(INDEX_SQL)
    conn.commit()

    cur.close()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
