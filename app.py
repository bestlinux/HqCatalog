"""
Aplicativo Streamlit para Catalogação de Coleção de HQs via Câmera e Gemini 2.5 Flash.
"""

import io
import base64
import os
from datetime import datetime
from typing import Optional, Any
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

DEFAULT_NO_COVER_PATH = r"C:\Users\bestl\OneDrive\HqCatalog\HqCatalog\No_Image_Available.jpg"

def processar_imagem_capa(imagem: Image.Image, max_dim: int = 700, quality: int = 85) -> str:
    """Redimensiona e converte uma foto PIL em uma string base64 compacta (JPEG)."""
    img = imagem.convert("RGB")
    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"

def obter_imagem_capa(capa_val: Optional[str]) -> Any:
    """Retorna a URL, base64 ou imagem PIL da capa, com fallback para No_Image_Available.jpg."""
    capa_str = (capa_val or "").strip()
    if capa_str:
        return capa_str
    
    if os.path.exists(DEFAULT_NO_COVER_PATH):
        try:
            return Image.open(DEFAULT_NO_COVER_PATH)
        except Exception:
            return DEFAULT_NO_COVER_PATH
            
    caminho_rel = os.path.join(os.path.dirname(os.path.abspath(__file__)), "No_Image_Available.jpg")
    if os.path.exists(caminho_rel):
        try:
            return Image.open(caminho_rel)
        except Exception:
            return caminho_rel
            
    return DEFAULT_NO_COVER_PATH

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

if "chat_mensagens_curador" not in st.session_state:
    st.session_state["chat_mensagens_curador"] = [
        {
            "role": "assistant",
            "content": "👋 Olá! Sou seu **Curador Virtual de HQs**.\n\nPosso te ajudar a explorar seu acervo e sugerir leituras com base nos enredos e resumos cadastrados!\n\nMe pergunte coisas como:\n- *'Quero ler algo sobre temas históricos no Brasil'*\n- *'Quais são as melhores HQs que ainda não li?'*\n- *'Me indique uma boa história de suspense ou ficção científica'*."
        }
    ]

if "radar_precos_resultado" not in st.session_state:
    st.session_state["radar_precos_resultado"] = None

if "oferta_pendente_desejos" not in st.session_state:
    st.session_state["oferta_pendente_desejos"] = None


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
        options=["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3-flash-preview"],
        index=0,
        help="gemini-3.1-flash-lite e gemini-3.5-flash são os modelos oficiais mais rápidos, estáveis e recomendados para catalogação e curadoria."
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
# DESTAQUE: EDIÇÃO DO DIA
# -------------------------------------------------------------
st.markdown("### 🌟 Edição do Dia")

# Gerenciamento da Edição do Dia na sessão
data_hoje = datetime.now().strftime("%Y-%m-%d")
if st.session_state.get("data_edicao_do_dia") != data_hoje:
    st.session_state["data_edicao_do_dia"] = data_hoje
    st.session_state["edicao_do_dia_id"] = None

hq_dia = None
if st.session_state.get("edicao_do_dia_id"):
    hq_dia = database.obter_hq_por_id(int(st.session_state["edicao_do_dia_id"]))

if not hq_dia:
    hq_dia = database.obter_hq_aleatoria()
    if hq_dia:
        st.session_state["edicao_do_dia_id"] = hq_dia["id"]

if hq_dia:
    with st.container(border=True):
        col_capa, col_detalhes = st.columns([1.1, 3.2], gap="medium")
        
        with col_capa:
            img_capa = obter_imagem_capa(hq_dia.get("capa"))
            tem_capa = bool(hq_dia.get("capa") and str(hq_dia["capa"]).strip())
            legenda_capa = "Foto da Capa" if tem_capa else "Capa Padrão (Não cadastrada)"
            st.image(img_capa, caption=legenda_capa, use_container_width=True)
            
            if not tem_capa:
                if st.button("📷 Cadastrar Capa", key="btn_add_capa_dia", use_container_width=True, help="Tire uma foto ou envie a capa desta edição"):
                    dialog_cadastrar_capa(int(hq_dia["id"]))
                    
        with col_detalhes:
            st.subheader(f"📖 {hq_dia['titulo']}")
            
            meta_itens = []
            if hq_dia.get("edicao"):
                meta_itens.append(f"🔖 **Edição/Vol:** {hq_dia['edicao']}")
            if hq_dia.get("editora"):
                meta_itens.append(f"🏢 **Editora:** {hq_dia['editora']}")
            if hq_dia.get("genero"):
                meta_itens.append(f"🏷️ **Gênero:** {hq_dia['genero']}")
            if hq_dia.get("escritor") and hq_dia["escritor"] != "Não informado":
                meta_itens.append(f"✍️ **Roteiro:** {hq_dia['escritor']}")
            if hq_dia.get("prateleira"):
                meta_itens.append(f"📍 **Prateleira:** `{hq_dia['prateleira']}`")
                
            if meta_itens:
                st.markdown(" • ".join(meta_itens))
                
            status_leitura = hq_dia.get("lido", "Não Lido")
            aval = int(hq_dia.get("avaliacao") or 0)
            aval_texto = ("⭐" * aval + f" ({aval}/5)") if aval > 0 else "⚪ Sem avaliação"
            st.caption(f"Status: **{status_leitura}** | Avaliação: **{aval_texto}**")
            
            st.markdown("---")
            
            st.markdown("#### 📝 Resumo")
            resumo_texto = (hq_dia.get("resumo") or "").strip()
            if resumo_texto:
                st.markdown(f"> {resumo_texto}")
            else:
                st.info("ℹ️ *Esta edição ainda não possui um resumo cadastrado. Você pode adicioná-lo editando a HQ pelo formulário ou tabela.*")
                
            st.markdown("")
            
            col_b1, col_b2, col_b3 = st.columns([1.5, 1.5, 2])
            with col_b1:
                if st.button("🎲 Sortear Outra", key="btn_sortear_outra_dia", use_container_width=True, help="Sortear aleatoriamente outro quadrinho da sua coleção"):
                    outra_hq = database.obter_hq_aleatoria(excluir_id=int(hq_dia["id"]))
                    if outra_hq:
                        st.session_state["edicao_do_dia_id"] = outra_hq["id"]
                        st.rerun()
            with col_b2:
                if st.button("✏️ Editar HQ", key="btn_editar_hq_dia", use_container_width=True, help="Editar informações desta HQ"):
                    dialog_editar_hq(int(hq_dia["id"]))
            with col_b3:
                pass
