"""
Aplicativo Streamlit para Catalogação de Coleção de HQs via Câmera e Gemini 2.5 Flash.
"""

import io
import base64
import os
import streamlit as st
import pandas as pd
from PIL import Image
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env se existir
load_dotenv()

import importlib
import database
import gemini_service
import auth

# Garante recarregamento dos módulos locais em caso de alterações a quente
importlib.reload(database)
importlib.reload(gemini_service)
importlib.reload(auth)

def processar_imagem_capa(imagem: Image.Image, max_dim: int = 700, quality: int = 85) -> str:
    """Redimensiona e converte uma foto PIL em uma string base64 compacta (JPEG)."""
    img = imagem.convert("RGB")
    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Catalogador de HQs | IA Vision",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# SEGURANÇA: VERIFICAÇÃO DE LOGIN
# -------------------------------------------------------------
auth.verificar_autenticacao()

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
    
    # Status da Sessão / Usuário Logado
    usuario_logado = st.session_state.get("logged_user", "admin")
    col_user, col_logout = st.columns([3, 2])
    with col_user:
        st.caption(f"👤 Usuário: **{usuario_logado}**")
    with col_logout:
        if st.button("🚪 Sair", key="btn_logout_top", use_container_width=True):
            auth.fazer_logout()
    
    st.markdown("---")
    
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
        options=["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-pro"],
        index=0,
        help="gemini-2.5-flash é o modelo oficial mais rápido e preciso para visão multimodal do Google."
    )

    # Indicador de Banco de Dados
    if database.is_using_turso():
        st.success("☁️ **Banco: Turso Cloud (Permanente)**", icon="🗄️")
    else:
        st.info("💾 **Banco: SQLite Local**", icon="📁")

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
        st.metric("⭐ Média Aval.", f"{stats.get('media_avaliacao', 0.0):.1f} / 5" if stats.get("media_avaliacao", 0.0) > 0 else "-")

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
    col_filtro_busca, col_filtro_prat, col_filtro_gen, col_filtro_leitura, col_filtro_aval = st.columns([2, 1, 1, 1, 1])

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

    with col_filtro_aval:
        opcoes_aval = {
            "Todas as Notas": -1,
            "⭐⭐⭐⭐⭐ (5)": 5,
            "⭐⭐⭐⭐ (4)": 4,
            "⭐⭐⭐ (3)": 3,
            "⭐⭐ (2)": 2,
            "⭐ (1)": 1,
            "⚪ Sem Avaliação": 0
        }
        aval_selecionada = st.selectbox("Filtrar por Avaliação:", list(opcoes_aval.keys()))
        aval_filtro_val = opcoes_aval[aval_selecionada]

    df_hqs = database.listar_todas_hqs(
        busca=busca_texto,
        prateleira_filtro=prateleira_selecionada,
        genero_filtro=genero_selecionado,
        status_leitura_filtro=leitura_selecionada,
        avaliacao_filtro=aval_filtro_val
    )

    if not df_hqs.empty:
        st.write(f"Exibindo **{len(df_hqs)}** quadrinho(s) cadastrado(s): *(Edite células ou selecione linhas e pressione `Delete` para excluir)*")
        
        df_editado = st.data_editor(
            df_hqs,
            use_container_width=True,
            num_rows="dynamic",
            disabled=["id", "capa", "criado_em"],
            hide_index=True,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "capa": st.column_config.ImageColumn("Capa", help="Foto da capa cadastrada"),
                "titulo": st.column_config.TextColumn("Título", required=True),
                "edicao": st.column_config.TextColumn("Edição/Vol."),
                "editora": st.column_config.TextColumn("Editora"),
                "genero": st.column_config.TextColumn("Gênero"),
                "escritor": st.column_config.TextColumn("Roteiro/Escritor"),
                "ilustrador": st.column_config.TextColumn("Arte/Ilustrador"),
                "prateleira": st.column_config.TextColumn("Prateleira", required=True),
                "lido": st.column_config.SelectboxColumn(
                    "Status de Leitura",
                    help="Status de leitura da edição",
                    options=["Não Lido", "Lido"],
                    required=True
                ),
                "avaliacao": st.column_config.NumberColumn(
                    "Avaliação ⭐",
                    help="Nota de 1 a 5 estrelas (0 = Sem avaliação)",
                    min_value=0,
                    max_value=5,
                    step=1,
                    format="%d ⭐"
                ),
                "criado_em": st.column_config.TextColumn("Data do Cadastro", disabled=True)
            },
            key="tabela_inventario_editavel"
        )

        # Detecção de alterações ou exclusões nas linhas do grid
        houve_alteracao = not df_editado.equals(df_hqs)

        col_save_grid, col_info_grid = st.columns([1, 2])
        with col_save_grid:
            if st.button("💾 Salvar Alterações da Tabela", type="primary", disabled=not houve_alteracao, use_container_width=True):
                # 1. Processa exclusões de linhas
                ids_originais = set(int(x) for x in df_hqs["id"].dropna())
                ids_restantes = set(int(x) for x in df_editado["id"].dropna()) if "id" in df_editado.columns else set()
                ids_deletados = ids_originais - ids_restantes

                linhas_excluidas = 0
                for del_id in ids_deletados:
                    if database.deletar_hq(del_id):
                        linhas_excluidas += 1

                # 2. Processa edições de linhas existentes
                linhas_atualizadas = 0
                for _, row_editada in df_editado.iterrows():
                    if pd.isna(row_editada.get("id")):
                        continue
                    hq_id_val = int(row_editada["id"])
                    orig_match = df_hqs[df_hqs["id"] == hq_id_val]
                    if not orig_match.empty:
                        orig = orig_match.iloc[0]
                        campos = ["titulo", "edicao", "editora", "genero", "escritor", "ilustrador", "prateleira", "lido", "avaliacao", "capa"]
                        if any(str(row_editada.get(c, "")) != str(orig.get(c, "")) for c in campos):
                            database.atualizar_hq(
                                hq_id=hq_id_val,
                                titulo=str(row_editada["titulo"] or ""),
                                edicao=str(row_editada["edicao"] or ""),
                                editora=str(row_editada["editora"] or ""),
                                genero=str(row_editada.get("genero") or "Outro"),
                                escritor=str(row_editada.get("escritor") or "Não informado"),
                                ilustrador=str(row_editada.get("ilustrador") or "Não informado"),
                                prateleira=str(row_editada["prateleira"] or ""),
                                lido=str(row_editada["lido"] or "Não Lido"),
                                avaliacao=int(row_editada.get("avaliacao") or 0),
                                capa=str(row_editada.get("capa") or "")
                            )
                            linhas_atualizadas += 1

                if linhas_atualizadas > 0 or linhas_excluidas > 0:
                    mensagens = []
                    if linhas_atualizadas > 0:
                        mensagens.append(f"{linhas_atualizadas} HQ(s) atualizada(s)")
                    if linhas_excluidas > 0:
                        mensagens.append(f"{linhas_excluidas} HQ(s) excluída(s)")
                    st.success(f"🎉 Gravado com sucesso: {', '.join(mensagens)}!")
                    st.rerun()

        with col_info_grid:
            if houve_alteracao:
                st.warning("⚠️ Alterações/exclusões pendentes detectadas no Grid! Clique em **\"Salvar Alterações da Tabela\"** para gravar no banco.", icon="✏️")
            else:
                st.caption("💡 **Dicas do Grid:** Dê 2 cliques para editar qualquer campo. Para excluir, marque a linha na caixa de seleção e pressione a tecla `Delete` no teclado ou no ícone da lixeira.")

        st.markdown("##### 🛠️ Ações Rápidas no Inventário")
        col_act_edit, col_act_capa, col_act_rate, col_act_toggle, col_act_del = st.columns(5)

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
                    if hq_atual.get("capa"):
                        st.image(hq_atual["capa"], width=130, caption="Capa Atual")

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

                        nota_atual = int(hq_atual.get("avaliacao") or 0)
                        novo_avaliacao = st.selectbox(
                            "Avaliação (1 a 5 estrelas):",
                            options=[0, 1, 2, 3, 4, 5],
                            index=nota_atual,
                            format_func=lambda x: "⚪ Sem Avaliação (0)" if x == 0 else f"{'⭐' * x} ({x} de 5)"
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
                                    lido=novo_status_leitura,
                                    avaliacao=novo_avaliacao,
                                    capa=hq_atual.get("capa") or ""
                                ):
                                    st.success(f"HQ #{id_para_editar} atualizada com sucesso!")
                                    st.rerun()
                                else:
                                    st.error("Erro ao salvar alterações no banco de dados.")
                else:
                    st.info(f"Nenhum quadrinho com o ID #{id_para_editar} foi encontrado.")

        # -------------------------------------------------------------
        # BOTÃO E POPOVER DE CADASTRAR / FOTOGRAFAR CAPA
        # -------------------------------------------------------------
        with col_act_capa:
            with st.popover("📷 Cadastrar Capa", use_container_width=True):
                st.markdown("#### Cadastrar Foto da Capa")
                id_para_capa = st.number_input(
                    "Informe o ID da HQ:",
                    min_value=1,
                    step=1,
                    key="input_capa_id"
                )
                hq_capa = database.obter_hq_por_id(int(id_para_capa))
                if hq_capa:
                    st.write(f"HQ: **{hq_capa['titulo']}** ({hq_capa.get('edicao') or 'Sem Edição'})")
                    capa_existente = hq_capa.get("capa")
                    if capa_existente:
                        st.image(capa_existente, width=140, caption="Capa Atual Cadastrada")
                        if st.button("🗑️ Remover Capa Atual", key="btn_remove_capa_indiv", type="secondary"):
                            database.remover_capa_hq(int(id_para_capa))
                            st.success("Capa removida com sucesso!")
                            st.rerun()

                    st.markdown("---")
                    st.markdown("##### 📸 Fotografar ou Enviar Capa:")
                    tab_capa_up, tab_capa_live = st.tabs(["📁 Câmera Nativa / Upload", "📷 Câmera Web ao Vivo"])
                    
                    foto_capa_selecionada = None
                    with tab_capa_up:
                        up_arq = st.file_uploader(
                            "Tire uma foto ou selecione a capa:",
                            type=["jpg", "jpeg", "png", "webp"],
                            key="uploader_capa_single"
                        )
                        if up_arq:
                            foto_capa_selecionada = Image.open(up_arq)

                    with tab_capa_live:
                        cam_arq = st.camera_input("Fotografar capa:", key="camera_capa_single")
                        if cam_arq:
                            foto_capa_selecionada = Image.open(cam_arq)

                    if foto_capa_selecionada is not None:
                        st.image(foto_capa_selecionada, width=160, caption="Pré-visualização")
                        if st.button("💾 Salvar Foto da Capa", type="primary", use_container_width=True, key="btn_confirm_salvar_capa"):
                            capa_processada = processar_imagem_capa(foto_capa_selecionada)
                            if database.definir_capa(int(id_para_capa), capa_processada):
                                st.success(f"🎉 Capa da HQ #{id_para_capa} salva com sucesso!")
                                st.rerun()
                            else:
                                st.error("Erro ao salvar foto da capa.")
                else:
                    st.info(f"Nenhum quadrinho com o ID #{id_para_capa} foi encontrado.")

        # -------------------------------------------------------------
        # BOTÃO E POPOVER PARA AVALIAR HQ (1-CLIQUE)
        # -------------------------------------------------------------
        with col_act_rate:
            with st.popover("⭐ Avaliar HQ", use_container_width=True):
                st.markdown("#### Avaliar HQ (1 a 5)")
                id_para_avaliar = st.number_input(
                    "Informe o ID da HQ:",
                    min_value=1,
                    step=1,
                    key="input_rate_id"
                )
                hq_rate = database.obter_hq_por_id(int(id_para_avaliar))
                if hq_rate:
                    st.write(f"HQ: **{hq_rate['titulo']}**")
                    nota_atual = int(hq_rate.get("avaliacao") or 0)
                    st.caption(f"Avaliação atual: {'⭐' * nota_atual if nota_atual > 0 else '⚪ Sem avaliação'}")
                    nova_nota = st.selectbox(
                        "Selecione a Nota:",
                        options=[0, 1, 2, 3, 4, 5],
                        index=nota_atual,
                        key="sel_fast_nota",
                        format_func=lambda x: "⚪ Sem Avaliação (0)" if x == 0 else f"{'⭐' * x} ({x} de 5)"
                    )
                    if st.button("💾 Salvar Nota", type="primary", use_container_width=True):
                        database.definir_avaliacao(int(id_para_avaliar), nova_nota)
                        st.success(f"Avaliação da HQ #{id_para_avaliar} atualizada com sucesso!")
                        st.rerun()
                else:
                    st.info(f"Nenhum quadrinho com o ID #{id_para_avaliar} encontrado.")

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
                else:
                    st.info(f"Nenhum quadrinho com o ID #{id_para_excluir} encontrado.")
    else:
        st.info("Nenhum quadrinho encontrado com os filtros aplicados ou banco de dados ainda vazio.")
