"""
Aplicativo Streamlit para Catalogação de Coleção de HQs via Câmera e Gemini 2.5 Flash.
"""

import os
import streamlit as st
from PIL import Image
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env se existir
load_dotenv()

import importlib
import database
import gemini_service

# Garante recarregamento dos módulos locais em caso de alterações a quente
importlib.reload(database)
importlib.reload(gemini_service)

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Catalogador de HQs | IA Vision",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializa o banco de dados SQLite
database.init_db()

# Inicialização de variáveis de estado de sessão
if "prateleira_atual" not in st.session_state:
    st.session_state["prateleira_atual"] = "Estante 1 - Prateleira 1"

if "ultimos_itens_salvos" not in st.session_state:
    st.session_state["ultimos_itens_salvos"] = []

if "ultima_foto_processada" not in st.session_state:
    st.session_state["ultima_foto_processada"] = None


# -------------------------------------------------------------
# BARRA LATERAL (SIDEBAR)
# -------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Configurações & Status")
    
    # Campo para chave de API do Gemini
    env_api_key = os.getenv("GEMINI_API_KEY", "")
    api_key_input = st.text_input(
        "Chave de API do Gemini:",
        value=env_api_key,
        type="password",
        help="Obtenha sua chave gratuita em https://aistudio.google.com"
    )
    
    if api_key_input:
        os.environ["GEMINI_API_KEY"] = api_key_input
        st.success("✅ Chave de API configurada!", icon="🔑")
    else:
        st.warning("⚠️ Insira sua chave de API para habilitar a IA.")

    # Seletor de Modelo Gemini
    modelo_selecionado = st.selectbox(
        "Modelo do Gemini:",
        options=["gemini-3.6-flash", "gemini-2.5-flash", "gemini-3-flash", "gemini-2.5-pro"],
        index=0,
        help="gemini-3.6-flash é o modelo mais recente e rápido recomendado pelo Google."
    )

    st.markdown("---")
    
    # Métricas gerais do inventário
    stats = database.obter_estatisticas()
    st.subheader("📊 Estatísticas da Coleção")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric("Total de HQs", stats["total_hqs"])
        st.metric("📖 Lidos", stats.get("total_lidos", 0))
        st.metric("Editoras", stats["total_editoras"])
    with col_m2:
        st.metric("Prateleiras", stats["total_prateleiras"])
        st.metric("⏳ Não Lidos", stats.get("total_nao_lidos", 0))
        st.metric("Gêneros", stats.get("total_generos", 0))

    if stats["total_hqs"] > 0:
        pct_lido = (stats.get("total_lidos", 0) / stats["total_hqs"]) * 100
        st.caption(f"Progresso de Leitura: **{pct_lido:.1f}%**")
        st.progress(pct_lido / 100)

    st.markdown("---")

    # Exportação do inventário para CSV
    df_export = database.listar_todas_hqs()
    if not df_export.empty:
        csv_data = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Exportar Inventário (CSV)",
            data=csv_data,
            file_name="inventario_hqs.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.markdown("---")
    st.caption("🚀 Desenvolvido com **Streamlit** & **Gemini**")


# -------------------------------------------------------------
# CABEÇALHO PRINCIPAL
# -------------------------------------------------------------
st.title("📚 Catalogador Inteligente de HQs")
st.markdown(
    "Tire fotos das prateleiras da sua coleção diretamente com a câmera do smartphone. "
    "A IA identificará os títulos, edições, editoras, **gênero**, **roteirista/escritor** e **desenhista/ilustrador** e salvará automaticamente no seu banco de dados."
)

st.markdown("---")


# -------------------------------------------------------------
# SEÇÃO 1: IDENTIFICAÇÃO DA PRATELEIRA E CAPTURA
# -------------------------------------------------------------
col_shelf, col_hint = st.columns([2, 2])