else:
    with st.container(border=True):
        st.info("📚 **Nenhuma edição cadastrada no momento.** Tire fotos da sua prateleira ou adicione títulos para ver a **Edição do Dia** em destaque aqui!", icon="✨")

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
                        # Salva automaticamente no banco de dados com prevenção de duplicatas
                        resultado = database.salvar_hqs(
                            hqs_detectadas,
                            prateleira_input.strip(),
                            ignorar_duplicadas=True,
                            retornar_detalhes=True
                        )
                        total_salvo = resultado["salvos"]
                        total_duplicados = resultado["duplicados"]
                        itens_salvos = resultado["itens_salvos"]
                        itens_duplicados = resultado["itens_duplicados"]

                        st.session_state["ultimos_itens_salvos"] = itens_salvos
                        
                        if total_salvo > 0 and total_duplicados > 0:
                            st.success(
                                f"🎉 **{total_salvo} HQ(s) nova(s) salva(s) com sucesso** na prateleira `{prateleira_input.strip()}`!"
                            )
                            st.info(
                                f"ℹ️ **{total_duplicados} HQ(s) ignorada(s)** pois já constavam no catálogo (mesmo Título + Edição/Número + Editora)."
                            )
                        elif total_salvo > 0:
                            st.success(
                                f"🎉 **{total_salvo} HQ(s) identificada(s) e salvas com sucesso** na prateleira `{prateleira_input.strip()}`!"
                            )
                        elif total_duplicados > 0:
                            st.warning(
                                f"⚠️ Nenhuma nova HQ gravada: todas as **{total_duplicados} HQ(s)** identificadas na foto já estavam cadastradas no catálogo com mesmo Título + Edição/Número + Editora."
                            )

                        if itens_duplicados:
                            with st.expander(f"🔍 Ver detalhes das {len(itens_duplicados)} HQ(s) ignoradas por duplicidade"):
                                for dup in itens_duplicados:
                                    st.write(f"- ⚠️ **{dup.get('titulo')}** ({dup.get('edicao') or 'Sem Edição'}) - Editora: *{dup.get('editora') or 'Desconhecida'}* — `{dup.get('motivo_duplicata')}`")
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
            "ilustrador": "Desenhista / Arte",
            "resumo": "Resumo da História"
        }
    )

st.markdown("---")

# -------------------------------------------------------------
# MODAIS (DIALOGS) DE AÇÕES RÁPIDAS
# -------------------------------------------------------------
@st.dialog("✏️ Editar HQ")
def dialog_editar_hq(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    id_para_editar = st.number_input("Informe o ID da HQ que deseja editar:", min_value=1, step=1, value=val_id, key=f"dlg_input_edit_id_{id_padrao or 'padrao'}")
    hq_atual = database.obter_hq_por_id(int(id_para_editar))
    if hq_atual:
        st.caption(f"Editando registro **#{hq_atual['id']}** cadastrado em `{hq_atual['criado_em']}`")
        if hq_atual.get("capa"):
            st.image(hq_atual["capa"], width=130, caption="Capa Atual")
        with st.form("form_edicao_dlg"):
            novo_titulo = st.text_input("Título:", value=hq_atual["titulo"])
            nova_edicao = st.text_input("Edição / Volume:", value=hq_atual["edicao"] or "")
            nova_editora = st.text_input("Editora:", value=hq_atual["editora"] or "")
            novo_genero = st.text_input("Gênero:", value=hq_atual.get("genero") or "Outro")
            novo_escritor = st.text_input("Escritor / Roteirista:", value=hq_atual.get("escritor") or "Não informado")
            novo_ilustrador = st.text_input("Ilustrador / Arte:", value=hq_atual.get("ilustrador") or "Não informado")
            nova_prateleira = st.text_input("Prateleira:", value=hq_atual["prateleira"] or "")
            status_atual_index = 1 if hq_atual.get("lido") == "Lido" else 0
            novo_status_leitura = st.selectbox("Status de Leitura:", options=["Não Lido", "Lido"], index=status_atual_index)
            nota_atual = int(hq_atual.get("avaliacao") or 0)
            novo_avaliacao = st.selectbox("Avaliação (1 a 5 estrelas):", options=[0, 1, 2, 3, 4, 5], index=nota_atual, format_func=lambda x: "⚪ Sem Avaliação (0)" if x == 0 else f"{'⭐' * x} ({x} de 5)")
            novo_resumo = st.text_area("📖 Resumo da História (Sinopse):", value=hq_atual.get("resumo") or "", height=90, placeholder="Breve resumo da trama central da história...")
            nova_resenha = st.text_area("✍️ Resenha / O que achou da HQ:", value=hq_atual.get("resenha") or "", height=90, placeholder="Escreva suas impressões pessoais...")
            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                btn_salvar_edicao = st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)
            with col_btn2:
                btn_cancelar = st.form_submit_button("❌ Fechar", type="secondary", use_container_width=True)
            if btn_salvar_edicao:
                if not novo_titulo.strip(): st.error("O título da HQ não pode ficar vazio.")
                else:
                    if database.atualizar_hq(
                        hq_id=int(id_para_editar),
                        titulo=novo_titulo,
                        edicao=nova_edicao,
                        editora=nova_editora,
                        prateleira=nova_prateleira,
                        genero=novo_genero,
                        escritor=novo_escritor,
                        ilustrador=novo_ilustrador,
                        lido=novo_status_leitura,
                        avaliacao=novo_avaliacao,
                        capa=hq_atual.get("capa") or "",
                        resenha=nova_resenha,
                        resumo=novo_resumo
                    ):
                        st.success(f"HQ #{id_para_editar} atualizada com sucesso!"); st.rerun()
                    else: st.error("Erro ao salvar alterações no banco de dados.")
            if btn_cancelar: st.rerun()
    else:
        st.info(f"Nenhum quadrinho com o ID #{id_para_editar} foi encontrado.")
        if st.button("❌ Fechar", key="btn_close_edit_empty", use_container_width=True): st.rerun()

