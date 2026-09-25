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

DEFAULT_NO_COVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "No_Image_Available.jpg")

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
    st.session_state["prateleira_atual"] = ""

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

if "historico_crud_assistido" not in st.session_state:
    st.session_state["historico_crud_assistido"] = []

if "hqs_em_revisao" not in st.session_state:
    st.session_state["hqs_em_revisao"] = []

if "ultimo_resultado_salvamento" not in st.session_state:
    st.session_state["ultimo_resultado_salvamento"] = None

if "pagina_atual" not in st.session_state:
    st.session_state["pagina_atual"] = "principal"


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

            # Prateleira: seleção entre todas as prateleiras cadastradas ou digitação manual
            lista_prats_cadastradas = [p for p in database.obter_prateleiras() if p and p != "Estante 1 - Prateleira 1"]
            prat_atual_hq = (hq_atual.get("prateleira") or "").strip()

            opcoes_dlg_prat = list(lista_prats_cadastradas)
            if prat_atual_hq and prat_atual_hq not in opcoes_dlg_prat:
                opcoes_dlg_prat.insert(0, prat_atual_hq)
            opcoes_dlg_prat.append("➕ Outra / Digitar nova prateleira...")

            idx_prat = opcoes_dlg_prat.index(prat_atual_hq) if prat_atual_hq in opcoes_dlg_prat else 0

            prat_selecionada = st.selectbox(
                "📍 Prateleira / Localização:",
                options=opcoes_dlg_prat,
                index=idx_prat,
                help="Selecione uma prateleira já cadastrada ou digite uma nova no campo abaixo."
            )
            prat_custom_input = st.text_input(
                "✍️ Digite uma nova prateleira (caso queira cadastrar/mudar para uma nova):",
                value="",
                placeholder="Preencha somente se desejar criar uma nova prateleira..."
            )

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
                    if prat_custom_input.strip():
                        nova_prateleira_final = prat_custom_input.strip()
                        database.cadastrar_prateleira(nova_prateleira_final)
                    elif prat_selecionada != "➕ Outra / Digitar nova prateleira...":
                        nova_prateleira_final = prat_selecionada
                    else:
                        nova_prateleira_final = prat_atual_hq

                    if database.atualizar_hq(
                        hq_id=int(id_para_editar),
                        titulo=novo_titulo,
                        edicao=nova_edicao,
                        editora=nova_editora,
                        prateleira=nova_prateleira_final,
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
def dialog_resenha(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    id_para_resenha = st.number_input("Informe o ID da HQ:", min_value=1, step=1, value=val_id, key=f"dlg_input_resenha_id_{id_padrao or 'padrao'}")
    hq_res = database.obter_hq_por_id(int(id_para_resenha))
    if hq_res:
        tit_hq = hq_res.get("titulo") or "Sem título"
        ed_hq = hq_res.get("edicao") or ""
        ed_str = f" ({ed_hq})" if ed_hq else ""
        edit_hq = hq_res.get("editora") or ""
        edit_str = f" | {edit_hq}" if edit_hq else ""
        st.markdown(f"📖 **HQ Selecionada:** **{tit_hq}**{ed_str}{edit_str} `(ID #{id_para_resenha})`")

        area_key = f"dlg_area_resenha_{id_para_resenha}"
        if area_key not in st.session_state:
            st.session_state[area_key] = hq_res.get("resenha") or ""

        # Aba de entrada: Digitação direta vs. Gravação / Envio de Áudio
        tab_texto, tab_audio = st.tabs(["✍️ Digitar / Revisar Resenha", "🎙️ Gravar / Enviar Áudio (IA)"])

        with tab_audio:
            st.caption("Fale livremente sobre a história, a arte e o que achou da HQ. O Gemini transcreverá sua fala automaticamente para texto!")
            tab_mic, tab_up_audio = st.tabs(["🎙️ Microfone ao Vivo", "📁 Enviar Arquivo de Áudio"])
            
            audio_para_transcrever = None
            mime_audio = "audio/wav"

            with tab_mic:
                gravacao_mic = st.audio_input("Grave sua resenha falando sobre a HQ:", key=f"dlg_mic_resenha_{id_para_resenha}")
                if gravacao_mic is not None:
                    audio_para_transcrever = gravacao_mic.getvalue()
                    mime_audio = gravacao_mic.type or "audio/wav"

            with tab_up_audio:
                upload_audio = st.file_uploader(
                    "Envie um arquivo de áudio (WhatsApp, celular, etc.):",
                    type=["wav", "mp3", "m4a", "ogg", "webm", "aac"],
                    key=f"dlg_up_audio_{id_para_resenha}"
                )
                if upload_audio is not None:
                    audio_para_transcrever = upload_audio.getvalue()
                    mime_audio = upload_audio.type or "audio/mp3"

            if audio_para_transcrever:
                col_tr1, col_tr2 = st.columns([1.5, 1])
                with col_tr1:
                    if st.button("✨ Transcrever Áudio com IA", type="primary", use_container_width=True, key=f"btn_transcrever_{id_para_resenha}"):
                        if not os.getenv("GEMINI_API_KEY"):
                            st.error("Chave de API do Gemini não configurada.")
                        else:
                            with st.spinner("🎙️ Transcrevendo seu áudio com Gemini..."):
                                try:
                                    texto_transcrito = gemini_service.transcrever_audio_resenha(
                                        audio_bytes=audio_para_transcrever,
                                        mime_type=mime_audio,
                                        api_key=os.getenv("GEMINI_API_KEY"),
                                        modelo=resolver_modelo("audio")
                                    )
                                    if texto_transcrito:
                                        st.session_state[area_key] = texto_transcrito
                                        st.success("🎉 Áudio transcrito com sucesso! O texto foi atualizado no campo abaixo.")
                                    else:
                                        st.warning("Não foi possível extrair texto do áudio fornecido.")
                                except Exception as e:
                                    st.error(f"Erro ao transcrever áudio: {e}")
                with col_tr2:
                    st.caption("💡 O texto transcrito é colocado na caixa abaixo para você revisar antes de salvar.")

        with tab_texto:
            st.caption("Você pode digitar, complementar ou revisar o texto transcrito abaixo:")

        texto_resenha = st.text_area(
            "Sua Resenha / O que achou da HQ:",
            value=st.session_state.get(area_key, ""),
            height=130,
            key=area_key,
            placeholder="Escreva suas impressões pessoais sobre esta edição..."
        )

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            if st.button("💾 Salvar Resenha", type="primary", use_container_width=True, key="dlg_btn_save_resenha"):
                database.definir_resenha(int(id_para_resenha), texto_resenha)
                st.success("Resenha salva com sucesso!")
                st.rerun()
        with col_r2:
            if st.button("❌ Fechar", key="dlg_btn_cancel_resenha", use_container_width=True):
                st.rerun()
    else:
        st.info(f"Nenhum quadrinho com o ID #{id_para_resenha} foi encontrado.")
        if st.button("❌ Fechar", key="dlg_btn_close_res_empty", use_container_width=True):
            st.rerun()

@st.dialog("⭐ Avaliar HQ")
def dialog_avaliar_hq():
    id_para_avaliar = st.number_input("Informe o ID da HQ:", min_value=1, step=1, key="dlg_input_rate_id")
    hq_rate = database.obter_hq_por_id(int(id_para_avaliar))
    if hq_rate:
        tit_hq = hq_rate.get("titulo") or "Sem título"
        ed_hq = hq_rate.get("edicao") or ""
        ed_str = f" ({ed_hq})" if ed_hq else ""
        st.markdown(f"📖 **HQ:** **{tit_hq}**{ed_str} `(ID #{id_para_avaliar})`")
        nota_atual = int(hq_rate.get("avaliacao") or 0)
        nova_nota = st.selectbox("Selecione a Nota:", options=[0, 1, 2, 3, 4, 5], index=nota_atual, key="dlg_sel_fast_nota", format_func=lambda x: "⚪ Sem Avaliação (0)" if x == 0 else f"{'⭐' * x} ({x} de 5)")
        col_av1, col_av2 = st.columns(2)
        with col_av1:
            if st.button("💾 Salvar Nota", type="primary", use_container_width=True, key="dlg_btn_save_nota"):
                database.definir_avaliacao(int(id_para_avaliar), nova_nota)
                st.success("Avaliação salva!")
                st.rerun()
        with col_av2:
            if st.button("❌ Fechar", key="dlg_btn_cancel_nota", use_container_width=True):
                st.rerun()
    else:
        st.info(f"Nenhum quadrinho com o ID #{id_para_avaliar} foi encontrado.")
        if st.button("❌ Fechar", key="dlg_btn_close_rate_empty", use_container_width=True):
            st.rerun()

@st.dialog("📖 Alternar Status de Leitura")
def dialog_alternar_leitura():
    id_para_toggle = st.number_input("Informe o ID da HQ:", min_value=1, step=1, key="dlg_input_toggle_id")
    hq_toggle = database.obter_hq_por_id(int(id_para_toggle))
    if hq_toggle:
        tit_hq = hq_toggle.get("titulo") or "Sem título"
        st.markdown(f"📖 **HQ:** **{tit_hq}** `(ID #{id_para_toggle})`")
        novo = database.alternar_status_leitura(int(id_para_toggle))
        st.success(f"Status alterado para **{novo}**!")
        st.rerun()
    else:
        st.info(f"Nenhum quadrinho com o ID #{id_para_toggle} foi encontrado.")
        if st.button("❌ Fechar", key="dlg_btn_close_toggle_empty", use_container_width=True):
            st.rerun()

@st.dialog("🗑️ Excluir HQ")
def dialog_excluir_hq():
    id_para_excluir = st.number_input("Informe o ID da HQ a excluir:", min_value=1, step=1, key="dlg_input_delete_id")
    hq_del = database.obter_hq_por_id(int(id_para_excluir))
    if hq_del:
        tit_hq = hq_del.get("titulo") or "Sem título"
        st.markdown(f"⚠️ Deseja realmente excluir **'{tit_hq}'** `(ID #{id_para_excluir})`?")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if st.button("🗑️ Confirmar Exclusão", type="primary", use_container_width=True, key="dlg_btn_confirm_del"):
                database.deletar_hq(int(id_para_excluir))
                st.success(f"HQ '{tit_hq}' excluída com sucesso!")
                st.rerun()
        with col_d2:
            if st.button("❌ Cancelar", key="dlg_btn_cancel_del", use_container_width=True):
                st.rerun()
    else:
        st.info(f"Nenhum quadrinho com o ID #{id_para_excluir} foi encontrado.")
        if st.button("❌ Fechar", key="dlg_btn_close_del_empty", use_container_width=True):
            st.rerun()
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
        options=[
            "Automático (Otimizado)",
            "gemini-3.1-pro-preview",
            "gemini-pro-latest",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3-flash-preview"
        ],
        index=0,
        help="Automático: gemini-3.6-flash para Visão/Lombadas e Chat com máxima velocidade e compatibilidade de cota."
    )

    def resolver_modelo(tipo: str) -> str:
        if modelo_selecionado != "Automático (Otimizado)":
            return modelo_selecionado
        return "gemini-3.6-flash"

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
        st.markdown(
            """
            <style>
            div.st-key-btn_metric_prat {
                margin-bottom: 0.5rem !important;
            }
            div.st-key-btn_metric_prat button {
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
                padding: 0 !important;
                margin: 0 !important;
                text-align: left !important;
                justify-content: flex-start !important;
                align-items: flex-start !important;
                cursor: pointer !important;
                height: auto !important;
                min-height: 0 !important;
                outline: none !important;
            }
            div.st-key-btn_metric_prat button,
            div.st-key-btn_metric_prat button * {
                font-size: 2.25rem !important;
                font-weight: 700 !important;
                line-height: 1.15 !important;
                color: inherit !important;
            }
            div.st-key-btn_metric_prat button:hover,
            div.st-key-btn_metric_prat button:hover * {
                color: #ff4b4b !important;
                text-decoration: underline !important;
            }
            div.st-key-btn_metric_prat button:active,
            div.st-key-btn_metric_prat button:focus {
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
            }
            </style>
            <div data-testid="stMetricLabel" style="margin-bottom: 2px;">
                <p style="margin: 0; font-size: 14px; font-weight: 400; line-height: 1.25; color: inherit; opacity: 0.8;">Prateleiras</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button(str(stats["total_prateleiras"]), key="btn_metric_prat", help="Clique no número para abrir o Gerenciador de Prateleiras"):
            st.session_state["pagina_atual"] = "editar_prateleiras"
            st.rerun()
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
# PÁGINA DEDICADA: GERENCIADOR E EDIÇÃO DE PRATELEIRAS
# -------------------------------------------------------------
def voltar_ao_catalogo():
    st.session_state["pagina_atual"] = "principal"
    if "pagina" in st.query_params:
        del st.query_params["pagina"]
    st.rerun()

def renderizar_pagina_editar_prateleiras():
    col_nav_t, col_nav_b = st.columns([3, 1.2])
    with col_nav_t:
        st.title("📍 Gerenciador & Edição de Prateleiras")
        st.markdown("Cadastre novas prateleiras, renomeie, unifique e organize as estantes da sua coleção sem poluir a página principal.")
    with col_nav_b:
        st.write("")
        if st.button("⬅️ Voltar ao Catálogo", type="primary", use_container_width=True, key="btn_voltar_cat_top"):
            voltar_ao_catalogo()

    st.markdown("---")

    prateleiras_detalhes = database.listar_prateleiras_detalhadas()
    nomes_prateleiras = [p["prateleira"] for p in prateleiras_detalhes] if prateleiras_detalhes else []

    # 1. Formulário de Cadastro de Nova Prateleira
    with st.container(border=True):
        st.subheader("➕ Cadastrar Nova Prateleira")
        st.markdown("Crie uma nova prateleira/localização para organizar suas futuras fotos e edições catalogadas.")
        col_n1, col_n2 = st.columns([2.5, 1.5])
        with col_n1:
            nome_nova_prat = st.text_input(
                "Nome da Nova Prateleira:",
                placeholder="Ex: Estante Marvel - Prateleira 4, Caixa Mangás 3...",
                key="input_criar_nova_prat"
            )
        with col_n2:
            st.write("")
            st.write("")
            btn_criar_prat = st.button("➕ Cadastrar Prateleira", type="primary", use_container_width=True, key="btn_cadastrar_nova_prat")

        if btn_criar_prat:
            if not nome_nova_prat.strip():
                st.error("Informe um nome válido para a nova prateleira.")
            elif nome_nova_prat.strip() in nomes_prateleiras:
                st.warning(f"A prateleira '{nome_nova_prat.strip()}' já existe na sua coleção.")
            else:
                database.cadastrar_prateleira(nome_nova_prat.strip())
                st.session_state["prateleira_atual"] = nome_nova_prat.strip()
                st.success(f"🎉 Nova prateleira **'{nome_nova_prat.strip()}'** cadastrada com sucesso e definida como sua prateleira ativa de catalogação!")
                st.rerun()

    st.markdown("---")

    if not prateleiras_detalhes:
        st.info("ℹ️ Nenhuma prateleira com HQs cadastradas no momento. Cadastre novas prateleiras acima ou tire fotos na página principal para começar a organizar sua coleção!")
        if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_cat_vazio"):
            voltar_ao_catalogo()
        return

    # 2. Formulário de Renomear Prateleira
    with st.container(border=True):
        st.subheader("✏️ Renomear Prateleira Existente")
        st.markdown(
            "Selecione uma prateleira existente e digite o novo nome. "
            "**Todas as HQs alocadas nela serão atualizadas automaticamente.**"
        )

        col_ren1, col_ren2 = st.columns(2)
        with col_ren1:
            prat_antiga_sel = st.selectbox(
                "📍 Selecione a prateleira para renomear:",
                options=nomes_prateleiras,
                key="sel_prat_para_renomear"
            )
        with col_ren2:
            novo_nome_prat = st.text_input(
                "✍️ Digite o novo nome da prateleira:",
                value=prat_antiga_sel,
                key="input_novo_nome_prat",
                help="Ex: Estante Marvel - Nicho 1, Caixa Mangás 2, Prateleira DC..."
            )

        col_b_ren, _ = st.columns([1.5, 3])
        with col_b_ren:
            if st.button("💾 Salvar Novo Nome da Prateleira", type="primary", use_container_width=True, key="btn_confirmar_renomear_prat"):
                if not novo_nome_prat.strip():
                    st.error("O novo nome da prateleira não pode ser vazio.")
                elif novo_nome_prat.strip() == prat_antiga_sel.strip():
                    st.info("O novo nome informado é idêntico ao nome atual.")
                else:
                    qtd_alt = database.renomear_prateleira(prat_antiga_sel, novo_nome_prat.strip())
                    if st.session_state.get("prateleira_atual") == prat_antiga_sel:
                        st.session_state["prateleira_atual"] = novo_nome_prat.strip()
                    st.success(f"🎉 Prateleira renomeada com sucesso! **{qtd_alt} HQ(s)** foram atualizadas para **'{novo_nome_prat.strip()}'**.")
                    st.rerun()

    st.markdown("---")

    # 3. Tabela Resumo das Prateleiras
    st.subheader(f"📊 Prateleiras Cadastradas ({len(prateleiras_detalhes)})")
    df_prat = pd.DataFrame(prateleiras_detalhes)
    st.dataframe(
        df_prat,
        use_container_width=True,
        hide_index=True,
        column_config={
            "prateleira": st.column_config.TextColumn("📍 Nome da Prateleira"),
            "total_hqs": st.column_config.NumberColumn("📚 Total de HQs"),
            "total_lidos": st.column_config.NumberColumn("📖 Lidos"),
            "total_nao_lidos": st.column_config.NumberColumn("⏳ Não Lidos"),
            "media_avaliacao": st.column_config.NumberColumn("⭐ Média Avaliação", format="%.1f")
        }
    )

    # 4. Inspecionar HQs por Prateleira
    with st.expander("🔍 Ver HQs alocadas em cada prateleira", expanded=False):
        prat_insp_sel = st.selectbox("Escolha uma prateleira para listar as obras:", options=nomes_prateleiras, key="sel_prat_inspect")
        df_hqs_prat = database.listar_todas_hqs(prateleira_filtro=prat_insp_sel)
        if isinstance(df_hqs_prat, pd.DataFrame) and not df_hqs_prat.empty:
            cols_vis = ["id", "titulo", "edicao", "editora", "genero", "lido", "avaliacao"]
            cols_exist = [c for c in cols_vis if c in df_hqs_prat.columns]
            st.dataframe(df_hqs_prat[cols_exist], use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhuma HQ encontrada nesta prateleira.")

    st.markdown("---")
    if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_cat_bottom", use_container_width=True):
        voltar_ao_catalogo()


# Controle de exibição de página dedicada
if st.query_params.get("pagina") == "editar_prateleiras" or st.session_state.get("pagina_atual") == "editar_prateleiras":
    renderizar_pagina_editar_prateleiras()
    st.stop()


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

# Gerenciamento da Edição do Dia na sessão e no banco
data_hoje = datetime.now().strftime("%Y-%m-%d")
if st.session_state.get("data_edicao_do_dia") != data_hoje:
    st.session_state["data_edicao_do_dia"] = data_hoje
    st.session_state["edicao_do_dia_id"] = None

hq_dia = None
if st.session_state.get("edicao_do_dia_id"):
    hq_dia = database.obter_hq_por_id(int(st.session_state["edicao_do_dia_id"]))

if not hq_dia:
    hq_dia = database.obter_edicao_do_dia(data_str=data_hoje)
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
                if st.button("🎲 Sortear Outra", key="btn_sortear_outra_dia", use_container_width=True, help="Sortear aleatoriamente outro quadrinho da sua coleção sem repetir recentes"):
                    outra_hq = database.sortear_edicao_do_dia(excluir_id=int(hq_dia["id"]), data_destaque=data_hoje)
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

lista_prateleiras_cadastradas = [p for p in database.obter_prateleiras() if p and p != "Estante 1 - Prateleira 1"]

with col_shelf:
    if lista_prateleiras_cadastradas:
        prat_atual = st.session_state.get("prateleira_atual", "")
        opcoes_prat = ["-- Selecione uma prateleira --"] + list(lista_prateleiras_cadastradas)
        if prat_atual and prat_atual not in opcoes_prat and prat_atual != "➕ Nova / Digitar outro nome...":
            opcoes_prat.insert(1, prat_atual)
        opcoes_prat.append("➕ Nova / Digitar outro nome...")

        idx_padrao = opcoes_prat.index(prat_atual) if prat_atual in opcoes_prat else 0

        prat_selecionada = st.selectbox(
            "📍 **Prateleira / Localização Atual:**",
            options=opcoes_prat,
            index=idx_padrao,
            help="Selecione uma prateleira já cadastrada ou digite uma nova para onde as HQs fotografadas serão salvas."
        )

        if prat_selecionada == "-- Selecione uma prateleira --":
            prateleira_input = ""
            st.session_state["prateleira_atual"] = ""
        elif prat_selecionada == "➕ Nova / Digitar outro nome...":
            prateleira_input = st.text_input(
                "✍️ Digite o nome da nova prateleira:",
                placeholder="Ex: Estante Marvel - Prateleira 1, Caixa Mangás...",
                help="Digite o nome da nova prateleira."
            )
            if prateleira_input.strip():
                st.session_state["prateleira_atual"] = prateleira_input.strip()
        else:
            prateleira_input = prat_selecionada
            st.session_state["prateleira_atual"] = prat_selecionada
    else:
        prateleira_input = st.text_input(
            "📍 **Prateleira / Localização Atual:**",
            value=st.session_state.get("prateleira_atual", ""),
            placeholder="Ex: Estante Marvel - Prateleira 1, Caixa Mangás...",
            help="Digite a prateleira ou localização onde as HQs estão guardadas."
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
# PROCESSAMENTO COM IA & REVISÃO INTERATIVA
# -------------------------------------------------------------
if imagem_para_processar is not None:
    st.image(imagem_para_processar, caption="Pré-visualização da Foto Capturada", use_container_width=True)

    col_btn_proc, _ = st.columns([1.2, 2])
    with col_btn_proc:
        botao_analisar = st.button("🔍 1. Identificar HQs na Foto", type="primary", use_container_width=True)

    if botao_analisar:
        if not os.getenv("GEMINI_API_KEY"):
            st.error("❌ Chave de API do Gemini não configurada! Insira-a na barra lateral.")
        else:
            status_placeholder = st.empty()
            with st.spinner(f"🤖 Analisando lombadas com {resolver_modelo('visao')}..."):
                try:
                    def atualizar_status(mensagem: str):
                        status_placeholder.info(mensagem, icon="⏳")

                    # Envia para a API do Gemini com retentativas automáticas e fallback
                    hqs_detectadas = gemini_service.processar_foto_prateleira(
                        imagem=imagem_para_processar,
                        api_key=os.getenv("GEMINI_API_KEY"),
                        modelo=resolver_modelo("visao"),
                        status_callback=atualizar_status
                    )
                    status_placeholder.empty()

                    if hqs_detectadas:
                        st.session_state["hqs_em_revisao"] = hqs_detectadas
                        st.session_state["ultimo_resultado_salvamento"] = None
                        st.rerun()
                    else:
                        st.warning("⚠️ Nenhum quadrinho pôde ser identificado nesta foto. Tente aproximar ou melhorar a iluminação.")
                except Exception as ex:
                    status_placeholder.empty()
                    st.error(f"Erro ao processar imagem: {ex}")

# Exibe a tabela de revisão e edição se houver itens identificados aguardando confirmação
if st.session_state.get("hqs_em_revisao"):
    st.markdown("### 📋 2. Revisão e Edição dos Itens Identificados")
    st.info(
        "💡 **Edição Manual Habilitada:** Você pode alterar qualquer dado diretamente nas células abaixo (Título, Edição, Editora, Autores, Resumo), adicionar novas linhas ou excluir itens antes de confirmar o salvamento.",
        icon="✏️"
    )

    df_revisao = pd.DataFrame(st.session_state["hqs_em_revisao"])
    colunas_obrigatorias = ["titulo", "edicao", "editora", "genero", "escritor", "ilustrador", "resumo"]
    for col in colunas_obrigatorias:
        if col not in df_revisao.columns:
            df_revisao[col] = ""

    df_revisao = df_revisao[colunas_obrigatorias]

    df_editado = st.data_editor(
        df_revisao,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "titulo": st.column_config.TextColumn("Título da HQ *", required=True),
            "edicao": st.column_config.TextColumn("Edição / Volume"),
            "editora": st.column_config.TextColumn("Editora"),
            "genero": st.column_config.TextColumn("Gênero"),
            "escritor": st.column_config.TextColumn("Roteirista / Escritor"),
            "ilustrador": st.column_config.TextColumn("Desenhista / Arte"),
            "resumo": st.column_config.TextColumn("Resumo da História")
        },
        key="data_editor_revisao_hqs"
    )

    st.caption(f"📍 Os itens confirmados serão associados à prateleira: **`{prateleira_input.strip() or 'Não especificada'}`**")

    col_salvar, col_descartar, _ = st.columns([1.5, 1.2, 2])
    with col_salvar:
        botao_confirmar_salvar = st.button("💾 3. Confirmar & Salvar no Catálogo", type="primary", use_container_width=True)
    with col_descartar:
        botao_descartar = st.button("🗑️ Descartar Revisão", use_container_width=True)

    if botao_descartar:
        st.session_state["hqs_em_revisao"] = []
        st.rerun()

    if botao_confirmar_salvar:
        if not prateleira_input.strip() or prateleira_input.strip() == "-- Selecione uma prateleira --":
            st.error("❌ Por favor, selecione ou informe o nome da Prateleira Atual antes de salvar.")
        else:
            itens_para_salvar = []
            if isinstance(df_editado, pd.DataFrame):
                registros = df_editado.to_dict(orient="records")
            else:
                registros = st.session_state["hqs_em_revisao"]

            for r in registros:
                tit = str(r.get("titulo") or "").strip()
                if tit:
                    itens_para_salvar.append(r)

            if not itens_para_salvar:
                st.warning("⚠️ Nenhum quadrinho com título preenchido para salvar.")
            else:
                resultado = database.salvar_hqs(
                    itens_para_salvar,
                    prateleira_input.strip(),
                    ignorar_duplicadas=True,
                    retornar_detalhes=True
                )
                st.session_state["ultimos_itens_salvos"] = resultado["itens_salvos"]
                st.session_state["ultimo_resultado_salvamento"] = resultado
                st.session_state["hqs_em_revisao"] = []
                st.rerun()

# Exibe o feedback do último salvamento se houver
if st.session_state.get("ultimo_resultado_salvamento"):
    resultado_ultimo = st.session_state["ultimo_resultado_salvamento"]
    total_salvo = resultado_ultimo["salvos"]
    total_duplicados = resultado_ultimo["duplicados"]
    itens_duplicados = resultado_ultimo.get("itens_duplicados", [])
    prat_usada = prateleira_input.strip() if prateleira_input.strip() and prateleira_input.strip() != "-- Selecione uma prateleira --" else "sua coleção"

    if total_salvo > 0 and total_duplicados > 0:
        st.success(f"🎉 **{total_salvo} HQ(s) nova(s) salva(s) com sucesso** na prateleira `{prat_usada}`!")
        st.info(f"ℹ️ **{total_duplicados} HQ(s) ignorada(s)** pois já constavam no catálogo com mesmo Título e Edição.")
    elif total_salvo > 0:
        st.success(f"🎉 **{total_salvo} HQ(s) salva(s) com sucesso** na prateleira `{prat_usada}`!")
    elif total_duplicados > 0:
        st.warning(f"⚠️ Nenhuma nova HQ gravada: todas as **{total_duplicados} HQ(s)** já estavam cadastradas no catálogo.")

    if itens_duplicados:
        with st.expander(f"🔍 Ver detalhes das {len(itens_duplicados)} HQ(s) ignoradas por duplicidade"):
            for dup in itens_duplicados:
                st.write(f"- ⚠️ **{dup.get('titulo')}** ({dup.get('edicao') or 'Sem Edição'}) - Editora: *{dup.get('editora') or 'Desconhecida'}* — `{dup.get('motivo_duplicata')}`")

# Exibe resumo visual imediato dos últimos itens detectados e salvos
if st.session_state.get("ultimos_itens_salvos"):
    st.markdown("### 📋 Itens Recém-Salvos no Catálogo")
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
            with st.container(border=True):
                st.info(f"🎯 **{qtd_sel} HQ(s) selecionada(s) no CheckBox:** Escolha uma ação em lote:")
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

                st.markdown("---")
                # Alteração de Prateleira em Massa
                lista_prats_massa = [p for p in database.obter_prateleiras() if p and p != "Estante 1 - Prateleira 1"]
                opcoes_massa_prat = ["-- Selecione a prateleira de destino --"] + list(lista_prats_massa) + ["➕ Outra / Digitar nova prateleira..."]

                col_m_txt, col_m_sel, col_m_btn = st.columns([1.5, 2.5, 1.5])
                with col_m_txt:
                    st.write("📍 **Alterar Prateleira em Massa:**")
                with col_m_sel:
                    prat_massa_sel = st.selectbox(
                        "Prateleira de destino:",
                        options=opcoes_massa_prat,
                        key="sel_bulk_prat_dest",
                        label_visibility="collapsed"
                    )
                    prat_massa_digitada = ""
                    if prat_massa_sel == "➕ Outra / Digitar nova prateleira...":
                        prat_massa_digitada = st.text_input(
                            "Digite o nome da nova prateleira:",
                            placeholder="Ex: Estante 3 - Quadrinhos Europeus",
                            key="input_bulk_prat_new",
                            label_visibility="collapsed"
                        )
                with col_m_btn:
                    if st.button("📍 Mover para Prateleira", type="primary", use_container_width=True, key="btn_bulk_apply_prat"):
                        if prat_massa_sel == "➕ Outra / Digitar nova prateleira...":
                            nova_prat_final = prat_massa_digitada.strip()
                        elif prat_massa_sel != "-- Selecione a prateleira de destino --":
                            nova_prat_final = prat_massa_sel.strip()
                        else:
                            nova_prat_final = ""

                        if not nova_prat_final:
                            st.error("Selecione ou digite uma prateleira de destino válida.")
                        else:
                            qtd_movidas = database.atualizar_prateleira_em_massa(ids_selecionados, nova_prat_final)
                            st.success(f"🎉 **{qtd_movidas} HQ(s)** alterada(s) para a prateleira **'{nova_prat_final}'** com sucesso!")
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

    # Opção de envio por Áudio para o Curador
    with st.expander("🎙️ Falar com o Curador por Voz / Áudio", expanded=False):
        st.caption("Fale diretamente com o Curador sobre temas, sugestões de leitura ou dúvidas sobre seu acervo:")
        tab_mic_c, tab_up_c = st.tabs(["🎙️ Gravar Microfone", "📁 Enviar Arquivo de Áudio"])
        audio_curador = None
        mime_curador = "audio/wav"
        with tab_mic_c:
            rec_c = st.audio_input("Fale sua pergunta sobre o acervo:", key="rec_mic_curador")
            if rec_c is not None:
                audio_curador = rec_c.getvalue()
                mime_curador = rec_c.type or "audio/wav"
        with tab_up_c:
            up_c = st.file_uploader("Ou envie áudio gravado:", type=["wav", "mp3", "m4a", "ogg", "webm", "aac"], key="up_audio_curador")
            if up_c is not None:
                audio_curador = up_c.getvalue()
                mime_curador = up_c.type or "audio/mp3"

        if audio_curador:
            if st.button("✨ Enviar Pergunta por Áudio", type="primary", key="btn_enviar_audio_curador", use_container_width=True):
                if not os.getenv("GEMINI_API_KEY"):
                    st.error("Chave de API do Gemini não configurada!")
                else:
                    with st.spinner("🎙️ Transcrevendo sua fala com Gemini..."):
                        try:
                            pergunta_curador_acionada = gemini_service.transcrever_audio(
                                audio_bytes=audio_curador,
                                mime_type=mime_curador,
                                tipo_contexto="curador",
                                api_key=os.getenv("GEMINI_API_KEY"),
                                modelo=resolver_modelo("audio")
                            )
                        except Exception as e:
                            st.error(f"Erro ao transcrever áudio: {e}")

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
                modelo=resolver_modelo("chat")
            )

        st.session_state["chat_mensagens_curador"].append({"role": "assistant", "content": resposta_curador})
        st.rerun()

st.markdown("---")

# -------------------------------------------------------------
# SEÇÃO 4: OPERAÇÕES DE CRUD ASSISTIDAS (AGENT / MCP)
# -------------------------------------------------------------
with st.expander("🛠️ Operações de CRUD assistidas", expanded=True):
    st.markdown(
        "Gerencie seu acervo de quadrinhos através de comandos em linguagem natural com a IA. "
        "Você pode **adicionar** novas HQs com enriquecimento de dados e anotação de compras, **remover** edições existentes, **atualizar** status de leitura/avaliação/prateleira, ou gerenciar sua Lista de Desejos."
    )

    comando_audio_acionado = None

    tab_crud_texto, tab_crud_audio = st.tabs(["✍️ Digitar Instrução", "🎙️ Falar Instrução por Áudio"])

    with tab_crud_texto:
        # Formulário para envio do comando digitado
        with st.form("form_crud_assistido", clear_on_submit=True):
            texto_comando = st.text_input(
                "💬 **Digite a instrução para o assistente de CRUD:**",
                placeholder="Ex: 'Adicione à minha coleção a edição definitiva de Watchmen que comprei hoje por R$ 120,00' ou 'Remova da minha coleção a edição X'...",
                key="input_texto_crud_cmd"
            )
            col_exec_btn, _ = st.columns([1.2, 4])
            with col_exec_btn:
                btn_executar_crud = st.form_submit_button("🚀 Executar Ação", type="primary", use_container_width=True)

    with tab_crud_audio:
        st.caption("Fale naturalmente seu comando de gerenciamento do acervo (adicionar, remover ou alterar edições):")
        tab_mic_crud, tab_up_crud = st.tabs(["🎙️ Gravar Microfone", "📁 Enviar Arquivo de Áudio"])
        audio_crud = None
        mime_crud = "audio/wav"

        with tab_mic_crud:
            rec_crud = st.audio_input("Grave seu comando (ex: 'Adicione Watchmen à minha coleção que comprei por 120 reais'):", key="rec_mic_crud")
            if rec_crud is not None:
                audio_crud = rec_crud.getvalue()
                mime_crud = rec_crud.type or "audio/wav"

        with tab_up_crud:
            up_crud = st.file_uploader("Selecione um arquivo de áudio:", type=["wav", "mp3", "m4a", "ogg", "webm", "aac"], key="up_audio_crud")
            if up_crud is not None:
                audio_crud = up_crud.getvalue()
                mime_crud = up_crud.type or "audio/mp3"

        if audio_crud:
            if st.button("🚀 Transcrever & Executar Ação por Voz", type="primary", key="btn_exec_audio_crud", use_container_width=True):
                if not os.getenv("GEMINI_API_KEY"):
                    st.error("Chave de API do Gemini não configurada!")
                else:
                    with st.spinner("🎙️ Transcrevendo seu comando com Gemini..."):
                        try:
                            comando_audio_acionado = gemini_service.transcrever_audio(
                                audio_bytes=audio_crud,
                                mime_type=mime_crud,
                                tipo_contexto="crud",
                                api_key=os.getenv("GEMINI_API_KEY"),
                                modelo=resolver_modelo("audio")
                            )
                        except Exception as e:
                            st.error(f"Erro ao transcrever áudio: {e}")

    comando_final = comando_audio_acionado or (texto_comando.strip() if 'btn_executar_crud' in locals() and btn_executar_crud and texto_comando.strip() else None)

    if comando_final:
        if not os.getenv("GEMINI_API_KEY"):
            st.error("❌ Chave de API do Gemini não configurada! Insira-a na barra lateral.")
        else:
            with st.spinner("🤖 Interpretando comando e executando operação no banco de dados..."):
                catalogo_completo = database.obter_contexto_hqs_para_chat()
                prat_padrao = st.session_state.get("prateleira_atual", "Estante 1 - Prateleira 1")

                try:
                    resultado_crud = gemini_service.processar_comando_crud_assistido(
                        comando=comando_final,
                        catalogo_hqs=catalogo_completo,
                        prateleira_padrao=prat_padrao,
                        api_key=os.getenv("GEMINI_API_KEY"),
                        modelo=resolver_modelo("crud")
                    )
                except Exception as e:
                    resultado_crud = {
                        "acao": "erro",
                        "explicacao": f"Erro ao processar instrução com a IA: {e}",
                        "dados": {}
                    }

                acao = resultado_crud.get("acao", "desconhecido")
                explicacao = resultado_crud.get("explicacao", "")
                dados = resultado_crud.get("dados", {})

                # Execução da Ação de CRUD no Banco de Dados
                registro_log = {
                    "comando": comando_final,
                    "acao": acao,
                    "explicacao": explicacao,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "status": "info",
                    "detalhes": ""
                }

                if acao == "adicionar":
                    titulo = (dados.get("titulo") or "").strip()
                    if not titulo:
                        registro_log["status"] = "erro"
                        registro_log["detalhes"] = "A IA não conseguiu identificar o título da HQ para cadastrar."
                    else:
                        edicao = (dados.get("edicao") or "").strip()
                        editora = (dados.get("editora") or "Desconhecida").strip()
                        genero = (dados.get("genero") or "Outro").strip()
                        escritor = (dados.get("escritor") or "Não informado").strip()
                        ilustrador = (dados.get("ilustrador") or "Não informado").strip()
                        prateleira_item = (dados.get("prateleira") or prat_padrao).strip()
                        lido = (dados.get("lido") or "Não Lido").strip()
                        try:
                            avaliacao = int(dados.get("avaliacao") or 0)
                        except (ValueError, TypeError):
                            avaliacao = 0
                        resumo = (dados.get("resumo") or "").strip()
                        resenha = (dados.get("resenha") or "").strip()
                        preco_pago = dados.get("preco_pago")
                        if preco_pago and f"R$ {preco_pago}" not in resenha and f"{preco_pago}" not in resenha:
                            info_preco = f"Comprado por R$ {float(preco_pago):.2f}"
                            resenha = f"{info_preco}. {resenha}".strip()

                        # Inserção da HQ
                        resultado_salvar = database.salvar_hqs(
                            itens=[{
                                "titulo": titulo,
                                "edicao": edicao,
                                "editora": editora,
                                "genero": genero,
                                "escritor": escritor,
                                "ilustrador": ilustrador,
                                "prateleira": prateleira_item,
                                "lido": lido,
                                "avaliacao": avaliacao,
                                "resumo": resumo,
                                "resenha": resenha
                            }],
                            prateleira=prateleira_item,
                            ignorar_duplicadas=False,
                            retornar_detalhes=True
                        )
                        if resultado_salvar["salvos"] > 0:
                            registro_log["status"] = "sucesso"
                            registro_log["detalhes"] = f"🎉 **'{titulo}'** adicionado com sucesso na prateleira `{prateleira_item}`!"
                        else:
                            registro_log["status"] = "aviso"
                            registro_log["detalhes"] = f"⚠️ HQ '{titulo}' não foi inserida (já existia ou dados inválidos)."

                elif acao == "remover":
                    titulo = (dados.get("titulo") or "").strip()
                    edicao = (dados.get("edicao") or "").strip()
                    hqs_encontradas = database.buscar_hqs_por_titulo_ou_edicao(titulo, edicao)
                    if hqs_encontradas:
                        removida = hqs_encontradas[0]
                        database.deletar_hq(int(removida["id"]))
                        registro_log["status"] = "sucesso"
                        registro_log["detalhes"] = f"🗑️ **'{removida['titulo']}'** (ID #{removida['id']}) removido com sucesso da coleção!"
                    else:
                        registro_log["status"] = "aviso"
                        registro_log["detalhes"] = f"⚠️ Nenhuma HQ correspondente a '{titulo}' foi encontrada para remoção."

                elif acao == "atualizar":
                    titulo = (dados.get("titulo") or "").strip()
                    edicao = (dados.get("edicao") or "").strip()
                    campo = dados.get("campo", "")
                    novo_valor = dados.get("novo_valor", "")

                    hqs_encontradas = database.buscar_hqs_por_titulo_ou_edicao(titulo, edicao)
                    if hqs_encontradas:
                        hq_alvo = hqs_encontradas[0]
                        if campo == "lido":
                            status_novo = "Lido" if "lido" in str(novo_valor).lower() and "não" not in str(novo_valor).lower() else "Não Lido"
                            database.definir_status_leitura(hq_alvo["id"], status_novo)
                            registro_log["status"] = "sucesso"
                            registro_log["detalhes"] = f"📖 Status de **'{hq_alvo['titulo']}'** alterado para **{status_novo}**!"
                        elif campo == "avaliacao":
                            try:
                                nova_nota = max(0, min(5, int(novo_valor)))
                                database.definir_avaliacao(hq_alvo["id"], nova_nota)
                                registro_log["status"] = "sucesso"
                                registro_log["detalhes"] = f"⭐ Avaliação de **'{hq_alvo['titulo']}'** alterada para **{nova_nota}/5**!"
                            except ValueError:
                                registro_log["status"] = "erro"
                                registro_log["detalhes"] = f"Valor de nota inválido: '{novo_valor}'"
                        elif campo == "prateleira":
                            database.atualizar_hq(
                                hq_id=int(hq_alvo["id"]),
                                titulo=hq_alvo["titulo"],
                                edicao=hq_alvo["edicao"],
                                editora=hq_alvo["editora"],
                                prateleira=str(novo_valor),
                                genero=hq_alvo.get("genero", "Outro"),
                                escritor=hq_alvo.get("escritor", "Não informado"),
                                ilustrador=hq_alvo.get("ilustrador", "Não informado"),
                                lido=hq_alvo.get("lido", "Não Lido"),
                                avaliacao=int(hq_alvo.get("avaliacao") or 0),
                                capa=hq_alvo.get("capa") or "",
                                resenha=hq_alvo.get("resenha") or "",
                                resumo=hq_alvo.get("resumo") or ""
                            )
                            registro_log["status"] = "sucesso"
                            registro_log["detalhes"] = f"📍 Prateleira de **'{hq_alvo['titulo']}'** alterada para `{novo_valor}`!"
                        elif campo == "resumo":
                            database.definir_resumo(hq_alvo["id"], str(novo_valor))
                            registro_log["status"] = "sucesso"
                            registro_log["detalhes"] = f"📝 Resumo de **'{hq_alvo['titulo']}'** atualizado com sucesso!"
                        elif campo == "resenha":
                            database.definir_resenha(hq_alvo["id"], str(novo_valor))
                            registro_log["status"] = "sucesso"
                            registro_log["detalhes"] = f"✍️ Resenha de **'{hq_alvo['titulo']}'** atualizada com sucesso!"
                        else:
                            registro_log["status"] = "info"
                            registro_log["detalhes"] = f"Campo '{campo}' não suportado para atualização automática."
                    else:
                        registro_log["status"] = "aviso"
                        registro_log["detalhes"] = f"⚠️ Não foi possível localizar a HQ '{titulo}' para atualizar."

                elif acao == "adicionar_desejo":
                    tit = (dados.get("titulo") or "").strip()
                    ed = (dados.get("edicao") or "").strip()
                    edit = (dados.get("editora") or "").strip()
                    preco = float(dados.get("melhor_preco") or 0.0)
                    obs = (dados.get("observacoes") or "").strip()
                    if tit:
                        database.adicionar_item_lista_desejos(
                            titulo=tit,
                            edicao=ed,
                            editora=edit,
                            melhor_preco=preco,
                            observacoes=obs or f"Adicionado via CRUD assistido em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                        )
                        registro_log["status"] = "sucesso"
                        registro_log["detalhes"] = f"⭐ **'{tit}'** adicionado à sua Lista de Desejos!"
                    else:
                        registro_log["status"] = "erro"
                        registro_log["detalhes"] = "Título da HQ não identificado para a Lista de Desejos."

                elif acao == "remover_desejo":
                    tit = (dados.get("titulo") or "").strip()
                    df_w = database.listar_lista_desejos()
                    if not df_w.empty and tit:
                        matches = df_w[df_w["titulo"].str.lower().str.contains(tit.lower(), na=False)]
                        if not matches.empty:
                            del_id = int(matches.iloc[0]["id"])
                            database.deletar_item_lista_desejos(del_id)
                            registro_log["status"] = "sucesso"
                            registro_log["detalhes"] = f"🗑️ **'{matches.iloc[0]['titulo']}'** removido da Lista de Desejos!"
                        else:
                            registro_log["status"] = "aviso"
                            registro_log["detalhes"] = f"Item '{tit}' não encontrado na Lista de Desejos."

                elif acao == "consultar":
                    registro_log["status"] = "info"
                    registro_log["detalhes"] = dados.get("resposta") or explicacao

                else:
                    registro_log["status"] = "info"
                    registro_log["detalhes"] = explicacao or "Comando não reconhecido ou operação não executada."

                st.session_state["historico_crud_assistido"].insert(0, registro_log)
                st.rerun()

    # Exibição do histórico de operações realizadas
    if st.session_state["historico_crud_assistido"]:
        col_h_t, col_h_c = st.columns([4, 1])
        with col_h_t:
            st.markdown("##### 📋 Operações Recentes")
        with col_h_c:
            if st.button("🗑️ Limpar Histórico", key="btn_clear_crud_history", use_container_width=True):
                st.session_state["historico_crud_assistido"] = []
                st.rerun()
        for item_op in st.session_state["historico_crud_assistido"][:6]:
            with st.container(border=True):
                c_st, c_tm = st.columns([4, 1])
                with c_st:
                    st.caption(f"💬 Comando: *\"{item_op['comando']}\"*")
                with c_tm:
                    st.caption(f"🕒 `{item_op['timestamp']}`")

                if item_op["status"] == "sucesso":
                    st.success(item_op["detalhes"] or item_op.get("explicacao", ""), icon="✅")
                elif item_op["status"] == "aviso":
                    st.warning(item_op["detalhes"] or item_op.get("explicacao", ""), icon="⚠️")
                elif item_op["status"] == "erro":
                    st.error(item_op["detalhes"] or item_op.get("explicacao", ""), icon="❌")
                else:
                    st.info(item_op["detalhes"] or item_op.get("explicacao", ""), icon="ℹ️")

st.markdown("---")

# -------------------------------------------------------------
# SEÇÃO 5: RADAR DE PREÇOS EM LOJAS & LISTA DE DESEJOS (SERPAPI)
# -------------------------------------------------------------
with st.expander("🛒 Radar de Preços em Lojas & Lista de Desejos", expanded=False):
    st.markdown(
        "Pesquise preços e disponibilidade de **Livros, Revistas, HQs e Mangás** em tempo real via **SerpApi (Google Shopping)** e adicione à sua **Lista de Desejos** com 1 clique!"
    )

    termo_preco_audio_acionado = None
    tab_preco_texto, tab_preco_audio = st.tabs(["✍️ Digitar Título", "🎙️ Falar Título por Áudio"])

    with tab_preco_texto:
        col_busca_p1, col_busca_p2 = st.columns([3, 1])
        with col_busca_p1:
            termo_preco_input = st.text_input(
                "Título da HQ / Livro para pesquisar preços nas lojas:",
                placeholder="Ex: Watchmen Edição Definitiva, Sandman, Flash Omnibus, Akira...",
                key="input_busca_precos_lojas"
            )
        with col_busca_p2:
            st.write("")
            st.write("")
            btn_pesquisar_preco = st.button("🔍 Consultar Preços", type="primary", use_container_width=True, key="btn_executar_busca_preco")

    with tab_preco_audio:
        st.caption("Fale o título da edição para consultar ofertas em tempo real no Google Shopping:")
        tab_mic_p, tab_up_p = st.tabs(["🎙️ Gravar Microfone", "📁 Enviar Arquivo de Áudio"])
        audio_preco = None
        mime_preco = "audio/wav"

        with tab_mic_p:
            rec_p = st.audio_input("Fale o título da obra (ex: 'Watchmen Edição Definitiva'):", key="rec_mic_preco")
            if rec_p is not None:
                audio_preco = rec_p.getvalue()
                mime_preco = rec_p.type or "audio/wav"

        with tab_up_p:
            up_p = st.file_uploader("Selecione um arquivo de áudio:", type=["wav", "mp3", "m4a", "ogg", "webm", "aac"], key="up_audio_preco")
            if up_p is not None:
                audio_preco = up_p.getvalue()
                mime_preco = up_p.type or "audio/mp3"

        if audio_preco:
            if st.button("🔍 Transcrever & Consultar Preços por Voz", type="primary", key="btn_exec_audio_preco", use_container_width=True):
                if not os.getenv("GEMINI_API_KEY"):
                    st.error("Chave de API do Gemini não configurada!")
                else:
                    with st.spinner("🎙️ Transcrevendo título com Gemini..."):
                        try:
                            termo_preco_audio_acionado = gemini_service.transcrever_audio(
                                audio_bytes=audio_preco,
                                mime_type=mime_preco,
                                tipo_contexto="busca_preco",
                                api_key=os.getenv("GEMINI_API_KEY"),
                                modelo=resolver_modelo("audio")
                            )
                        except Exception as e:
                            st.error(f"Erro ao transcrever áudio: {e}")

    termo_final_preco = termo_preco_audio_acionado or (termo_preco_input.strip() if 'btn_pesquisar_preco' in locals() and btn_pesquisar_preco and termo_preco_input.strip() else None)

    if termo_final_preco:
        with st.spinner(f"🛒 Consultando ofertas de '{termo_final_preco}' via SerpApi (Google Shopping)..."):
            try:
                dados_cotacao = gemini_service.pesquisar_precos_serpapi(
                    termo_busca=termo_final_preco
                )
                st.session_state["radar_precos_resultado"] = dados_cotacao
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao consultar a API do SerpApi: {e}")

    # 2. Exibição do Retorno da API SerpApi
    if st.session_state.get("radar_precos_resultado"):
        cotacao = st.session_state["radar_precos_resultado"]
        termo_pesquisado = cotacao.get("termo") or termo_preco_input.strip()
        itens_encontrados = cotacao.get("itens", [])
        total_encontrados = cotacao.get("total_encontrados", len(itens_encontrados))
        raw_results = cotacao.get("raw_results", {})

        st.markdown(f"### 📋 Resultados no Google Shopping: **{termo_pesquisado}**")
        st.caption(f"Exibindo **{total_encontrados}** oferta(s) de Livros e Revistas filtradas da API.")

        if not itens_encontrados:
            st.warning(f"⚠️ Nenhuma oferta de Livro ou Revista encontrada para **'{termo_pesquisado}'** no Google Shopping.")
        else:
            # Renderiza os itens em grid de 2 a 3 colunas
            cols_por_linha = 2
            for i in range(0, len(itens_encontrados), cols_por_linha):
                chunk = itens_encontrados[i:i + cols_por_linha]
                cols = st.columns(cols_por_linha)
                for idx_col, item in enumerate(chunk):
                    idx_global = i + idx_col
                    with cols[idx_col]:
                        with st.container(border=True):
                            c_img, c_info = st.columns([1, 2])
                            with c_img:
                                thumb_url = item.get("thumbnail") or item.get("serpapi_thumbnail")
                                if thumb_url:
                                    st.image(thumb_url, use_container_width=True)
                                else:
                                    st.caption("🖼️ Sem miniatura")

                            with c_info:
                                tit_item = item.get("title", "Sem título")
                                preco_item = item.get("price", "Preço não informado")
                                preco_num = float(item.get("extracted_price") or 0.0)
                                loja_item = item.get("source", "Loja não informada")
                                raw_link = item.get("product_link") or item.get("link") or ""
                                link_item = gemini_service.sanitizar_url_oferta(raw_link) if raw_link else gemini_service.gerar_link_loja(loja_item, tit_item)
                                condicao = item.get("second_hand_condition", "")
                                frete = item.get("delivery", "")
                                rating = item.get("rating")
                                reviews = item.get("reviews")

                                st.markdown(f"**{tit_item}**")
                                st.markdown(f"🏪 **Loja:** `{loja_item}`")
                                st.markdown(f"🏷️ **Preço:** <span style='font-size: 1.15rem; font-weight: bold; color: #00d26a;'>{preco_item}</span>", unsafe_allow_html=True)

                                detalhes_extras = []
                                if condicao:
                                    detalhes_extras.append(f"📦 {condicao.capitalize()}")
                                if frete:
                                    detalhes_extras.append(f"🚚 {frete}")
                                if rating:
                                    rev_str = f" ({reviews})" if reviews else ""
                                    detalhes_extras.append(f"⭐ {rating}{rev_str}")
                                if detalhes_extras:
                                    st.caption(" • ".join(detalhes_extras))

                                if link_item:
                                    st.link_button("🔗 Ver Oferta na Loja", url=link_item, use_container_width=True)

                                # Botão para adicionar direto à Lista de Desejos
                                if st.button(f"⭐ Salvar na Lista de Desejos", key=f"btn_add_wish_serp_{idx_global}", use_container_width=True):
                                    database.adicionar_item_lista_desejos(
                                        titulo=tit_item,
                                        edicao="",
                                        editora="",
                                        melhor_preco=preco_num,
                                        melhor_loja=loja_item,
                                        link_oferta=link_item,
                                        observacoes=f"Adicionado via SerpApi Google Shopping em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                                    )
                                    st.success(f"🎉 **'{tit_item[:40]}...'** adicionado à sua Lista de Desejos!")
                                    st.rerun()

        # Visualização de todo o conteúdo de retorno bruto da API
        with st.expander("🔍 Ver Conteúdo Bruto de Retorno da API SerpApi (JSON)", expanded=False):
            st.json(raw_results if raw_results else cotacao)

        col_c1, _ = st.columns([1, 3])
        with col_c1:
            if st.button("❌ Fechar Pesquisa", use_container_width=True, key="btn_fechar_radar_cotacao"):
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


