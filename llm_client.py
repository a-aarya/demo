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
        "You are a shopping assistant if user asks any personal questions then politely refuse."
        "you are meant to answer only fashion related queries."
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
        "You are a strict router for a fashion shopping assistant.\n"
    "If the user mentions clothing items, fashion, colors, brands, outfits, styling -> SEARCH\n"
    "If the user greets or asks shopping-related help -> CHAT\n"
    "If the user talks about feelings, loneliness, life, relationships, emotions -> PERSONAL\n"
    "Respond ONLY in JSON like {\"route\": \"SEARCH\" | \"CHAT\" | \"PERSONAL\"}"
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
        "You are a fashion intent parser.\n"
    "Analyze the user's query and return JSON.\n\n"
    "Rules:\n"
    "- If the query mentions TWO clothing items together (e.g. 'jeans top', 'kurti jeans'),\n"
    "  treat it as a COMBINATION intent.\n"
    "- For combinations, return:\n"
    "  {\"primary_item\": \"top\", \"pair_with\": \"jeans\"}\n"
    "- For single items, return:\n"
    "  {\"category\": \"jeans\"}\n"
    "- Do NOT invent categories.\n"
    "- Output ONLY JSON."
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

def generate_chat_response(query: str, history: list) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a fashion assistant.\n"
"DO NOT assume products, brands, or selections unless explicitly chosen by the user.\n"
"Never invent fitting rooms, selections, or brand names.\n"
"If unsure, ask a clarification question."
"if user says i dont like the options then say 'I understand, fashion is very personal! Could you share more about what you're looking for or any specific preferences?'"

            )
        }
    ]

    # replay chat history
    for msg in history:
        if msg["role"] in ["user", "assistant"]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    # add latest user query
    messages.append({
        "role": "user",
        "content": query
    })

    return _safe_call(messages, max_tokens=100)

def get_clarification_plan(query: str) -> dict:
    """
    Detects vague shopping requests and returns targeted follow-up questions.
    """
    system_prompt = (
        "You are a fashion shopping clarification planner.\n"
        "Decide whether the user's request is too vague to run a good product search.\n"
        "If vague, ask short and specific follow-up questions.\n\n"
        "Return ONLY valid JSON with this shape:\n"
        "{\n"
        "  \"needs_clarification\": true|false,\n"
        "  \"questions\": [\"question 1\", \"question 2\"],\n"
        "  \"missing_fields\": [\"category\", \"color\"],\n"
        "  \"reason\": \"short reason\"\n"
        "}\n\n"
        "Rules:\n"
        "- Ask at most 4 questions.\n"
        "- Focus on practical filters: category/type, color, occasion, audience, budget.\n"
        "- For family/group shopping, include questions about who to shop for (adults/kids, gender split, count).\n"
        "- If request is specific enough, set needs_clarification to false and questions to [].\n"
        "- Fashion domain only."
    )

    res = _safe_call(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
        max_tokens=220,
        temp=0.0,
        json_mode=True
    )

    try:
        data = json.loads(res)
        questions = data.get("questions") or []
        if not isinstance(questions, list):
            questions = []
        return {
            "needs_clarification": bool(data.get("needs_clarification", False)) and bool(questions),
            "questions": [str(q).strip() for q in questions if str(q).strip()][:4],
            "missing_fields": data.get("missing_fields") or [],
            "reason": str(data.get("reason") or "").strip()
        }
    except Exception:
        return {
            "needs_clarification": False,
            "questions": [],
            "missing_fields": [],
            "reason": ""
        }

def build_refined_search_query(original_query: str, clarification_answers: str) -> str:
    """
    Combines original request + user clarification into a single searchable query.
    """
    system_prompt = (
        "You are a fashion shopping query refiner.\n"
        "Combine the original request and follow-up answers into one concise search query.\n"
        "Keep all concrete constraints (category, audience, occasion, color, budget, count).\n"
        "Do not invent missing facts.\n"
        "Output plain text only."
    )
    user_prompt = (
        f"Original request:\n{original_query}\n\n"
        f"Clarification answers:\n{clarification_answers}\n\n"
        "Return one final search query."
    )

    res = _safe_call(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        max_tokens=120,
        temp=0.0
    )
    return res.strip() if res else f"{original_query}. {clarification_answers}"