@st.dialog("📷 Cadastrar / Alterar Foto da Capa")
def dialog_cadastrar_capa(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    id_para_capa = st.number_input("Informe o ID da HQ:", min_value=1, step=1, value=val_id, key=f"dlg_input_capa_id_{id_padrao or 'padrao'}")
    hq_capa = database.obter_hq_por_id(int(id_para_capa))
    if hq_capa:
        st.write(f"HQ: **{hq_capa['titulo']}** ({hq_capa.get('edicao') or 'Sem Edição'})")
        if hq_capa.get("capa"):
            st.image(hq_capa["capa"], width=140, caption="Capa Atual Cadastrada")
            if st.button("🗑️ Remover Capa Atual", key="dlg_btn_remove_capa", type="secondary"):
                database.remover_capa_hq(int(id_para_capa)); st.success("Capa removida!"); st.rerun()
        st.markdown("---")
        tab_capa_up, tab_capa_live = st.tabs(["📁 Câmera Nativa / Upload", "📷 Câmera Web ao Vivo"])
        foto_capa_selecionada = None
        with tab_capa_up:
            up_arq = st.file_uploader("Tire uma foto ou selecione a capa:", type=["jpg", "jpeg", "png", "webp"], key="dlg_uploader_capa")
            if up_arq: foto_capa_selecionada = Image.open(up_arq)
        with tab_capa_live:
            cam_arq = st.camera_input("Fotografar capa:", key="dlg_camera_capa")
            if cam_arq: foto_capa_selecionada = Image.open(cam_arq)
        if foto_capa_selecionada is not None:
            st.image(foto_capa_selecionada, width=160, caption="Pré-visualização")
            col_sc1, col_sc2 = st.columns(2)
            with col_sc1:
                if st.button("💾 Salvar Foto da Capa", type="primary", use_container_width=True, key="dlg_btn_salvar_capa"):
                    capa_processada = processar_imagem_capa(foto_capa_selecionada)
                    if database.definir_capa(int(id_para_capa), capa_processada): st.success("Capa salva!"); st.rerun()
            with col_sc2:
                if st.button("❌ Fechar", key="dlg_btn_cancel_capa", use_container_width=True): st.rerun()
        elif st.button("❌ Fechar", key="dlg_btn_close_capa_only", use_container_width=True): st.rerun()
    else:
        st.info(f"Nenhum quadrinho com o ID #{id_para_capa} encontrado.");
        if st.button("❌ Fechar", key="dlg_btn_close_capa_empty", use_container_width=True): st.rerun()

@st.dialog("✍️ Resenha / O que achou da HQ")
def dialog_resenha():
    id_para_resenha = st.number_input("Informe o ID da HQ:", min_value=1, step=1, key="dlg_input_resenha_id")
    hq_res = database.obter_hq_por_id(int(id_para_resenha))
    if hq_res:
        texto_resenha = st.text_area("Sua Resenha:", value=hq_res.get("resenha") or "", height=130, key="dlg_area_resenha")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            if st.button("💾 Salvar Resenha", type="primary", use_container_width=True, key="dlg_btn_save_resenha"):
                database.definir_resenha(int(id_para_resenha), texto_resenha); st.success("Resenha salva!"); st.rerun()
        with col_r2:
            if st.button("❌ Fechar", key="dlg_btn_cancel_resenha", use_container_width=True): st.rerun()
    else:
        st.info("Nenhum quadrinho com o ID informado encontrado.")
        if st.button("❌ Fechar", key="dlg_btn_close_res_empty", use_container_width=True): st.rerun()

@st.dialog("⭐ Avaliar HQ")
def dialog_avaliar_hq():
    id_para_avaliar = st.number_input("Informe o ID da HQ:", min_value=1, step=1, key="dlg_input_rate_id")
    hq_rate = database.obter_hq_por_id(int(id_para_avaliar))
    if hq_rate:
        nota_atual = int(hq_rate.get("avaliacao") or 0)
        nova_nota = st.selectbox("Selecione a Nota:", options=[0, 1, 2, 3, 4, 5], index=nota_atual, key="dlg_sel_fast_nota", format_func=lambda x: "⚪ Sem Avaliação (0)" if x == 0 else f"{'⭐' * x} ({x} de 5)")
        col_av1, col_av2 = st.columns(2)
        with col_av1:
            if st.button("💾 Salvar Nota", type="primary", use_container_width=True, key="dlg_btn_save_nota"):
                database.definir_avaliacao(int(id_para_avaliar), nova_nota); st.success("Avaliação salva!"); st.rerun()
        with col_av2:
            if st.button("❌ Fechar", key="dlg_btn_cancel_nota", use_container_width=True): st.rerun()
    else:
        st.info("Nenhum quadrinho encontrado.");
        if st.button("❌ Fechar", key="dlg_btn_close_rate_empty", use_container_width=True): st.rerun()

@st.dialog("📖 Alternar Status de Leitura")
def dialog_alternar_leitura():
    id_para_toggle = st.number_input("Informe o ID da HQ:", min_value=1, step=1, key="dlg_input_toggle_id")
    hq_toggle = database.obter_hq_por_id(int(id_para_toggle))
    if hq_toggle:
        novo = database.alternar_status_leitura(int(id_para_toggle))
        st.success(f"Status alterado para **{novo}**!"); st.rerun()
    else:
        st.info("Nenhum quadrinho encontrado.");
        if st.button("❌ Fechar", key="dlg_btn_close_toggle_empty", use_container_width=True): st.rerun()

@st.dialog("🗑️ Excluir HQ")
def dialog_excluir_hq():
    id_para_excluir = st.number_input("Informe o ID da HQ a excluir:", min_value=1, step=1, key="dlg_input_delete_id")
    if database.obter_hq_por_id(int(id_para_excluir)):
        if st.button("🗑️ Confirmar Exclusão", type="primary", use_container_width=True, key="dlg_btn_confirm_del"):
            database.deletar_hq(int(id_para_excluir)); st.success("Excluído!"); st.rerun()
@st.dialog("✏️ Editar Item da Lista de Desejos")
def dialog_editar_desejo():
    id_para_editar = st.number_input("Informe o ID do item da Lista de Desejos:", min_value=1, step=1, key="dlg_input_edit_wish_id")
    item = database.obter_item_lista_desejos(int(id_para_editar))
    if item:
        with st.form("form_editar_desejo"):
            st.write(f"Editando: **{item['titulo']}** (ID #{item['id']})")
            novo_titulo = st.text_input("Título da HQ:", value=item.get("titulo") or "")
            novo_edicao = st.text_input("Edição / Volume:", value=item.get("edicao") or "")
            novo_editora = st.text_input("Editora:", value=item.get("editora") or "")

            col_p, col_l = st.columns(2)
            with col_p:
                novo_preco = st.number_input("Melhor Preço (R$):", min_value=0.0, value=float(item.get("melhor_preco") or 0.0), step=1.0, format="%.2f")
            with col_l:
                novo_loja = st.text_input("Melhor Loja:", value=item.get("melhor_loja") or "")

            novo_link = st.text_input("Link da Oferta (URL):", value=item.get("link_oferta") or "")
            novo_obs = st.text_area("Observações:", value=item.get("observacoes") or "", height=80)

            col_btn_salvar, col_btn_fechar = st.columns(2)
            with col_btn_salvar:
                btn_salvar = st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)
            with col_btn_fechar:
                btn_fechar = st.form_submit_button("❌ Fechar", use_container_width=True)

            if btn_salvar:
                if database.atualizar_item_lista_desejos(
                    item_id=int(id_para_editar),
                    titulo=novo_titulo,
                    edicao=novo_edicao,
                    editora=novo_editora,
                    melhor_preco=novo_preco,
                    melhor_loja=novo_loja,
                    link_oferta=novo_link,
                    observacoes=novo_obs
                ):
                    st.success(f"Item #{id_para_editar} atualizado com sucesso!")
                    st.rerun()
                else:
                    st.error("Erro ao salvar alterações no banco de dados.")
            if btn_fechar:
                st.rerun()
    else:
        st.info(f"Nenhum item com o ID #{id_para_editar} foi encontrado na Lista de Desejos.")
        if st.button("❌ Fechar", key="btn_close_edit_wish_empty", use_container_width=True):
            st.rerun()


