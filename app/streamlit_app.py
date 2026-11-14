import streamlit as st

st.set_page_config(page_title="Flame in Freefall", page_icon="🔥", layout="wide")

st.title("Hello Flame in Freefall 🔥")
st.caption("NASA Space Apps 2026 — combustion en microgravité et sécurité incendie Lune/Mars")

explorer, gaps, next_exp, assistant = st.tabs(
    ["Explorer", "Carte des trous", "Prochaine expérience", "Assistant"]
)

with explorer:
    st.info("À venir : filtres expérience / matériau / O2 / gravité, table et graphiques.")

with gaps:
    st.info("À venir : nuage O2 × débit, scénario en marqueur, zones sans données.")

with next_exp:
    st.info("À venir : scénario → prédiction avec incertitude + recommandation d'expérience.")

with assistant:
    st.info("À venir : chat RAG avec sources citées.")
