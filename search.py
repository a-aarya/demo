import chromadb
from sentence_transformers import SentenceTransformer
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
import os

# ---------- CONFIG ----------
MISTRAL_API_KEY = os.getenv("")

client_llm = MistralClient(api_key=MISTRAL_API_KEY)

# ChromaDB
client = chromadb.Client()
collection = client.get_collection("fashion_products")

# Embedding model (lightweight)
model = SentenceTransformer("all-MiniLM-L6-v2")

# ---------- QUERY REWRITE ----------
def rewrite_query(query: str) -> str:
    messages = [
        ChatMessage(
            role="system",
            content=(
                "You rewrite fashion search queries to be more descriptive "
                "for semantic product retrieval. Do not invent attributes."
            )
        ),
        ChatMessage(role="user", content=query)
    ]

    response = client_llm.chat(
        model="mistral-small-latest",
        messages=messages,
        temperature=0.2
    )

    return response.choices[0].message.content.strip()

# ---------- SEARCH ----------
def search_products(query: str):
    # 1. Rewrite query
    enriched_query = rewrite_query(query)

    # 2. Embed query
    query_embedding = model.encode(enriched_query).tolist()

    # 3. Vector search
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=10
    )

    # 4. Ranking
    ranked = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i]

        score = (
            0.6 * (1 - distance) +
            0.2 * meta.get("rating", 0) +
            0.2 * (meta.get("discount", 0) / 100)
        )

        ranked.append({
            "score": round(score, 3),
            "price": meta["price"],
            "rating": meta["rating"],
            "discount": meta["discount"],
            "seller": meta["seller"],
            "url": meta["url"],
            "image": meta["image"]
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:5]
