import streamlit as st
import time
import os
from search import search_products
from llm_client import get_router_decision, generate_chat_response
from dotenv import load_dotenv

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

st.title("🛍️ AI Fashion Stylist")

# --- 2. Compact Render Card ---
def render_card(item):
    img_url = item.get("image")
    if not img_url or str(img_url).lower() == "nan":
        img_url = "https://via.placeholder.com/300x400?text=No+Image"

    # Inka stylish border container
    with st.container(border=True):
        st.image(img_url, use_container_width=True)
        name = item.get('name', 'Product')
        st.markdown(f"**{name[:30]}...**")
        
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
    st.session_state.messages.append({"role": "user", "content": prompt, "results": []})

    with st.chat_message("assistant"):
        route = get_router_decision(prompt)
        results = []

        if route == "CHAT":
            response_text = generate_chat_response(prompt)
            st.markdown(response_text)
        else:
            with st.spinner("Searching..."):
                results = search_products(prompt, top_k=6)
            
            st.markdown("Here are the best matches I found:")
            
            # THE SLOW REVEAL LOGIC
            if results:
               
                grid_cols = st.columns(3)
                for idx, item in enumerate(results):
                   
                    time.sleep(0.3) 
                    with grid_cols[idx % 3]:
                        render_card(item)

    # Save to history
    st.session_state.messages.append({"role": "assistant", "content": "Here are the top matches:", "results": results})