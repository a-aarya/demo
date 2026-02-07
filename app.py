import re

import streamlit as st
from dotenv import load_dotenv

from llm_client import (
    build_refined_search_query,
    generate_chat_response,
    get_clarification_plan,
    get_router_decision,
)
from search import search_products

load_dotenv()

st.set_page_config(page_title="AI Fashion Stylist", layout="wide")

st.markdown(
    """
<style>
    .stApp {
        background-color: #000000;
        color: #FFFFFF;
    }

    .card-container {
        display: flex;
        flex-direction: column;
        height: 420px;
        background: #111111;
        border: 1px solid #222222;
        border-radius: 8px;
        overflow: hidden;
        transition: transform 0.2s ease, border-color 0.2s ease;
        margin-bottom: 10px;
    }

    .card-container:hover {
        border-color: #4ADE80;
        transform: translateY(-5px);
        box-shadow: 0 4px 15px rgba(74, 222, 128, 0.1);
    }

    .image-container img {
        width: 100%;
        height: 250px !important;
        object-fit: cover;
    }

    .card-content {
        padding: 10px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        flex-grow: 1;
    }

    .brand-name {
        color: #878b94;
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        margin: 0;
    }

    .product-title {
        font-size: 13px;
        color: #FFFFFF;
        margin: 4px 0;
        height: 38px;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        line-height: 1.4;
    }

    .price-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .price-val {
        color: #4ADE80;
        font-size: 16px;
        font-weight: 800;
    }

    .rating-badge {
        background: #232f3e;
        color: #FACC15;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 11px;
    }

    .desc-box {
        background: #0D1117;
        border-left: 3px solid #4ADE80;
        padding: 12px;
        border-radius: 4px;
        font-size: 13px;
        color: #cbd5e0;
    }
</style>
""",
    unsafe_allow_html=True,
)


def format_rating(val):
    try:
        return f"{float(val):.1f}"
    except Exception:
        return "0.0"


def parse_description(text):
    if not text or str(text).lower() == "nan":
        return ["No details available."]
    clean = re.sub(r"<.*?>", "\n", text)
    return [line.strip() for line in clean.split("\n") if line.strip()]


def extract_quantity(text, default=6, max_limit=6):
    match = re.search(r"\b(\d+)\b", text or "")
    if match:
        qty = int(match.group(1))
        return min(qty, max_limit)
    return default


def format_clarification_message(questions, reason=""):
    question_lines = "\n".join([f"{idx + 1}. {q}" for idx, q in enumerate(questions)])
    prefix = "To narrow this down, I need a bit more detail."
    if reason:
        prefix = f"{prefix}\n{reason}"
    return f"{prefix}\n\n{question_lines}\n\nReply in one message and I will search immediately."


def has_enough_search_context(text):
    """
    Rule-based guard to avoid unnecessary repeated clarification rounds.
    """
    if not text:
        return False

    lowered = text.lower()
    tokens = re.findall(r"\b\w+\b", lowered)
    token_count = len(tokens)

    category_terms = {
        "saree", "sari", "kurti", "kurta", "dress", "gown", "shirt", "top",
        "tee", "blouse", "jeans", "denim", "jacket", "coat", "lehenga",
        "salwar", "suit", "tshirt", "t-shirt", "hoodie", "skirt", "pants",
        "trousers", "traditional", "ethnic", "western"
    }
    color_terms = {
        "red", "blue", "green", "white", "black", "grey", "gray", "pink",
        "purple", "orange", "yellow", "maroon", "navy", "beige", "brown"
    }
    audience_terms = {
        "men", "man", "male", "women", "woman", "female", "kids", "kid",
        "boy", "boys", "girl", "girls", "family", "adult", "adults"
    }
    occasion_terms = {
        "wedding", "party", "festival", "office", "casual", "formal",
        "college", "daily", "travel", "function", "engagement", "diwali", "eid"
    }

    has_category = any(term in lowered for term in category_terms)
    has_color = any(term in lowered for term in color_terms)
    has_audience = any(term in lowered for term in audience_terms)
    has_occasion = any(term in lowered for term in occasion_terms)
    has_budget = bool(re.search(r"\b(budget|under|below|between|rs|inr|rupee|rupees|\d{3,})\b", lowered))
    has_quantity = bool(re.search(r"\b\d+\b", lowered))

    if "family" in lowered:
        return (has_audience or has_quantity) and (has_category or has_color or has_occasion or has_budget)

    if has_category:
        return True

    details = sum([has_color, has_audience, has_occasion, has_budget, has_quantity])
    return token_count >= 6 and details >= 2


