import streamlit as st
import time
import os
from search import search_products
from llm_client import get_router_decision, generate_chat_response
from dotenv import load_dotenv
import re




load_dotenv()

# --- 1. Page Config & CSS ---
st.set_page_config(page_title="AI Fashion Stylist", layout="wide")

st.markdown("""
<style>
    /* smooth fade-in animation */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .main-card {
        animation: fadeIn 0.8s ease-out forwards;
    }
    .stImage img {
        object-fit: cover;
        height: 300px !important;
        border-radius: 8px;
    }
    .price-tag { font-size: 20px; font-weight: 700; color: #4ADE80; }
    .rating-text { color: #FACC15; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

def extract_quantity(text, default=6, max_limit=15):
    match = re.search(r"\b(\d+)\b", text)
    if match:
        qty = int(match.group(1))
        return min(qty, max_limit)
    return default

st.title("🛍️ AI Fashion Stylist")

# --- 2. Compact Render Card ---
def render_card(item):
    img_url = item.get("img") or item.get("image")

    if not img_url or str(img_url).lower() == "nan":
        img_url = "https://via.placeholder.com/300x400?text=No+Image"

    # Inka stylish border container
    with st.container(border=True):
        st.image(img_url, use_container_width=True)
        name = item.get('name', 'Product')
        st.markdown(f"**{name}**")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"<span class='price-tag'>₹{item.get('price')}</span>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<span class='rating-text'>⭐ {item.get('avg_rating', 0)}</span>", unsafe_allow_html=True)
        st.caption(f"{item.get('brand')} | {item.get('colour', 'N/A').title()}")

# --- 3. Chat Logic with Slow Reveal ---

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({"role": "assistant", "content": "Hi! Ready to find some styles?", "results": []})

# Render History (Normal speed)
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("results"):
            cols = st.columns(3)
            for idx, item in enumerate(msg["results"]):
                with cols[idx % 3]:
                    render_card(item)

# New Input
if prompt := st.chat_input("Type here..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append(
        {"role": "user", "content": prompt, "results": []}
    )

    # ---------- Reference Resolution ----------
    ordinal_map = {
        "first": 0, "1st": 0,
        "second": 1, "2nd": 1,
        "third": 2, "3rd": 2,
        "fourth": 3, "4th": 3,
        "fifth": 4, "5th": 4,
        "sixth": 5, "6th": 5,
    }

    lower_prompt = prompt.lower()

    if "last_results" in st.session_state:
        for key, idx in ordinal_map.items():
            if key in lower_prompt:
                try:
                    product = st.session_state.last_results[idx]

                    detail_text = f"""
**{product['name']}**

• Brand: {product['brand']}
• Color: {product['colour']}
• Price: ₹{product['price']}
**Rating:** ⭐ {round(product.get('avg_rating', 0), 1)}


Would you like to buy this or compare it with another?
"""
                    with st.chat_message("assistant"):
                        st.markdown(detail_text)

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": detail_text,
                        "results": []
                    })
                    st.stop()
                except:
                    pass

    # ---------- Normal Routing ----------
    with st.chat_message("assistant"):
        route = get_router_decision(prompt)

        if route == "CHAT":
            response_text = generate_chat_response(prompt, st.session_state.messages)
            st.markdown(response_text)

            st.session_state.messages.append(
                {"role": "assistant", "content": response_text, "results": []}
            )

        else:
            with st.spinner("Searching..."):
                k = extract_quantity(prompt)
                results = search_products(prompt, top_k=k)

            st.session_state.last_results = results

            st.markdown("Here are the best matches I found:")

            if results:
                grid_cols = st.columns(3)
                for idx, item in enumerate(results):
                    time.sleep(0.3)
                    with grid_cols[idx % 3]:
                        render_card(item)

            st.session_state.messages.append(
                {"role": "assistant", "content": "Here are the top matches:", "results": results}
            )
