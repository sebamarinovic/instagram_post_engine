"""Google login gate for the Streamlit app, built on Streamlit's native
auth (st.login/st.user), configured entirely in .streamlit/secrets.toml
(never committed — see .streamlit/secrets.toml.example).

This app is single-user and personal: logging in with *any* Google account
isn't enough on its own, so ALLOWED_GOOGLE_EMAILS (in .env) restricts access
to a specific allowlist of addresses.
"""
import os

import streamlit as st
from streamlit.errors import StreamlitAuthError

def _allowed_emails():
    raw = os.getenv("ALLOWED_GOOGLE_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}

def require_login():
    """Call at the very top of every page (right after st.set_page_config).
    Stops the script — showing a login button, or an access-denied message
    for a Google account outside the allowlist — for anyone not authorized.

    st.user.is_logged_in raises AttributeError (not just False) when
    .streamlit/secrets.toml has no [auth] section configured yet, so this
    reads it via getattr with a default instead of accessing it directly.
    """
    if not getattr(st.user, "is_logged_in", False):
        st.title("🔒 Instagram Rebuild")
        st.write("Esta app es privada. Inicia sesión con tu cuenta de Google para continuar.")
        if st.button("Iniciar sesión con Google", type="primary"):
            try:
                st.login()
            except StreamlitAuthError:
                st.error(
                    "El login con Google no está configurado todavía. "
                    "Revisa .streamlit/secrets.toml (ver .streamlit/secrets.toml.example)."
                )
        st.stop()

    allowed = _allowed_emails()
    if allowed and (st.user.email or "").lower() not in allowed:
        st.error(f"La cuenta {st.user.email} no tiene acceso a esta app.")
        if st.button("Cerrar sesión"):
            st.logout()
        st.stop()

def sidebar_user_badge():
    """Small 'logged in as ... / cerrar sesión' block for the sidebar."""
    st.sidebar.caption(f"👤 {st.user.name or st.user.email}")
    if st.sidebar.button("🚪 Cerrar sesión", use_container_width=True):
        st.logout()
