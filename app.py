import streamlit as st
from search import search_products

st.set_page_config(
    page_title="AI Fashion Search",
    layout="wide"
)

st.title("AI Fashion Search")
st.caption("Semantic product discovery with intelligent fallback")

query = st.text_input(
    "What are you looking for?",
    placeholder="e.g. red kurti, office wear saree"
)


if st.button("Search") and query.strip():
    with st.spinner("Finding the best matches..."):
        results = search_products(query)

    if not results:
        st.warning("No results found.")
    else:
        if not results[0]["exact_match"]:
            st.info(
                "Exact filters are limited in the catalog. "
                "Showing the closest matching styles."
            )

        for i, item in enumerate(results, 1):
            col1, col2 = st.columns([1, 3])

            with col1:
                st.image(item["image"], use_container_width=True)

            with col2:
                st.subheader(f"{i}. {item['name']}")
                st.write(
                    f"""
                    💰 **Price:** ₹{item['price']}  
                    ⭐ **Rating:** {item['rating']}  
                    🔖 **Discount:** {item['discount']}%  
                    🏷️ **Seller:** {item['seller']}
                    """
                )

            st.divider()
