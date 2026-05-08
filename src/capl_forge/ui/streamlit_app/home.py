"""Streamlit home page."""
import streamlit as st

st.set_page_config(page_title="CAPL Forge", page_icon="🔧")

st.title("CAPL Forge")
st.caption("CANoe Project Knowledge Extraction and Resolution System")

st.markdown("## Module 1: Knowledge Extraction")
st.markdown("- **Signal context** lookup")
st.markdown("- **DID browser** for diagnostic identifiers")
st.markdown("- **Sysvar browser** for system variables")
st.markdown("- **Env var browser** for environment variables")
st.markdown("- **Statistics and provenance**")

st.markdown("---")
st.markdown("Use the sidebar to navigate between views.")