@st.dialog("➕ Adicionar HQ na Lista de Desejos")
def dialog_adicionar_desejo_manual():
    with st.form("form_add_desejo_manual"):
        st.write("Preencha os dados do quadrinho que você deseja adquirir:")
        novo_titulo = st.text_input("Título da HQ *:", placeholder="Ex: Batman Ano Um")
        novo_edicao = st.text_input("Edição / Volume:", placeholder="Ex: Edição Especial, Vol. 1")
        novo_editora = st.text_input("Editora:", placeholder="Ex: Panini, Pipoca & Nanquim")

        col_p, col_l = st.columns(2)
        with col_p:
            novo_preco = st.number_input("Preço Encontrado (R$):", min_value=0.0, value=0.0, step=1.0, format="%.2f")
        with col_l:
            novo_loja = st.text_input("Loja:", placeholder="Ex: Amazon, Comix, etc")

        novo_link = st.text_input("Link da Oferta (URL):", placeholder="https://...")
        novo_obs = st.text_area("Observações:", placeholder="Ex: Anotado para compra na Black Friday", height=80)

        col_btn_add, col_btn_fechar = st.columns(2)
        with col_btn_add:
            btn_add = st.form_submit_button("➕ Adicionar à Lista", type="primary", use_container_width=True)
        with col_btn_fechar:
            btn_fechar = st.form_submit_button("❌ Fechar", use_container_width=True)

        if btn_add:
            if novo_titulo.strip():
                item_id = database.adicionar_item_lista_desejos(
                    titulo=novo_titulo,
                    edicao=novo_edicao,
                    editora=novo_editora,
                    melhor_preco=novo_preco,
                    melhor_loja=novo_loja,
                    link_oferta=novo_link,
                    observacoes=novo_obs
                )
                if item_id > 0:
                    st.success(f"🎉 '{novo_titulo}' adicionado com sucesso à sua Lista de Desejos!")
                    st.rerun()
                else:
                    st.error("Erro ao salvar item na Lista de Desejos.")
            else:
                st.warning("Informe pelo menos o título da HQ.")
        if btn_fechar:
            st.rerun()


