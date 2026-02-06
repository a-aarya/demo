import streamlit as st
import time
import os
import re
from search import search_products
from llm_client import get_router_decision, generate_chat_response
from dotenv import load_dotenv

load_dotenv()

# --- 1. Page Config & Professional Dark CSS ---
st.set_page_config(page_title="AI Fashion Stylist", layout="wide")

st.markdown("""
<style>
    /* Absolute Dark Background */
    .stApp {
        background-color: #000000;
        color: #FFFFFF;
    }

    /* Smaller Flipkart/Amazon Style Card Container */
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
""", unsafe_allow_html=True)

# Helper: Format Rating
def format_rating(val):
    try: return f"{float(val):.1f}"
    except: return "0.0"

# Helper: Clean HTML description
def parse_description(text):
    if not text or str(text).lower() == "nan": return ["No details available."]
    clean = re.sub(r'<.*?>', '\n', text)
    return [line.strip() for line in clean.split('\n') if line.strip()]

def extract_quantity(text, default=6, max_limit=12):
    match = re.search(r"\b(\d+)\b", text)
    if match:
        qty = int(match.group(1))
        return min(qty, max_limit)
    return default

# --- 2. Compact Render Card (Fixed Arguments) ---
def render_card(item, idx, msg_idx):
    img_url = item.get("image") or item.get("img") or "https://via.placeholder.com/300x400?text=No+Image"
    rating = format_rating(item.get('avg_rating'))
    
    with st.container():
        st.markdown(f"""
            <div class="card-container">
                <div class="image-container"><img src="{img_url}"></div>
                <div class="card-content">
                    <div>
                        <p class="brand-name">{item.get('brand', 'FASHION')}</p>
                        <p class="product-title">{item.get('name', 'Product Name')}</p>
                    </div>
                    <div class="price-row">
                        <span class="price-val">₹{item.get('price', '0')}</span>
                        <span class="rating-badge">⭐ {rating}</span>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        # Unique key using msg_idx and idx prevents NameError and duplicate keys
        if st.button("🛒 Add to Cart", key=f"btn_cart_{msg_idx}_{idx}", use_container_width=True):
            st.toast(f"Added {item.get('brand')} to your cart! 🔥")

st.title("AI Fashion Concierge")

# --- 3. Session State & History ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "Welcome back. Looking for something specific?", 
        "results": [],
        "type": "chat"
    })

# Render Chat History (Persistent)
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
                st.image(p.get('image') or p.get('img'), use_container_width=True)
                if st.button("🛒 Add to Bag", key=f"det_cart_{m_idx}", type="primary", use_container_width=True):
                    st.success("Added to bag!")
            with col2:
                st.markdown(f"**Price: ₹{p['price']} | Rating: ⭐ {format_rating(p.get('avg_rating'))}**")
                desc = parse_description(p.get('description', ''))
                st.markdown("**Detailed Specifications:**")
                html_desc = "".join([f"<li>{line}</li>" for line in desc[:10]])
                st.markdown(f'<div class="desc-box"><ul>{html_desc}</ul></div>', unsafe_allow_html=True)

# Input Handling
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
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"### 🔍 Deep Dive: {product['brand']}\n{product['name']}",
                    "type": "details",
                    "product_data": product
                })
                st.rerun()

    if not resolved:
        with st.chat_message("assistant"):
            route = get_router_decision(prompt)
            if route == "CHAT":
                response = generate_chat_response(prompt, st.session_state.messages)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response, "results": [], "type": "chat"})
            else:
                with st.spinner("Searching inventory..."):
                    k = extract_quantity(prompt)
                    results = search_products(prompt, top_k=k)
                
                st.session_state.last_results = results
                msg_text = f"I've curated {len(results)} matches for you:"
                st.markdown(msg_text)
                
                # Render grid immediately
                cols = st.columns(4)
                current_msg_idx = len(st.session_state.messages)
                for i, item in enumerate(results):
                    with cols[i % 4]:
                        render_card(item, i, current_msg_idx)

                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": msg_text, 
                    "results": results,
                    "type": "chat"
                })