def render_card(item, idx, msg_idx):
    img_url = item.get("image") or item.get("img") or "https://via.placeholder.com/300x400?text=No+Image"
    rating = format_rating(item.get("avg_rating"))

    with st.container():
        st.markdown(
            f"""
            <div class="card-container">
                <div class="image-container"><img src="{img_url}"></div>
                <div class="card-content">
                    <div>
                        <p class="brand-name">{item.get("brand", "FASHION")}</p>
                        <p class="product-title">{item.get("name", "Product Name")}</p>
                    </div>
                    <div class="price-row">
                        <span class="price-val">Rs {item.get("price", "0")}</span>
                        <span class="rating-badge">Rating {rating}</span>
                    </div>
                </div>
            </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Add to Cart", key=f"btn_cart_{msg_idx}_{idx}", use_container_width=True):
            st.toast(f"Added {item.get('brand')} to your cart.")


def run_search_and_render(search_query):
    with st.spinner("Searching inventory..."):
        k = extract_quantity(search_query)
        results = search_products(search_query, top_k=k)

    if not results:
        no_result_msg = (
            "I could not find an exact match in our inventory.\n\n"
            "You can try:\n"
            "- A different category (for example: tops)\n"
            "- Changing style or color\n"
            "- Adjusting your budget\n\n"
            "What would you like to try next?"
        )
        st.markdown(no_result_msg)
        st.session_state.messages.append(
            {"role": "assistant", "content": no_result_msg, "results": [], "type": "chat"}
        )
        return

    st.session_state.last_results = results
    msg_text = f"I have curated {len(results)} matches for you:"
    st.markdown(msg_text)

    cols = st.columns(4)
    current_msg_idx = len(st.session_state.messages)
    for i, item in enumerate(results):
        with cols[i % 4]:
            render_card(item, i, current_msg_idx)

    st.session_state.messages.append(
        {"role": "assistant", "content": msg_text, "results": results, "type": "chat"}
    )


st.title("AI Fashion Assistant")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Welcome back. Looking for something specific?",
            "results": [],
            "type": "chat",
        }
    ]

if "pending_clarification" not in st.session_state:
    st.session_state.pending_clarification = None

for m_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        if msg.get("results"):
            cols = st.columns(4)
            for p_idx, item in enumerate(msg["results"]):
                with cols[p_idx % 4]:
                    render_card(item, p_idx, m_idx)

        if msg.get("type") == "details":
            p = msg["product_data"]
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(p.get("image") or p.get("img"), use_container_width=True)
                if st.button("Add to Bag", key=f"det_cart_{m_idx}", type="primary", use_container_width=True):
                    st.success("Added to bag.")
            with col2:
                st.markdown(f"**Price: Rs {p['price']} | Rating: {format_rating(p.get('avg_rating'))}**")
                desc = parse_description(p.get("description", ""))
                st.markdown("**Detailed Specifications:**")
                html_desc = "".join([f"<li>{line}</li>" for line in desc[:10]])
                st.markdown(f'<div class="desc-box"><ul>{html_desc}</ul></div>', unsafe_allow_html=True)


if prompt := st.chat_input("Search for styles or ask for '1st one details'"):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt, "results": [], "type": "chat"})

    lower_prompt = prompt.lower()
    ordinal_map = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3}

    resolved = False
    if "last_results" in st.session_state and any(x in lower_prompt for x in ordinal_map.keys()):
        for key, idx in ordinal_map.items():
            if key in lower_prompt and idx < len(st.session_state.last_results):
                product = st.session_state.last_results[idx]
                resolved = True
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": f"### Product details: {product['brand']}\n{product['name']}",
                        "type": "details",
                        "product_data": product,
                    }
                )
                st.rerun()

    if not resolved:
        with st.chat_message("assistant"):
            pending = st.session_state.get("pending_clarification")
            if pending:
                answers = pending.get("answers", [])
                answers.append(prompt)
                combined_answers = " ".join(answers).strip()
                original_query = pending.get("original_query", "")
                refined_query = build_refined_search_query(original_query, combined_answers)

                rounds = int(pending.get("rounds", 1))
                if has_enough_search_context(refined_query):
                    st.session_state.pending_clarification = None
                    ack_msg = "Thanks, that helps. Searching with those preferences now."
                    st.markdown(ack_msg)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": ack_msg, "results": [], "type": "chat"}
                    )
                    run_search_and_render(refined_query)
                else:
                    follow_up = get_clarification_plan(refined_query)
                    if follow_up.get("needs_clarification") and rounds < 2 and follow_up.get("questions"):
                        questions = follow_up.get("questions", [])[:3]
                        clarification_msg = format_clarification_message(questions, follow_up.get("reason", ""))
                        st.markdown(clarification_msg)
                        st.session_state.pending_clarification = {
                            "original_query": original_query,
                            "answers": answers,
                            "rounds": rounds + 1,
                        }
                        st.session_state.messages.append(
                            {"role": "assistant", "content": clarification_msg, "results": [], "type": "chat"}
                        )
                    else:
                        st.session_state.pending_clarification = None
                        ack_msg = "Thanks, that helps. Searching with those preferences now."
                        st.markdown(ack_msg)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": ack_msg, "results": [], "type": "chat"}
                        )
                        run_search_and_render(refined_query)
            else:
                route = get_router_decision(prompt)
                if route == "PERSONAL":
                    refusal_msg = (
                        "I can help with fashion and styling only.\n\n"
                        "If you want outfit ideas, colors, or shopping help, tell me what you need."
                    )
                    st.markdown(refusal_msg)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": refusal_msg, "results": [], "type": "chat"}
                    )
                elif route == "CHAT":
                    response = generate_chat_response(prompt, st.session_state.messages)
                    st.markdown(response)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": response, "results": [], "type": "chat"}
                    )
                else:
                    if has_enough_search_context(prompt):
                        run_search_and_render(prompt)
                    else:
                        clarification = get_clarification_plan(prompt)
                        if clarification.get("needs_clarification") and clarification.get("questions"):
                            clarification_msg = format_clarification_message(
                                clarification.get("questions", []), clarification.get("reason", "")
                            )
                            st.markdown(clarification_msg)
                            st.session_state.pending_clarification = {
                                "original_query": prompt,
                                "answers": [],
                                "rounds": 1,
                            }
                            st.session_state.messages.append(
                                {"role": "assistant", "content": clarification_msg, "results": [], "type": "chat"}
                            )
                        else:
                            run_search_and_render(prompt)