# -------------------------------------------------------------
# SEÇÃO 2: VISUALIZAÇÃO DO INVENTÁRIO COMPLETO
# -------------------------------------------------------------
with st.expander("📚 Ver Inventário Atual (Banco de Dados SQLite)", expanded=True):
    col_filtro_busca, col_filtro_prat, col_filtro_gen, col_filtro_leitura, col_filtro_aval, col_filtro_ordem = st.columns([2, 1, 1, 1, 1, 1.2])

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

    with col_filtro_ordem:
        opcoes_ordem = {
            "🔤 Título (A-Z)": "titulo_asc",
            "🔤 Título (Z-A)": "titulo_desc",
            "🕒 Mais Recentes": "id_desc",
            "⏳ Mais Antigos": "id_asc",
            "⭐ Melhor Avaliação": "avaliacao_desc",
            "🏢 Editora (A-Z)": "editora_asc",
            "📍 Prateleira (A-Z)": "prateleira_asc"
        }
        ordem_selecionada = st.selectbox("Ordenar por:", list(opcoes_ordem.keys()))
        ordem_val = opcoes_ordem[ordem_selecionada]

    df_hqs = database.listar_todas_hqs(
        busca=busca_texto,
        prateleira_filtro=prateleira_selecionada,
        genero_filtro=genero_selecionado,
        status_leitura_filtro=leitura_selecionada,
        avaliacao_filtro=aval_filtro_val,
        ordem_por=ordem_val
    )

    if not df_hqs.empty:
        # Insere coluna de seleção para ações em massa
        df_hqs_display = df_hqs.copy()
        df_hqs_display.insert(0, "selecionar", False)

        st.write(f"Exibindo **{len(df_hqs)}** quadrinho(s) cadastrado(s) ordenados por **{ordem_selecionada}**: *(Marque o CheckBox para ações em massa ou dê 2 cliques para editar)*")

        df_editado = st.data_editor(
            df_hqs_display,
            use_container_width=True,
            num_rows="fixed",
            disabled=["id", "capa", "criado_em"],
            hide_index=True,
            column_config={
                "selecionar": st.column_config.CheckboxColumn(
                    "🔘 Selecionar",
                    help="Marque as HQs para aplicar ações em lote (Lido/Não Lido ou Excluir)",
                    default=False
                ),
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
                "resumo": st.column_config.TextColumn(
                    "Resumo da História",
                    help="Resumo/sinopse da história da HQ gerado pela IA ou editado manualmente"
                ),
                "resenha": st.column_config.TextColumn(
                    "Resenha / Opinião",
                    help="Sua resenha ou opinião pessoal sobre a HQ"
                ),
                "criado_em": st.column_config.TextColumn("Data do Cadastro", disabled=True)
            },
            key="tabela_inventario_editavel"
        )

        # 1. Identifica IDs selecionados pelo CheckBox
        ids_selecionados = []
        if "selecionar" in df_editado.columns and "id" in df_editado.columns:
            ids_selecionados = [int(x) for x in df_editado[df_editado["selecionar"] == True]["id"].dropna()]

        # 2. Se houver HQs selecionadas no CheckBox, exibe a barra de Ações em Massa
        if ids_selecionados:
            qtd_sel = len(ids_selecionados)
            st.info(f"🎯 **{qtd_sel} HQ(s) selecionada(s) no CheckBox:** Escolha uma ação em massa abaixo:")
            col_blk_lido, col_blk_nlido, col_blk_del, col_blk_clear = st.columns([1.5, 1.5, 1.5, 1])
            with col_blk_lido:
                if st.button("📖 Marcar como 'Lido'", type="primary", use_container_width=True, key="btn_bulk_set_lido"):
                    qtd_alt = database.atualizar_status_leitura_em_massa(ids_selecionados, "Lido")
                    st.success(f"🎉 **{qtd_alt} HQ(s)** marcada(s) como **Lido** com sucesso!")
                    st.rerun()
            with col_blk_nlido:
                if st.button("📕 Marcar como 'Não Lido'", type="secondary", use_container_width=True, key="btn_bulk_set_nao_lido"):
                    qtd_alt = database.atualizar_status_leitura_em_massa(ids_selecionados, "Não Lido")
                    st.success(f"🎉 **{qtd_alt} HQ(s)** marcada(s) como **Não Lido** com sucesso!")
                    st.rerun()
            with col_blk_del:
                if st.button("🗑️ Excluir Selecionadas", type="secondary", use_container_width=True, key="btn_bulk_ask_del"):
                    st.session_state["confirmar_exclusao_massa_ids"] = ids_selecionados
                    st.rerun()
            with col_blk_clear:
                if st.button("❌ Desmarcar", use_container_width=True, key="btn_bulk_uncheck"):
                    st.session_state["confirmar_exclusao_massa_ids"] = None
                    st.rerun()

            if st.session_state.get("confirmar_exclusao_massa_ids"):
                ids_del_list = st.session_state["confirmar_exclusao_massa_ids"]
                st.warning(f"⚠️ **Atenção:** Deseja realmente excluir permanentemente as **{len(ids_del_list)} HQ(s)** selecionadas do banco de dados?")
                col_cf_y, col_cf_n = st.columns(2)
                with col_cf_y:
                    if st.button("⚠️ Sim, Confirmar Exclusão em Massa", type="primary", use_container_width=True, key="btn_confirm_bulk_del_act"):
                        qtd_removidas = database.deletar_hqs_em_massa(ids_del_list)
                        st.session_state["confirmar_exclusao_massa_ids"] = None
                        st.success(f"🗑️ **{qtd_removidas} HQ(s)** excluída(s) com sucesso!")
                        st.rerun()
                with col_cf_n:
                    if st.button("Cancelar", use_container_width=True, key="btn_cancel_bulk_del_act"):
                        st.session_state["confirmar_exclusao_massa_ids"] = None
                        st.rerun()

        # Detecção de alterações ou exclusões diretas nas células do grid (ignorando 'selecionar')
        df_editado_sem_sel = df_editado.drop(columns=["selecionar"], errors="ignore")
        houve_alteracao = not df_editado_sem_sel.equals(df_hqs)

        col_save_grid, col_info_grid = st.columns([1, 2])
        with col_save_grid:
            if st.button("💾 Salvar Alterações da Tabela", type="primary", disabled=not houve_alteracao, use_container_width=True):
                # 1. Processa exclusões de linhas manuais
                ids_originais = set(int(x) for x in df_hqs["id"].dropna())
                ids_restantes = set(int(x) for x in df_editado_sem_sel["id"].dropna()) if "id" in df_editado_sem_sel.columns else set()
                ids_deletados = ids_originais - ids_restantes

                linhas_excluidas = 0
                for del_id in ids_deletados:
                    if database.deletar_hq(del_id):
                        linhas_excluidas += 1

                # 2. Processa edições de linhas existentes
                linhas_atualizadas = 0
                for _, row_editada in df_editado_sem_sel.iterrows():
                    if pd.isna(row_editada.get("id")):
                        continue
                    hq_id_val = int(row_editada["id"])
                    orig_match = df_hqs[df_hqs["id"] == hq_id_val]
                    if not orig_match.empty:
                        orig = orig_match.iloc[0]
                        campos = ["titulo", "edicao", "editora", "genero", "escritor", "ilustrador", "prateleira", "lido", "avaliacao", "capa", "resenha", "resumo"]
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
                                capa=str(row_editada.get("capa") or ""),
                                resenha=str(row_editada.get("resenha") or ""),
                                resumo=str(row_editada.get("resumo") or "")
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
                st.caption("💡 **Dicas:** Marque os CheckBoxes para aplicar ações em lote (Lido/Não Lido ou Excluir) ou dê 2 cliques em qualquer célula para editar.")

        st.markdown("##### 🛠️ Ações Rápidas no Inventário")
        col_act_edit, col_act_capa, col_act_resenha, col_act_rate, col_act_toggle, col_act_del = st.columns(6)

        with col_act_edit:
            if st.button("✏️ Editar HQ", use_container_width=True, help="Abrir formulário de edição por ID"):
                dialog_editar_hq()

        with col_act_capa:
            if st.button("📷 Cadastrar Capa", use_container_width=True, help="Fotografar ou enviar capa por ID"):
                dialog_cadastrar_capa()

        with col_act_resenha:
            if st.button("✍️ Resenha", use_container_width=True, help="Escrever ou ler resenha por ID"):
                dialog_resenha()

        with col_act_rate:
            if st.button("⭐ Avaliar HQ", use_container_width=True, help="Dar nota de 1 a 5 por ID"):
                dialog_avaliar_hq()

        with col_act_toggle:
            if st.button("📖 Lido / Não Lido", use_container_width=True, help="Alternar status de leitura em 1 clique"):
                dialog_alternar_leitura()

        with col_act_del:
            if st.button("🗑️ Excluir HQ", use_container_width=True, help="Excluir quadrinho por ID"):
                dialog_excluir_hq()
    else:
        st.info("Nenhum quadrinho encontrado com os filtros aplicados ou banco de dados ainda vazio.")

