# llm_client.py (Fixed & Complete)

import os
import json
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Logger Setup
logger = logging.getLogger("llm_client")
logger.setLevel(logging.ERROR)

# Client Setup
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.1-8b-instant"

def _safe_call(messages, max_tokens=200, temp=0.0, json_mode=False):
    """
    Centralized safe caller with strict temperature control.
    """
    try:
        kwargs = {
            "model": MODEL,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return None

def rewrite_query(query: str) -> str:
    """Optimizes the query WITHOUT adding categories not present."""
    system_prompt = (
        "You are a search query optimizer. "
        "Extract ONLY the fashion keywords. "
        "DO NOT assume a category (like kurta or dress) if the user did not mention one, ask user first"
        "If they only say a color, output only that color."
    )    
    res = _safe_call(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
        max_tokens=50,
        temp=0.0
    )
    return res.strip() if res else query

def get_router_decision(query: str) -> str:
    """
    Decides if the query is a 'SEARCH' or 'CHAT'.
    """
    system_prompt = (
        "You are a router. Analyze the user's input.\n"
        "If they mention items (dress, saree), colors, brands, or describe a look -> Output JSON: {\"route\": \"SEARCH\"}\n"
        "If they are just saying hello, thanks, or asking who you are -> Output JSON: {\"route\": \"CHAT\"}"
    )
    
    res = _safe_call(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
        max_tokens=20,
        temp=0.0,
        json_mode=True
    )
    
    try:
        return json.loads(res).get("route", "CHAT")
    except:
        return "SEARCH"

def extract_intent(query: str) -> dict:
    """
    Extracts structured filters from the query.
    """
    system_prompt = (
        "Extract search filters from the query into JSON.\n"
        "Fields: category (string), color (string), max_price (int), gender (string).\n"
        "If a field is missing, omit it."
    )
    
    res = _safe_call(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
        max_tokens=150,
        temp=0.0,
        json_mode=True
    )
    
    try:
        return json.loads(res)
    except:
        return {}

def generate_product_summary(query: str, products: list) -> str:
    """
    Summarizes REAL database results.
    """
    if not products:
        return "I checked our inventory, but I couldn't find an exact match. Could we try a different color?"

    context_str = "\n".join(
        [f"- {p['name']} ({p['brand']})" for p in products[:3]]
    )

    system_prompt = (
        "You are a professional boutique assistant.\n"
        "Summarize these products for the user. ONLY mention the products listed below.\n"
        "DO NOT mention brands not in the list."
    )

    prompt = f"User Query: {query}\n\nAvailable Products:\n{context_str}"

    res = _safe_call(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        max_tokens=200,
        temp=0.1
    )
    return res or "Here are the best matches I found for you."

def generate_chat_response(query: str) -> str:
    return _safe_call(
        [
            {"role": "system", "content": "You are a polite, professional fashion stylist assistant."},
            {"role": "user", "content": query}
        ],
        max_tokens=100
    )