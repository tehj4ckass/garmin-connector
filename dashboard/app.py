import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
from dashboard_data import inject_custom_css

st.set_page_config(page_title="Garmin Dashboard", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
inject_custom_css()

pg = st.navigation([
    st.Page("Overview.py",                  title="📈 Übersicht"),
    st.Page("pages/2_Training.py",          title="🏃 Training"),
    st.Page("pages/3_Recovery.py",          title="😴 Erholung"),
    st.Page("pages/4_Correlations.py",      title="🔗 Zusammenhänge"),
    st.Page("pages/5_Activity_Detail.py",   title="🔍 Aktivitäts-Detail"),
    st.Page("pages/6_Data_Quality.py",      title="🧪 Datenqualität"),
])
pg.run()