st.markdown("---")

# -------------------------------------------------------------
# SEÇÃO 3: CURADOR VIRTUAL: RECOMENDAÇÕES DA COLEÇÃO
# -------------------------------------------------------------
with st.expander("💬 Curador Virtual: Assistente & Recomendações da Coleção", expanded=True):
    st.markdown(
        "Peça recomendações personalizadas com base nos **Resumos das Histórias**, gêneros e enredos cadastrados no seu próprio acervo!"
    )

    pergunta_curador_acionada = None

    # Botões de perguntas rápidas da coleção
    col_cur1, col_cur2, col_cur3, col_cur_clear = st.columns([1.2, 1.2, 1.2, 0.6])
    with col_cur1:
        if st.button("🇧🇷 Temas Históricos", use_container_width=True, help="Buscar quadrinhos sobre história no acervo"):
            pergunta_curador_acionada = "Eu gostaria de ler alguma coisa relacionado a temas históricos no Brasil ou no mundo."
    with col_cur2:
        if st.button("⭐ Melhores Não Lidos", use_container_width=True, help="Indicar HQs com boas notas que ainda não li"):
            pergunta_curador_acionada = "Quais são as melhores HQs que eu ainda não li na minha coleção?"
    with col_cur3:
        if st.button("🎲 Surpreenda-me", use_container_width=True, help="Pedir uma recomendação aleatória com base na história"):
            pergunta_curador_acionada = "Me dê uma recomendação especial da minha coleção para ler hoje com base no resumo da história."
    with col_cur_clear:
        if st.button("🗑️ Limpar", key="btn_limpar_curador", use_container_width=True, help="Limpar conversa do curador"):
            st.session_state["chat_mensagens_curador"] = [
                {
                    "role": "assistant",
                    "content": "👋 Conversa reiniciada! Como posso te ajudar a explorar seu catálogo de HQs hoje?"
                }
            ]
            st.rerun()

    # Container de exibição das mensagens do curador
    chat_container_curador = st.container(height=340)
    with chat_container_curador:
        for msg in st.session_state["chat_mensagens_curador"]:
            with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
                st.markdown(msg["content"])

    # Entrada de texto do Curador
    texto_chat_curador = st.chat_input("Pergunte ao Curador sobre suas HQs (ex: 'Quero ler algo de suspense ou terror')...", key="input_chat_curador")
    pergunta_curador_final = pergunta_curador_acionada or texto_chat_curador

    if pergunta_curador_final:
        st.session_state["chat_mensagens_curador"].append({"role": "user", "content": pergunta_curador_final})

        catalogo_atual = database.obter_contexto_hqs_para_chat()
        with st.spinner("🤖 Analisando os resumos e enredos da sua coleção..."):
            resposta_curador = gemini_service.consultar_chatbot_colecao(
                pergunta=pergunta_curador_final,
                catalogo_hqs=catalogo_atual,
                historico_mensagens=st.session_state["chat_mensagens_curador"][:-1],
                api_key=os.getenv("GEMINI_API_KEY"),
                modelo=modelo_selecionado
            )

        st.session_state["chat_mensagens_curador"].append({"role": "assistant", "content": resposta_curador})
        st.rerun()

