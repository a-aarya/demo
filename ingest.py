import pandas as pd
import chromadb
from sentence_transformers import SentenceTransformer

df = pd.read_csv("myntra202305041052.csv")

model = SentenceTransformer("all-MiniLM-L6-v2")

# ChromaDB
client = chromadb.Client()
collection = client.get_or_create_collection("fashion_products")

for _, row in df.iterrows():
    # Semantic text comes ONLY from name
    text = f"{row['name']} by {row['seller']}"

    embedding = model.encode(text).tolist()

    collection.add(
        ids=[str(row["id"])],
        documents=[text],
        embeddings=[embedding],
        metadatas=[{
            "price": float(row["price"]),
            "mrp": float(row["mrp"]),
            "discount": float(row["discount"]),
            "rating": float(row["rating"]),
            "ratingTotal": int(row["ratingTotal"]),
            "seller": row["seller"],
            "url": row["purl"],
            "image": row["img"]
        }]
    )

print("Ingestion complete")