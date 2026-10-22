"""Two workspaces: a beginner budget planner and the original research lab."""
import streamlit as st


def main():
    st.set_page_config(page_title="Roaring Returns | Start with your budget", page_icon="◈", layout="wide")
    st.radio("Workspace", ["Budget planner", "Research lab"], horizontal=True,
             key="workspace", label_visibility="collapsed")
    if st.session_state.workspace == "Research lab":
        from .demo import main as research_main
        research_main(configure_page=False)
    else:
        from .home import render
        render()