with col_shelf:
    prateleira_input = st.text_input(
        "📍 **Prateleira / Localização Atual:**",
        value=st.session_state["prateleira_atual"],
        help="Ex: Estante Marvel - Prateleira 3, Nicho Mangás 1, Caixa 4"
    )
    st.session_state["prateleira_atual"] = prateleira_input

with col_hint:
    st.info(
        "💡 **Dica para melhor precisão:** "
        "Enquadre bem as lombadas com boa iluminação e evite reflexos intensos.",
        icon="✨"
    )

st.subheader("📸 Captura da Foto da Prateleira")

# Abas de entrada: Câmera ou Upload de Imagem (útil para testes ou fotos já salvas)
tab_upload, tab_camera = st.tabs(["📁 Enviar Foto / Câmera Nativa (Recomendado)", "📷 Câmera Web ao Vivo (st.camera_input)"])

imagem_para_processar = None

with tab_upload:
    st.markdown(
        "📱 **Dica para celular:** Ao tocar no botão abaixo, escolha **\"Câmera\"** para fotografar a prateleira em alta resolução."
    )
    foto_upload = st.file_uploader(
        "Selecione uma imagem ou tire uma foto:",
        type=["jpg", "jpeg", "png", "webp"],
        help="Funciona diretamente no celular sem necessidade de HTTPS."
    )
    if foto_upload is not None:
        imagem_para_processar = Image.open(foto_upload)

with tab_camera:
    st.caption(
        "⚠️ *Aviso de segurança dos navegadores:* O streaming ao vivo de webcam requer conexão segura (HTTPS ou localhost). "
        "Se a câmera não abrir no celular via IP local (HTTP), use a aba **\"Câmera Nativa\"** ao lado ou habilite a flag de origem segura no Chrome."
    )
    foto_camera = st.camera_input("Aponte para a prateleira:")
    if foto_camera is not None:
        imagem_para_processar = Image.open(foto_camera)


# -------------------------------------------------------------
# PROCESSAMENTO COM IA & PERSISTÊNCIA AUTOMÁTICA
# -------------------------------------------------------------
if imagem_para_processar is not None:
    st.image(imagem_para_processar, caption="Pré-visualização da Foto Capturada", use_container_width=True)

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        botao_analisar = st.button("🚀 Processar & Salvar HQs", type="primary", use_container_width=True)

    if botao_analisar:
        if not os.getenv("GEMINI_API_KEY"):
            st.error("❌ Chave de API do Gemini não configurada! Insira-a na barra lateral.")
        elif not prateleira_input.strip():
            st.error("❌ Por favor, informe o nome ou código da Prateleira Atual.")
        else:
            status_placeholder = st.empty()
            with st.spinner(f"🤖 Analisando lombadas com {modelo_selecionado} e catalogando..."):
                try:
                    def atualizar_status(mensagem: str):
                        status_placeholder.info(mensagem, icon="⏳")

                    # Envia para a API do Gemini com retentativas automáticas e fallback
                    hqs_detectadas = gemini_service.processar_foto_prateleira(
                        imagem=imagem_para_processar,
                        api_key=os.getenv("GEMINI_API_KEY"),
                        modelo=modelo_selecionado,
                        status_callback=atualizar_status
                    )
                    status_placeholder.empty()

                    if hqs_detectadas:
                        # Salva automaticamente no banco de dados SQLite
                        total_salvo = database.salvar_hqs(hqs_detectadas, prateleira_input.strip())
                        st.session_state["ultimos_itens_salvos"] = hqs_detectadas
                        
                        st.success(
                            f"🎉 **{total_salvo} HQ(s) identificada(s) e salvas com sucesso** na prateleira `{prateleira_input.strip()}`!"
                        )
                    else:
                        st.warning("⚠️ Nenhum quadrinho pôde ser identificado nesta foto. Tente aproximar ou melhorar a iluminação.")
                except Exception as ex:
                    status_placeholder.empty()
                    st.error(f"Erro ao processar imagem: {ex}")

