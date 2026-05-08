"""Streamlit signal search view."""
import streamlit as st
import sqlite3
from pathlib import Path

st.set_page_config(page_title="Signal Search", page_icon="📡")

st.title("Signal Search")

db_path = st.text_input("Database path", value="dcu_knowledge.db")
signal_name = st.text_input("Signal name")

if signal_name and db_path:
    db = Path(db_path)
    if db.exists():
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        signals = conn.execute(
            "SELECT * FROM signals WHERE name LIKE ? AND source_file IN "
            "(SELECT source_file FROM sources WHERE preferred = 1)",
            (f"%{signal_name}%",),
        ).fetchall()
        conn.close()
        st.write(f"Found {len(signals)} signals")
        for sig in signals:
            with st.expander(f"{sig['name']} (from {sig['source_file']})"):
                st.json(dict(sig))
    else:
        st.error(f"Database not found: {db_path}")
