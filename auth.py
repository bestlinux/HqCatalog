"""
Módulo de Autenticação Básica para o Catalogador de HQs
Permite proteger o aplicativo contra acessos públicos não autorizados.
"""

import os
import streamlit as st
from typing import Tuple


def obter_credenciais_configuradas() -> Tuple[str, str]:
    """
    Retorna o usuário e a senha esperados do ambiente (.env) ou dos secrets do Streamlit.
    Padrão de fallback: admin / admin123 (caso não configurado).
    """
    usuario_padrao = "admin"
    senha_padrao = "admin123"

    usuario = os.getenv("APP_USERNAME")
    senha = os.getenv("APP_PASSWORD")

    # Verifica também em st.secrets caso esteja no Streamlit Cloud
    try:
        if hasattr(st, "secrets"):
            if not usuario and "APP_USERNAME" in st.secrets:
                usuario = st.secrets["APP_USERNAME"]
            if not senha and "APP_PASSWORD" in st.secrets:
                senha = st.secrets["APP_PASSWORD"]
    except Exception:
        pass

    return usuario or usuario_padrao, senha or senha_padrao


def verificar_credenciais(usuario_digitado: str, senha_digitada: str) -> bool:
    """Verifica se o usuário e senha digitados correspondem às credenciais esperadas."""
    usuario_esperado, senha_esperada = obter_credenciais_configuradas()
    return (
        usuario_digitado.strip().lower() == usuario_esperado.strip().lower()
        and senha_digitada == senha_esperada
    )


def fazer_logout() -> None:
    """Encerra a sessão do usuário atual."""
    st.session_state["authenticated"] = False
    st.session_state["logged_user"] = None
    st.rerun()


def render_login_screen() -> None:
    """Renderiza uma tela de login limpa, responsiva e centralizada."""
    _, col_center, _ = st.columns([1, 2, 1])

    with col_center:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 20px;">
                <h1>🔐 Acesso Restrito</h1>
                <p style="color: #888; font-size: 1.1rem;">
                    Identifique-se para acessar o <strong>Catalogador de HQs</strong>.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.form("form_login_app", clear_on_submit=False):
            usuario_input = st.text_input(
                "👤 Usuário:",
                placeholder="Ex: admin",
                value=""
            )
            senha_input = st.text_input(
                "🔑 Senha:",
                type="password",
                placeholder="Digite sua senha"
            )

            btn_login = st.form_submit_button("🚀 Entrar no Sistema", type="primary", use_container_width=True)

            if btn_login:
                if not usuario_input.strip() or not senha_input:
                    st.warning("⚠️ Por favor, preencha o usuário e a senha.")
                elif verificar_credenciais(usuario_input, senha_input):
                    st.session_state["authenticated"] = True
                    st.session_state["logged_user"] = usuario_input.strip()
                    st.success("✅ Login realizado com sucesso! Carregando acervo...")
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos.")

def verificar_autenticacao() -> bool:
    """
    Controla o fluxo de autenticação.
    Se o usuário estiver autenticado, retorna True e permite continuar.
    Caso contrário, exibe a tela de login e bloqueia a renderização do restante do app.
    """
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        render_login_screen()
        st.stop()
        return False

    return True