# Exibe resumo visual imediato dos últimos itens detectados e salvos
if st.session_state["ultimos_itens_salvos"]:
    st.markdown("### 📋 Itens Recém-Identificados e Salvos")
    st.dataframe(
        st.session_state["ultimos_itens_salvos"],
        use_container_width=True,
        column_config={
            "titulo": "Título da HQ",
            "edicao": "Edição / Volume",
            "editora": "Editora",
            "genero": "Gênero",
            "escritor": "Roteirista / Escritor",
            "ilustrador": "Desenhista / Arte"
        }
    )

st.markdown("---")


# -------------------------------------------------------------
# SEÇÃO 2: VISUALIZAÇÃO DO INVENTÁRIO COMPLETO
# -------------------------------------------------------------
with st.expander("📚 Ver Inventário Atual (Banco de Dados SQLite)", expanded=True):
    col_filtro_busca, col_filtro_prat, col_filtro_gen, col_filtro_leitura = st.columns([2, 1, 1, 1])

    with col_filtro_busca:
        busca_texto = st.text_input("🔍 Buscar por título, autor, editora, gênero ou edição:", placeholder="Digite para filtrar...")

    with col_filtro_prat:
        lista_prateleiras = ["Todas"] + database.obter_prateleiras()
        prateleira_selecionada = st.selectbox("Filtrar por Prateleira:", lista_prateleiras)

    with col_filtro_gen:
        lista_generos = ["Todos"] + database.obter_generos()
        genero_selecionado = st.selectbox("Filtrar por Gênero:", lista_generos)

    with col_filtro_leitura:
        leitura_selecionada = st.selectbox("Status de Leitura:", ["Todos", "Lido", "Não Lido"])

    df_hqs = database.listar_todas_hqs(
        busca=busca_texto,
        prateleira_filtro=prateleira_selecionada,
        genero_filtro=genero_selecionado,
        status_leitura_filtro=leitura_selecionada
    )

    if not df_hqs.empty:
        st.write(f"Exibindo **{len(df_hqs)}** quadrinho(s) cadastrado(s):")
        st.dataframe(
            df_hqs,
            use_container_width=True,
            column_config={
                "id": "ID",
                "titulo": "Título",
                "edicao": "Edição/Vol.",
                "editora": "Editora",
                "genero": "Gênero",
                "escritor": "Roteiro/Escritor",
                "ilustrador": "Arte/Ilustrador",
                "prateleira": "Prateleira",
                "lido": st.column_config.SelectboxColumn(
                    "Status de Leitura",
                    help="Status de leitura da edição",
                    options=["Não Lido", "Lido"],
                    required=True
                ),
                "criado_em": "Data do Cadastro"
            }
        )

        st.markdown("##### 🛠️ Ações Rápidas no Inventário")
        col_act_edit, col_act_toggle, col_act_del = st.columns(3)

        # -------------------------------------------------------------
        # BOTÃO E POPOVER DE EDIÇÃO
        # -------------------------------------------------------------
        with col_act_edit:
            with st.popover("✏️ Editar HQ por ID", use_container_width=True):
                st.markdown("#### Editar Dados da HQ")
                id_para_editar = st.number_input(
                    "Informe o ID da HQ que deseja editar:",
                    min_value=1,
                    step=1,
                    key="input_edit_id"
                )

                hq_atual = database.obter_hq_por_id(int(id_para_editar))

                if hq_atual:
                    st.caption(f"Editando registro **#{hq_atual['id']}** cadastrado em `{hq_atual['criado_em']}`")
                    with st.form("form_edicao_hq"):
                        novo_titulo = st.text_input("Título:", value=hq_atual["titulo"])
                        nova_edicao = st.text_input("Edição / Volume:", value=hq_atual["edicao"] or "")
                        nova_editora = st.text_input("Editora:", value=hq_atual["editora"] or "")
                        novo_genero = st.text_input("Gênero:", value=hq_atual.get("genero") or "Outro")
                        novo_escritor = st.text_input("Escritor / Roteirista:", value=hq_atual.get("escritor") or "Não informado")
                        novo_ilustrador = st.text_input("Ilustrador / Arte:", value=hq_atual.get("ilustrador") or "Não informado")
                        nova_prateleira = st.text_input("Prateleira:", value=hq_atual["prateleira"] or "")
                        
                        status_atual_index = 1 if hq_atual.get("lido") == "Lido" else 0
                        novo_status_leitura = st.selectbox(
                            "Status de Leitura:",
                            options=["Não Lido", "Lido"],
                            index=status_atual_index
                        )

                        btn_salvar_edicao = st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)

                        if btn_salvar_edicao:
                            if not novo_titulo.strip():
                                st.error("O título da HQ não pode ficar vazio.")
                            else:
                                if database.atualizar_hq(
                                    hq_id=int(id_para_editar),
                                    titulo=novo_titulo,
                                    edicao=nova_edicao,
                                    editora=nova_editora,
                                    genero=novo_genero,
                                    escritor=novo_escritor,
                                    ilustrador=novo_ilustrador,
                                    prateleira=nova_prateleira,
                                    lido=novo_status_leitura
                                ):
                                    st.success(f"HQ #{id_para_editar} atualizada com sucesso!")
                                    st.rerun()
                                else:
                                    st.error("Erro ao salvar alterações no banco de dados.")
                else:
                    st.info(f"Nenhum quadrinho com o ID #{id_para_editar} foi encontrado.")

        # -------------------------------------------------------------
        # BOTÃO E POPOVER PARA ALTERNAR STATUS DE LEITURA (1-CLIQUE)
        # -------------------------------------------------------------
        with col_act_toggle:
            with st.popover("📖 Alternar Lido / Não Lido", use_container_width=True):
                st.markdown("#### Alternar Status de Leitura")
                id_para_toggle = st.number_input(
                    "Informe o ID da HQ:",
                    min_value=1,
                    step=1,
                    key="input_toggle_id"
                )
                hq_toggle = database.obter_hq_por_id(int(id_para_toggle))
                if hq_toggle:
                    status_atual = hq_toggle.get("lido", "Não Lido")
                    novo_alvo = "Lido" if status_atual == "Não Lido" else "Não Lido"
                    st.write(f"HQ: **{hq_toggle['titulo']}**")
                    st.write(f"Status atual: `{status_atual}` ➡️ Mudará para: **`{novo_alvo}`**")
                    if st.button(f"Marcar como {novo_alvo}", type="primary", use_container_width=True):
                        novo = database.alternar_status_leitura(int(id_para_toggle))
                        st.success(f"HQ #{id_para_toggle} marcada como **{novo}**!")
                        st.rerun()
                else:
                    st.info(f"Nenhum quadrinho com ID #{id_para_toggle} encontrado.")

        # -------------------------------------------------------------
        # BOTÃO E POPOVER DE EXCLUSÃO
        # -------------------------------------------------------------
        with col_act_del:
            with st.popover("🗑️ Excluir HQ por ID", use_container_width=True):
                st.markdown("#### Excluir HQ")
                id_para_excluir = st.number_input(
                    "Informe o ID da HQ a excluir:",
                    min_value=1,
                    step=1,
                    key="input_delete_id"
                )
                hq_del = database.obter_hq_por_id(int(id_para_excluir))
                if hq_del:
                    st.warning(f"Tem certeza que deseja excluir **{hq_del['titulo']}** (#{hq_del['id']})?")
                    if st.button("Confirmar Exclusão Definitiva", type="secondary", use_container_width=True):
                        if database.deletar_hq(int(id_para_excluir)):
                            st.success(f"Item #{id_para_excluir} excluído com sucesso!")
                            st.rerun()
                        else:
                            st.error(f"Erro ao excluir item #{id_para_excluir}.")
                else:
                    st.info(f"Nenhum quadrinho com o ID #{id_para_excluir} encontrado.")
    else:
        st.info("Nenhum quadrinho encontrado com os filtros aplicados ou banco de dados ainda vazio.")