st.markdown("---")

# -------------------------------------------------------------
# SEÇÃO 4: RADAR DE PREÇOS EM LOJAS & LISTA DE DESEJOS
# -------------------------------------------------------------
with st.expander("🛒 Radar de Preços em Lojas & Lista de Desejos", expanded=False):
    st.markdown(
        "Pesquise preços e disponibilidade de qualquer edição no mercado brasileiro (**Amazon, Magazine Luiza, Mercado Livre, Mundos Infinitos e Comix**) e adicione à sua **Lista de Desejos** com 1 clique!"
    )

    # 1. Campo de Consulta de Preços
    col_busca_p1, col_busca_p2 = st.columns([3, 1])
    with col_busca_p1:
        termo_preco_input = st.text_input(
            "Título da HQ para pesquisar preços nas lojas:",
            placeholder="Ex: Flash Omnibus Vol 1, Batman Cavaleiro das Trevas Panini, Watchmen...",
            key="input_busca_precos_lojas"
        )
    with col_busca_p2:
        st.write("")
        st.write("")
        btn_pesquisar_preco = st.button("🔍 Consultar Preços", type="primary", use_container_width=True, key="btn_executar_busca_preco")

    if btn_pesquisar_preco and termo_preco_input.strip():
        with st.spinner("🛒 Consultando preços nas 5 lojas (Amazon, MagazineLuiza, MercadoLivre, Mundos Infinitos, Comix)..."):
            dados_cotacao = gemini_service.pesquisar_precos_hq(
                termo_busca=termo_preco_input.strip(),
                api_key=os.getenv("GEMINI_API_KEY"),
                modelo=modelo_selecionado
            )
            st.session_state["radar_precos_resultado"] = dados_cotacao
            st.rerun()

    # 2. Exibição do Resultado da Cotação
    if st.session_state.get("radar_precos_resultado"):
        cotacao = st.session_state["radar_precos_resultado"]
        tit_hq = cotacao.get("titulo") or "HQ Pesquisada"
        ed_hq = cotacao.get("edicao") or ""
        lojas = cotacao.get("lojas", [])
        melhor_loja = cotacao.get("melhor_loja") or ""
        melhor_preco = float(cotacao.get("melhor_preco") or 0.0)
        link_melhor = cotacao.get("link_melhor_oferta") or ""

        st.markdown(f"### 📋 Cotação: **{tit_hq}** {f'({ed_hq})' if ed_hq else ''}")

        # Grid visual com as 5 lojas
        cols_lojas = st.columns(len(lojas) if lojas else 1)
        for idx, lj in enumerate(lojas):
            nome_loja = lj.get("loja", "")
            preco_str = lj.get("preco_str", "")
            link_loja = lj.get("link", "")
            status_lj = lj.get("status", "")

            with cols_lojas[idx % len(cols_lojas)]:
                eh_melhor = (nome_loja == melhor_loja and melhor_preco > 0)
                if eh_melhor:
                    st.success(f"**{nome_loja}**\n\n🏷️ **{preco_str}** *(Melhor Oferta!)*")
                elif preco_str and "não encontrado" not in preco_str.lower() and status_lj != "Titulo não encontrado":
                    st.info(f"**{nome_loja}**\n\n💵 **{preco_str}**")
                else:
                    st.warning(f"**{nome_loja}**\n\n❌ *Não encontrado*")

                if link_loja and status_lj == "Encontrado":
                    st.markdown(f"[🔗 Ver na Loja]({link_loja})")

        # Bloco de ação da Lista de Desejos
        st.markdown("---")
        if melhor_loja and melhor_preco > 0:
            st.success(f"🏆 **Melhor Oferta Encontrada:** [{melhor_loja} por R$ {melhor_preco:,.2f}]({link_melhor})")
            texto_btn_salvar = f"⭐ Adicionar '{tit_hq}' à Lista de Desejos ({melhor_loja} - R$ {melhor_preco:,.2f})"
        else:
            st.warning(
                "⚠️ **Título não encontrado disponível com estoque nas 5 lojas consultadas.**\n\n"
                "📌 **Dicas para uma pesquisa mais assertiva:**\n"
                "- **Simplifique o termo:** Em vez de *'Flash por Geoff Johns - Omnibus (Volume 1)'*, tente *'Flash Omnibus 1'* ou *'Flash Geoff Johns Vol 1'*.\n"
                "- **Evite pontuações e parênteses:** Caracteres como `( )`, `-` ou aspas podem filtrar os resultados das lojas.\n"
                "- **Adicione a Editora ou Formato:** Ex: *'Batman Cavaleiro das Trevas Panini'* ou *'Sandman Edição Definitiva 1'*."
            )
            texto_btn_salvar = f"⭐ Adicionar '{tit_hq}' à Lista de Desejos (sem preço definido)"

        col_act_w1, col_act_w2 = st.columns([3, 1])
        with col_act_w1:
            if st.button(texto_btn_salvar, type="primary", use_container_width=True, key="btn_add_radar_wishlist"):
                database.adicionar_item_lista_desejos(
                    titulo=cotacao.get("titulo", tit_hq),
                    edicao=cotacao.get("edicao", ed_hq),
                    editora=cotacao.get("editora", ""),
                    melhor_preco=melhor_preco,
                    melhor_loja=melhor_loja,
                    link_oferta=link_melhor,
                    observacoes=f"Cotado via Radar de Preços em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                )
                st.success(f"🎉 **'{tit_hq}'** adicionado com sucesso à sua Lista de Desejos!")
                st.session_state["radar_precos_resultado"] = None
                st.rerun()

        with col_act_w2:
            if st.button("❌ Fechar Cotação", use_container_width=True, key="btn_fechar_radar_cotacao"):
                st.session_state["radar_precos_resultado"] = None
                st.rerun()

    st.markdown("---")
    st.subheader("⭐ Sua Lista de Desejos Atual")

    df_desejos = database.listar_lista_desejos()

    if isinstance(df_desejos, pd.DataFrame) and not df_desejos.empty:
        st.write(
            f"Exibindo **{len(df_desejos)}** item(ns) na Lista de Desejos: *(Dê 2 cliques em qualquer célula para editar o Preço, Loja, Edição ou Link diretamente)*"
        )

        df_desejos_editado = st.data_editor(
            df_desejos,
            use_container_width=True,
            num_rows="fixed",
            disabled=["id", "criado_em"],
            hide_index=True,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "titulo": st.column_config.TextColumn("Título da HQ", required=True),
                "edicao": st.column_config.TextColumn("Edição / Vol."),
                "editora": st.column_config.TextColumn("Editora"),
                "melhor_preco": st.column_config.NumberColumn("Melhor Preço (R$)", format="R$ %.2f", min_value=0.0, step=1.0),
                "melhor_loja": st.column_config.TextColumn("Melhor Loja"),
                "link_oferta": st.column_config.TextColumn("Link da Oferta (URL)", help="Cole a URL direta da loja"),
                "observacoes": st.column_config.TextColumn("Observações / Origem"),
                "criado_em": st.column_config.TextColumn("Data da Inclusão", disabled=True)
            },
            key="tabela_desejos_editavel"
        )

        # Detecta alterações no grid
        houve_alt_desejos = not df_desejos_editado.equals(df_desejos)

        col_save_w_grid, col_info_w_grid = st.columns([1, 2])
        with col_save_w_grid:
            if houve_alt_desejos:
                if st.button("💾 Salvar Alterações na Lista", type="primary", use_container_width=True, key="btn_save_desejos_grid"):
                    for _, row in df_desejos_editado.iterrows():
                        database.atualizar_item_lista_desejos(
                            item_id=int(row["id"]),
                            titulo=str(row["titulo"]).strip(),
                            edicao=str(row.get("edicao", "") or "").strip(),
                            editora=str(row.get("editora", "") or "").strip(),
                            melhor_preco=float(row.get("melhor_preco") or 0.0),
                            melhor_loja=str(row.get("melhor_loja", "") or "").strip(),
                            link_oferta=str(row.get("link_oferta", "") or "").strip(),
                            observacoes=str(row.get("observacoes", "") or "").strip()
                        )
                    st.success("🎉 Alterações na Lista de Desejos salvas com sucesso!")
                    st.rerun()

        with col_info_w_grid:
            if houve_alt_desejos:
                st.caption("⚠️ Você fez alterações no grid. Clique em 'Salvar Alterações' para gravar.")

        st.markdown("---")
        st.write("🛠️ **Ações Rápidas da Lista de Desejos:**")
        col_act_w_edit, col_act_w_add, col_act_w_del = st.columns(3)

        with col_act_w_edit:
            if st.button("✏️ Editar por Formulário", use_container_width=True, help="Editar preço, loja e dados de um item por ID"):
                dialog_editar_desejo()

        with col_act_w_add:
            if st.button("➕ Adicionar Manualmente", use_container_width=True, help="Cadastrar novo quadrinho desejado sem precisar buscar"):
                dialog_adicionar_desejo_manual()

        with col_act_w_del:
            id_w_del = st.number_input("ID para remover:", min_value=1, step=1, key="input_del_wishlist")
            if st.button("🗑️ Remover da Lista", type="secondary", use_container_width=True):
                if database.deletar_item_lista_desejos(int(id_w_del)):
                    st.success(f"Item #{id_w_del} removido da Lista de Desejos!")
                    st.rerun()
                else:
                    st.warning("Item não encontrado.")
    else:
        st.info("Sua Lista de Desejos está vazia.")
        if st.button("➕ Adicionar Primeiro Item Manualmente", type="primary", use_container_width=True, key="btn_add_first_wish"):
            dialog_adicionar_desejo_manual()


