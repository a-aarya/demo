# app.py
import streamlit as st
from search import search_products
from gemini_client import extract_intent
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="AI Fashion Search", layout="wide")

st.title("🛍️ AI Fashion Search")
st.caption(
    "Semantic + attribute-aware product search. "
    "Color and category are inferred automatically from the query."
)


n_results = st.slider("Number of results", min_value=3, max_value=12, value=8)
st.write("---")


query = st.text_input(
    "What are you looking for?",
    placeholder="e.g. red saree, black kurti, embroidered lehenga"
)

search_button = st.button("Search")


if search_button and query.strip():

   
    try:
        intent = extract_intent(query) or {}
        st.caption(
            f"Interpreted → "
            f"color: {intent.get('color')}, "
            f"category: {intent.get('category')}, "
            f"max_price: {intent.get('max_price')}, "
            f"min_price: {intent.get('min_price')}"
        )
    except Exception:
        st.caption("Interpreted → offline fallback")

    with st.spinner("Searching best matches..."):
        try:
            results = search_products(query, top_k=n_results)
        except Exception as e:
            st.error(f"Search failed: {e}")
            results = []

    if not results:
        st.warning("No results found. Try a different query.")
    else:
        if not results[0].get("exact_match", False):
            st.info("Exact filters were relaxed to improve recall.")

        
        for i, item in enumerate(results, start=1):
            col_img, col_txt = st.columns([1, 2])

            # Image
            with col_img:
                img_url = item.get("image")
                if img_url:
                    st.image(img_url, use_column_width=True)
                else:
                    st.image(
                        "https://assets.myntassets.com/h_720,q_90,w_540/v1/assets/images/default.jpg",
                        use_column_width=True
                    )

            # Text
            with col_txt:
                st.subheader(f"{i}. {item.get('name','Unnamed product')}")

                st.markdown(
                    f"""
                    **Brand:** {item.get('brand','N/A')}  
                    **Color:** {item.get('colour','N/A')}  
                    **Price:** ₹{item.get('price','N/A')}  
                    **Rating:** {item.get('avg_rating','N/A')} ({item.get('rating_count',0)} reviews)  
                    **Score:** {item.get('score')} (semantic: {item.get('similarity')})
                    """
                )

                desc = item.get("description")
                if desc:
                    st.markdown(f"📝 **Details:** {desc[:300]}...")

                if item.get("exact_match"):
                    st.caption("✔ Matches your requested color & category")
                else:
                    st.caption("≈ Closely matches your intent based on style & semantics")

            st.divider()

st.markdown("---")
st.caption("Built with Gemini + pgvector | Dataset: FashionDataset.csv (1k demo)")
