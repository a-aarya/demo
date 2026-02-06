# ingest.py
import pandas as pd
import psycopg2
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import os
from tqdm import tqdm

load_dotenv()

DB_NAME = os.getenv("DB_NAME", "testdb")
DB_USER = os.getenv("DB_USER", "aaryagodbole")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

CSV_FILE = "FashionDataset.csv"  
SAMPLE_SIZE = 2000              


model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")


df = pd.read_csv(CSV_FILE)
df.columns = [c.strip() for c in df.columns]
if SAMPLE_SIZE:
    df = df.head(SAMPLE_SIZE)


required_cols = ["p_id", "name", "price", "colour", "brand", "img",
                 "ratingCount", "avg_rating", "description", "p_attributes"]
missing = [c for c in required_cols if c not in df.columns]
if missing:
    raise SystemExit(f"Missing columns in CSV: {missing}")

# Connect to DB
conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASS,
    host=DB_HOST,
    port=DB_PORT,
    sslmode="require"   
)

cur = conn.cursor()


cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
conn.commit()

# create table (clean start)
cur.execute("DROP TABLE IF EXISTS myntra_products;")
cur.execute("""
CREATE TABLE myntra_products (
    product_id TEXT PRIMARY KEY,
    name TEXT,
    price INT,
    colour TEXT,
    brand TEXT,
    img TEXT,
    rating_count INT,
    avg_rating FLOAT,
    description TEXT,
    attributes TEXT,
    embedding VECTOR(768)
);
""")
conn.commit()

# Insert with embeddings
for _, row in tqdm(df.iterrows(), total=len(df)):
    # build semantic text from name + description + attributes
    text_for_embedding = " ".join([
        str(row.get("name", "")),
        str(row.get("description", "")),
        str(row.get("p_attributes", ""))
    ]).strip()

    embedding = model.encode(text_for_embedding).tolist()

    cur.execute("""
        INSERT INTO myntra_products
        (product_id, name, price, colour, brand, img, rating_count,
        avg_rating, description, attributes, embedding)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (product_id) DO NOTHING;
    """, (
        str(row["p_id"]),
        row["name"],
        int(row["price"]) if not pd.isna(row["price"]) else None,
        str(row["colour"]).lower() if not pd.isna(row["colour"]) else None,
        row["brand"],
        row["img"],
        int(row["ratingCount"]) if not pd.isna(row["ratingCount"]) else 0,
        float(row["avg_rating"]) if not pd.isna(row["avg_rating"]) else 0.0,
        row.get("description", ""),
        row.get("p_attributes", ""),
        embedding
    ))

conn.commit()
cur.close()
conn.close()

print("Fashion dataset ingested successfully (sample size: {})".format(len(df)))