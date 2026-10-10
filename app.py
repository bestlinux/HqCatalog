"""
Aplicativo Streamlit para Catalogação de Coleção de HQs via Câmera e Gemini 2.5 Flash.
"""

import io
import base64
import os
import time
import urllib.parse
from datetime import datetime
from typing import Optional, Any
import requests
import streamlit as st
import pandas as pd
from PIL import Image
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env se existir
load_dotenv()

import database
import gemini_service
import auth
import jev_engine

DEFAULT_NO_COVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "No_Image_Available.jpg")

def processar_imagem_capa(imagem: Any, max_dim: int = 700, quality: int = 85) -> str:
    """Redimensiona e converte uma foto (PIL, UploadedFile ou bytes) em uma string base64 compacta (JPEG)."""
    if imagem is None:
        return ""
    if not isinstance(imagem, Image.Image):
        try:
            imagem = Image.open(imagem)
        except Exception:
            return ""
    img = imagem.convert("RGB")
    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"

def obter_imagem_capa(capa_val: Any) -> Any:
    """Retorna a URL, base64 ou imagem PIL da capa, com fallback para No_Image_Available.jpg."""
    if capa_val is None:
        if os.path.exists(DEFAULT_NO_COVER_PATH):
            return DEFAULT_NO_COVER_PATH
        return None

    # Se já for objeto de imagem carregado (PIL, BytesIO, UploadedFile, bytes), retorna diretamente
    if isinstance(capa_val, (Image.Image, io.BytesIO, bytes)) or hasattr(capa_val, "read"):
        return capa_val

    # Se não for string, tenta converter com segurança
    if not isinstance(capa_val, str):
        try:
            capa_val = str(capa_val)
        except Exception:
            return capa_val

    capa_str = capa_val.strip()
    if capa_str:
        if capa_str.startswith("http") and ("guiadosquadrinhos.com" in capa_str or "ShowImage.aspx" in capa_str):
            # Imagens do Guia dos Quadrinhos são bloqueadas por anti-hotlink do Cloudflare
            # Nunca envie ShowImage.aspx cru diretamente para a tag <img> do navegador
            b64_c = gemini_service.obter_capa_gq_cache(capa_str)
            if b64_c and b64_c.startswith("data:image"):
                return b64_c
            b64_dl = gemini_service.baixar_imagem_url_base64(capa_str)
            if b64_dl and b64_dl.startswith("data:image"):
                return b64_dl
            # Fallback seguro: se não conseguiu carregar via headless, usa No_Image_Available para não quebrar a tela
            if os.path.exists(DEFAULT_NO_COVER_PATH):
                return DEFAULT_NO_COVER_PATH
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
    return None

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

# Inicializa o banco de dados apenas na primeira carga da sessão
if "db_inicializado" not in st.session_state:
    database.init_db()
    st.session_state["db_inicializado"] = True

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

if "ordem_leitura_resultado" not in st.session_state:
    st.session_state["ordem_leitura_resultado"] = None

if "dna_colecao_resultado" not in st.session_state:
    st.session_state["dna_colecao_resultado"] = None

if "storyteller_resultado" not in st.session_state:
    st.session_state["storyteller_resultado"] = None

if "storyteller_hq_id" not in st.session_state:
    st.session_state["storyteller_hq_id"] = None

if "quiz_acervo_resultado" not in st.session_state:
    st.session_state["quiz_acervo_resultado"] = None

if "quiz_respostas_usuario" not in st.session_state:
    st.session_state["quiz_respostas_usuario"] = {}

if "quiz_finalizado" not in st.session_state:
    st.session_state["quiz_finalizado"] = False


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
            st.image(obter_imagem_capa(hq_atual["capa"]), width=130, caption="Capa Atual")
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

            col_val_edit, col_est_edit = st.columns(2)
            with col_val_edit:
                novo_valor = st.number_input("Valor (R$):", min_value=0.0, value=float(hq_atual.get("valor") or 0.0), step=1.0, format="%.2f")
            with col_est_edit:
                opcoes_estados = ["Excelente", "Muito Bom", "Bom", "Regular", "Ruim", "Novo / Lacrado"]
                est_atual_hq = hq_atual.get("estado_conservacao") or "Excelente"
                idx_est_hq = opcoes_estados.index(est_atual_hq) if est_atual_hq in opcoes_estados else 0
                novo_estado = st.selectbox("Estado de Conservação:", options=opcoes_estados, index=idx_est_hq)

            opcoes_status = ["Não Lido", "Lendo", "Lido"]
            status_atual = hq_atual.get("lido") or "Não Lido"
            status_atual_index = opcoes_status.index(status_atual) if status_atual in opcoes_status else 0
            novo_status_leitura = st.selectbox("Status de Leitura:", options=opcoes_status, index=status_atual_index)
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
                        valor=novo_valor,
                        estado_conservacao=novo_estado,
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
            st.image(obter_imagem_capa(hq_capa["capa"]), width=140, caption="Capa Atual Cadastrada")
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
            st.image(obter_imagem_capa(foto_capa_selecionada), width=160, caption="Pré-visualização")
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

@st.dialog("🌐 Buscar Fonte (Reserp.ai + Google)", width="large")
def dialog_buscar_fonte(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    hq_alvo = database.obter_hq_por_id(int(val_id))
    if not hq_alvo:
        st.warning(f"Quadrinho com ID #{val_id} não encontrado.")
        if st.button("❌ Fechar", key="btn_close_busca_fonte_empty", use_container_width=True):
            st.rerun()
        return

    titulo = (hq_alvo.get("titulo") or "").strip()
    edicao = (hq_alvo.get("edicao") or "").strip()
    editora = (hq_alvo.get("editora") or "").strip()
    if editora.lower() in ["desconhecida", "não informada", "nao informada"]:
        editora = ""

    texto_cabecalho = f"{titulo} {edicao} {editora}".strip()
    st.markdown(f"#### 🌐 Buscar Fontes e Dados para: **{texto_cabecalho}**")

    # Mostra dados atuais
    detalhes_atuais = []
    if hq_alvo.get("escritor") and str(hq_alvo["escritor"]).lower() not in ["não informado", "nao informado", ""]:
        detalhes_atuais.append(f"✍️ **Roteiro:** `{hq_alvo['escritor']}`")
    if hq_alvo.get("ilustrador") and str(hq_alvo["ilustrador"]).lower() not in ["não informado", "nao informado", ""]:
        detalhes_atuais.append(f"🎨 **Desenho:** `{hq_alvo['ilustrador']}`")
    if hq_alvo.get("valor") and float(hq_alvo["valor"]) > 0:
        detalhes_atuais.append(f"💰 **Preço:** `R$ {float(hq_alvo['valor']):.2f}`".replace(".", ","))
    if hq_alvo.get("link_edicao"):
        detalhes_atuais.append(f"🔗 [Link Atual]({hq_alvo['link_edicao']})")
    if detalhes_atuais:
        st.caption(" • ".join(detalhes_atuais))

    st.markdown("---")

    # Termo de pesquisa padrão otimizado para SERP
    query_padrao = f"{titulo} {edicao} {editora} \"guia dos quadrinhos\"".strip()
    termo_busca = st.text_input(
        "🔎 Termo de Busca no Google (Reserp.ai):",
        value=query_padrao,
        key=f"input_reserp_query_{val_id}",
        help="Pesquisa no Google via Reserp.ai sem bloqueios de Cloudflare ou IP."
    )

    c_btn1, c_btn2 = st.columns([2, 1])
    with c_btn1:
        btn_pesquisar = st.button("🔎 Pesquisar Fontes na Web (Reserp.ai)", key=f"btn_pesquisar_reserp_{val_id}", type="primary", use_container_width=True)
    with c_btn2:
        btn_limpar = st.button("🔄 Nova Busca", key=f"btn_limpar_reserp_{val_id}", use_container_width=True)

    session_reserp_key = f"reserp_fontes_data_{val_id}"
    termo_cache_key = f"termo_reserp_cache_{val_id}"
    input_key = f"input_reserp_query_{val_id}"
    session_extraidos_key = f"dados_extraidos_fonte_{val_id}"

    if btn_limpar:
        st.session_state.pop(session_reserp_key, None)
        st.session_state.pop(termo_cache_key, None)
        st.session_state.pop(input_key, None)
        st.session_state.pop(session_extraidos_key, None)
        st.session_state.pop(f"fonte_input_capa_{val_id}", None)
        st.session_state.pop(f"fonte_capas_encontradas_{val_id}", None)
        st.session_state.pop(f"fonte_input_roteiro_{val_id}", None)
        st.session_state.pop(f"fonte_input_ilustrador_{val_id}", None)
        st.session_state.pop(f"fonte_input_valor_{val_id}", None)
        st.session_state.pop(f"fonte_input_link_{val_id}", None)
        st.session_state.pop(f"fonte_input_resumo_{val_id}", None)
        st.rerun()

    termo_mudou = st.session_state.get(termo_cache_key) != termo_busca.strip()
    if termo_mudou:
        st.session_state.pop(session_extraidos_key, None)
        st.session_state.pop(f"fonte_input_capa_{val_id}", None)
        st.session_state.pop(f"fonte_capas_encontradas_{val_id}", None)

    sem_fontes = not bool(st.session_state.get(session_reserp_key, {}).get("fontes"))

    if btn_pesquisar or termo_mudou or (session_reserp_key not in st.session_state) or sem_fontes:
        with st.spinner("🔍 Consultando Google via Reserp.ai (sem bloqueios)..."):
            fn_fontes = getattr(gemini_service, "buscar_fontes_hq_reserp", None)
            dados_fontes = {}
            if fn_fontes:
                try:
                    dados_fontes = fn_fontes(
                        titulo=titulo,
                        edicao=edicao,
                        editora=editora,
                        termo_custom=termo_busca.strip()
                    )
                except Exception as ex_f:
                    st.error(f"Erro na consulta Reserp.ai: {ex_f}")
            st.session_state[session_reserp_key] = dados_fontes
            st.session_state[termo_cache_key] = termo_busca.strip()

    res_busca = st.session_state.get(session_reserp_key, {})
    fontes_lista = res_busca.get("fontes", [])[:2]
    link_gq_encontrado = res_busca.get("link_guia_dos_quadrinhos", "")
    texto_reserp = res_busca.get("texto_consolidado", "")

    if fontes_lista:
        st.success(f"✨ Encontrada(s) **{len(fontes_lista)}** fonte(s) na web!")
        
        for idx, fonte in enumerate(fontes_lista):
            f_tit = fonte.get("titulo") or "Página Encontrada"
            f_url = fonte.get("url") or ""
            f_res = fonte.get("resumo") or ""
            with st.container(border=True):
                st.markdown(f"**[{f_tit}]({f_url})**")
                st.caption(f"🔗 `{f_url}`")
                if f_res:
                    st.markdown(f"> *{f_res}*")

        if link_gq_encontrado:
            st.info(f"🎯 **Página canônica no Guia dos Quadrinhos:** [{link_gq_encontrado}]({link_gq_encontrado})")

        st.markdown("---")
        st.markdown("#### 🤖 Extração Inteligente com IA")

        if st.button("🚀 Extrair Dados (Python Direto / ZenRows / ScraperAPI / IA Gemini)", key=f"btn_extrair_reserp_{val_id}", type="primary", use_container_width=True):
            # Limpa explicitamente dados e capas de execuções anteriores para esta busca
            st.session_state.pop(session_extraidos_key, None)
            st.session_state.pop(f"fonte_input_capa_{val_id}", None)
            st.session_state.pop(f"fonte_capas_encontradas_{val_id}", None)
            dados = {}
            modelo_usado = None
            origem_extracao = ""
            
            # 1. TENTATIVA DIRETA DE BAIXAR O HTML COM PYTHON PURO (SEM IA - 100% FIEL E DETERMINÍSTICO)
            url_gq_tentativa = link_gq_encontrado
            if not url_gq_tentativa and fontes_lista:
                for f in fontes_lista:
                    u_cand = f.get("url") or ""
                    if "guiadosquadrinhos.com/edicao/" in u_cand:
                        url_gq_tentativa = u_cand
                        break
            
            if url_gq_tentativa and "/edicao/" in url_gq_tentativa:
                with st.spinner("⚡ 1/4: Tentando extração direta 100% fiel do HTML oficial (Python BeautifulSoup)..."):
                    html_baixado = gemini_service.buscar_html_edicao_guia_dos_quadrinhos(url_gq_tentativa)
                    if html_baixado and ("historia" in html_baixado.lower() or "ampliar_capa" in html_baixado):
                        dados_diretos = gemini_service.extrair_dados_html_guia_dos_quadrinhos(html_baixado, url_gq_tentativa)
                        if dados_diretos and (dados_diretos.get("roteiro") or dados_diretos.get("desenho") or dados_diretos.get("resumo")):
                            dados = dados_diretos
                            modelo_usado = "Python Extractor (Ficha Oficial Guia dos Quadrinhos - Sem IA)"
                            origem_extracao = "html_puro"

            # 2. TENTATIVA COM ZENROWS SE O PYTHON PURO NÃO CONSEGUIU EXTRAIR OU FOI BLOQUEADO
            if not dados or not (dados.get("roteiro") or dados.get("desenho") or dados.get("resumo")):
                if url_gq_tentativa and "/edicao/" in url_gq_tentativa:
                    with st.spinner("🌐 2/4: Tentando extração via ZenRows Scraper API..."):
                        try:
                            html_zen = gemini_service.buscar_html_zenrows(url_gq_tentativa)
                            if html_zen and (gemini_service.eh_html_valido_guia_dos_quadrinhos(html_zen) or "historia" in html_zen.lower()):
                                dados_zen = gemini_service.extrair_dados_html_guia_dos_quadrinhos(html_zen, url_gq_tentativa)
                                if dados_zen and (dados_zen.get("roteiro") or dados_zen.get("desenho") or dados_zen.get("resumo")):
                                    dados = dados_zen
                                    modelo_usado = "ZenRows Scraper (Ficha Oficial Guia dos Quadrinhos)"
                                    origem_extracao = "zenrows"
                        except Exception as ex_zen:
                            print(f"[Aviso ZenRows: {ex_zen}]")

            # 2.2 TENTATIVA COM SCRAPERAPI SE O ZENROWS NÃO CONSEGUIU EXTRAIR OU FALHOU (FAILOVER)
            if not dados or not (dados.get("roteiro") or dados.get("desenho") or dados.get("resumo")):
                if url_gq_tentativa and "/edicao/" in url_gq_tentativa:
                    with st.spinner("🌐 3/4: Tentando extração via ScraperAPI (Failover Anti-Bloqueio)..."):
                        try:
                            html_scraper = gemini_service.buscar_html_scraperapi(url_gq_tentativa)
                            if html_scraper and (gemini_service.eh_html_valido_guia_dos_quadrinhos(html_scraper) or "historia" in html_scraper.lower()):
                                dados_scraper = gemini_service.extrair_dados_html_guia_dos_quadrinhos(html_scraper, url_gq_tentativa)
                                if dados_scraper and (dados_scraper.get("roteiro") or dados_scraper.get("desenho") or dados_scraper.get("resumo")):
                                    dados = dados_scraper
                                    modelo_usado = "ScraperAPI Scraper (Ficha Oficial Guia dos Quadrinhos)"
                                    origem_extracao = "scraperapi"
                        except Exception as ex_scraper:
                            print(f"[Aviso ScraperAPI: {ex_scraper}]")

            # 3. FALLBACK INTELIGENTE PARA IA GEMINI SE NADA MAIS FUNCIONOU
            if not dados or not (dados.get("roteiro") or dados.get("desenho") or dados.get("resumo")):
                with st.spinner("🤖 4/4: Consultando dados via IA Gemini (Fallback Inteligente)..."):
                    prompt_llm = f"""Você é o especialista mestre na enciclopédia GUIA DOS QUADRINHOS e nos quadrinhos publicados no Brasil.
Seu objetivo é extrair e estruturar com máxima precisão a ficha técnica completa para a EDIÇÃO BRASILEIRA:
Título: "{titulo}"
Edição/Volume: "{edicao}"
Editora: "{editora}"

Fontes e textos coletados na web:
---
{texto_reserp[:14000]}
---
Link oficial da edição no Guia dos Quadrinhos: {link_gq_encontrado or 'Não identificado'}

DIRETRIZES DE EXTRAÇÃO E PREENCHIMENTO:
1. "roteiro": Identifique o(s) roteirista(s) principal(is) desta edição específica "{titulo} nº {edicao}" da editora "{editora}". Se houver mais de um, separe por vírgula.
2. "ilustrador": Identifique o(s) desenhista(s)/artista(s) desta edição específica.
3. "valor": Preço oficial de capa em reais (número float, ex: 4.40 se presente no texto/snippet, ou 0.0).
4. "resumo": Monte um resumo rico e fiel contendo a sinopse da edição e a lista de histórias que compõem este volume específico da {editora}.
5. "capa": Extraia ou confirme a URL da imagem da capa oficial da edição (ShowImage.aspx ou link de imagem).
6. "link_edicao": Link canônico oficial da edição no Guia dos Quadrinhos (ex: "{link_gq_encontrado}").

Retorne ESTRITAMENTE um JSON com as chaves:
{{
  "roteiro": "...",
  "ilustrador": "...",
  "valor": 0.0,
  "resumo": "...",
  "capa": "...",
  "link_edicao": "..."
}}
"""
                    cliente = gemini_service.get_gemini_client()
                    modelos = ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash', 'gemini-3.6-flash', 'gemini-3.1-flash-lite']
                    resposta = None
                    ultimo_erro = None
                    config_gen = None
                    if gemini_service.types is not None and hasattr(gemini_service.types, "GenerateContentConfig"):
                        try:
                            config_gen = gemini_service.types.GenerateContentConfig(
                                temperature=0.1,
                                response_mime_type="application/json"
                            )
                        except Exception:
                            config_gen = None

                    for mod in modelos:
                        try:
                            if config_gen is not None:
                                resposta = cliente.models.generate_content(
                                    model=mod,
                                    contents=prompt_llm,
                                    config=config_gen
                                )
                            else:
                                resposta = cliente.models.generate_content(
                                    model=mod,
                                    contents=prompt_llm
                                )
                            if resposta and resposta.text:
                                modelo_usado = mod
                                origem_extracao = "ia_gemini"
                                break
                        except Exception as ai_err:
                            ultimo_erro = ai_err
                            continue

                    if not resposta or not resposta.text:
                        st.error(f"Erro ao processar com a IA: {ultimo_erro}")
                    else:
                        dados = gemini_service.limpar_e_parsear_json_dict(resposta.text)

            if dados:
                if modelo_usado:
                    dados["_modelo_usado"] = modelo_usado
                    st.session_state[f"fonte_modelo_usado_{val_id}"] = modelo_usado
                st.session_state[session_extraidos_key] = dados
                # Popula campos editáveis
                st.session_state[f"fonte_input_roteiro_{val_id}"] = dados.get("roteiro") or ""
                st.session_state[f"fonte_input_ilustrador_{val_id}"] = dados.get("ilustrador") or dados.get("desenho") or ""
                try:
                    st.session_state[f"fonte_input_valor_{val_id}"] = float(dados.get("valor") or dados.get("preco_capa") or 0.0)
                except Exception:
                    st.session_state[f"fonte_input_valor_{val_id}"] = 0.0
                st.session_state[f"fonte_input_resumo_{val_id}"] = dados.get("resumo") or ""
                
                link_final_ed = dados.get("link_edicao") or dados.get("url_edicao") or link_gq_encontrado or ""
                st.session_state[f"fonte_input_link_{val_id}"] = link_final_ed
                
                # Resolução de Capa (id="ampliar_capa" / <meta property="og:image"> / ShowImage.aspx)
                capa_extraida = dados.get("capa_b64") or dados.get("capa") or dados.get("capa_url") or ""
                if link_final_ed and "/edicao/" in link_final_ed:
                    fn_der_capa = getattr(gemini_service, "derivar_url_capa_guia_dos_quadrinhos", None)
                    if fn_der_capa:
                        url_der = fn_der_capa(link_final_ed, editora=editora, edicao=edicao)
                        if url_der and (not capa_extraida or "ShowImage.aspx" not in capa_extraida or not (capa_extraida.startswith("http") or capa_extraida.startswith("data:image"))):
                            capa_extraida = url_der
                
                if capa_extraida and str(capa_extraida).startswith("http") and ("guiadosquadrinhos.com" in capa_extraida or "ShowImage.aspx" in capa_extraida):
                    b64_capa = gemini_service.baixar_imagem_url_base64(str(capa_extraida).strip(), fallback_url=link_final_ed)
                    if b64_capa and b64_capa.startswith("data:image"):
                        capa_extraida = b64_capa

                # Executa a mesma Busca de Capas online para obter as opções em alta definição
                termo_capa_busca = f"{titulo} {edicao} {editora}".strip()
                capas_encontradas = gemini_service.buscar_capas_online(
                    titulo=termo_capa_busca,
                    edicao=edicao,
                    editora=editora,
                    escritor=dados.get("roteiro") or "",
                    limite=12,
                    url_edicao=link_final_ed
                )
                
                if capa_extraida and (capa_extraida.startswith("data:image") or not ("guiadosquadrinhos.com" in capa_extraida or "ShowImage.aspx" in capa_extraida)):
                    if not any(c.get("url") == capa_extraida for c in capas_encontradas):
                        capas_encontradas.insert(0, {
                            "url": capa_extraida,
                            "titulo": f"{titulo} nº {edicao} (Guia dos Quadrinhos Oficial)",
                            "fonte": "Guia dos Quadrinhos",
                            "thumbnail": capa_extraida
                        })
                
                st.session_state[f"fonte_capas_encontradas_{val_id}"] = capas_encontradas
                if capas_encontradas:
                    st.session_state[f"fonte_input_capa_{val_id}"] = capas_encontradas[0]["url"]
                elif capa_extraida and (capa_extraida.startswith("data:image") or not ("guiadosquadrinhos.com" in capa_extraida or "ShowImage.aspx" in capa_extraida)):
                    st.session_state[f"fonte_input_capa_{val_id}"] = str(capa_extraida).strip()
                elif hq_alvo.get("capa"):
                    st.session_state[f"fonte_input_capa_{val_id}"] = hq_alvo.get("capa")
                    
                if origem_extracao == "html_puro":
                    st.success("✅ Dados extraídos com **100% de fidelidade diretamente do HTML oficial** (Python BeautifulSoup - Sem alucinações)! Revise os campos abaixo.")
                elif origem_extracao == "zenrows":
                    st.success("✅ Dados extraídos com **100% de fidelidade via ZenRows Scraper** (HTML Oficial Guia dos Quadrinhos)! Revise os campos abaixo.")
                elif origem_extracao == "scraperapi":
                    st.success("✅ Dados extraídos com **100% de fidelidade via ScraperAPI** (HTML Oficial Guia dos Quadrinhos)! Revise os campos abaixo.")
                else:
                    st.success(f"✅ Dados e opções de capas extraídos com sucesso via **{modelo_usado or 'Gemini'}**! Revise os campos abaixo.")

        # Opção manual de colar link ou texto da página (posicionada antes dos widgets para permitir extração direta)
        with st.expander("📋 Opção Manual: Colar Link ou Texto da Página", expanded=False):
            url_ou_texto = st.text_area("Link direto ou Texto copiado da página:", placeholder="https://www.guiadosquadrinhos.com/edicao/...", key=f"txt_url_manual_fonte_{val_id}")
            if st.button("🚀 Processar Texto / Link Manual", key=f"btn_manual_busca_fonte_{val_id}", width="stretch"):
                if not url_ou_texto.strip():
                    st.warning("Cole o link ou texto primeiro!")
                else:
                    # Limpa explicitamente dados e capas de execuções anteriores
                    st.session_state.pop(session_extraidos_key, None)
                    st.session_state.pop(f"fonte_input_capa_{val_id}", None)
                    st.session_state.pop(f"fonte_capas_encontradas_{val_id}", None)
                    texto_extraido = url_ou_texto.strip()
                    url_manual_gq = ""
                    origem_manual = ""
                    mod_manual_usado = None
                    
                    # Normaliza links do Guia dos Quadrinhos colados sem protocolo ou com www faltando
                    if "guiadosquadrinhos.com" in texto_extraido:
                        if not texto_extraido.startswith("http"):
                            texto_extraido = "https://" + texto_extraido.lstrip("/")
                        if "www.guiadosquadrinhos.com" not in texto_extraido:
                            texto_extraido = texto_extraido.replace("guiadosquadrinhos.com", "www.guiadosquadrinhos.com")

                    if texto_extraido.startswith("http"):
                        url_manual_gq = texto_extraido

                    dados_man = {}

                    # 1. TENTATIVA DIRETA COM PYTHON PURO (SEM IA / SEM ZENROWS)
                    if not texto_extraido.startswith("http"):
                        # Usuário colou texto ou fragmento HTML diretamente
                        with st.spinner("⚡ 1/4: Extraindo dados do texto colado via Python puro..."):
                            if "<div" in texto_extraido or "class=" in texto_extraido or "historia" in texto_extraido.lower() or "personagens:" in texto_extraido.lower() or "roteiro:" in texto_extraido.lower():
                                dados_man = gemini_service.extrair_dados_texto_ou_html_gq(texto_extraido, url_orig=url_manual_gq)
                                if dados_man and (dados_man.get("roteiro") or dados_man.get("desenho") or dados_man.get("resumo")):
                                    origem_manual = "html_puro"
                                    mod_manual_usado = "Python Extractor (Texto Puro da Página)"
                    else:
                        # Usuário colou uma URL: tenta baixar com Python puro
                        with st.spinner("⚡ 1/4: Tentando baixar página com Python puro (BeautifulSoup)..."):
                            try:
                                if "guiadosquadrinhos.com" in texto_extraido:
                                    html_puro = gemini_service.buscar_html_edicao_guia_dos_quadrinhos(texto_extraido)
                                else:
                                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
                                    r = requests.get(texto_extraido, headers=headers, timeout=10)
                                    html_puro = r.text if r.status_code == 200 else ""

                                if html_puro and len(html_puro) > 500:
                                    dados_puro = gemini_service.extrair_dados_texto_ou_html_gq(html_puro, url_orig=url_manual_gq)
                                    if dados_puro and (dados_puro.get("roteiro") or dados_puro.get("desenho") or dados_puro.get("resumo")):
                                        dados_man = dados_puro
                                        origem_manual = "html_puro"
                                        mod_manual_usado = "Python Extractor (Página Oficial - Sem IA)"
                            except Exception as e_puro:
                                print(f"[Aviso Python puro manual: {e_puro}]")

                    # 2. TENTATIVA VIA ZENROWS (SE O PYTHON PURO FALHOU OU NÃO OBTEVE OS DADOS E É UMA URL)
                    if (not dados_man or not (dados_man.get("roteiro") or dados_man.get("desenho") or dados_man.get("resumo"))) and texto_extraido.startswith("http"):
                        with st.spinner("🌐 2/4: Tentando acessar e extrair via ZenRows Scraper API..."):
                            try:
                                html_zen = gemini_service.buscar_html_zenrows(texto_extraido)
                                if html_zen and (gemini_service.eh_html_valido_guia_dos_quadrinhos(html_zen) or len(html_zen) > 500):
                                    dados_zen = gemini_service.extrair_dados_html_guia_dos_quadrinhos(html_zen, url_orig=url_manual_gq)
                                    if not dados_zen or not (dados_zen.get("roteiro") or dados_zen.get("desenho") or dados_zen.get("resumo")):
                                        dados_zen = gemini_service.extrair_dados_texto_ou_html_gq(html_zen, url_orig=url_manual_gq)
                                    if dados_zen and (dados_zen.get("roteiro") or dados_zen.get("desenho") or dados_zen.get("resumo")):
                                        dados_man = dados_zen
                                        origem_manual = "zenrows"
                                        mod_manual_usado = "ZenRows Scraper (HTML Oficial Guia dos Quadrinhos)"
                            except Exception as e_zen:
                                print(f"[Aviso ZenRows manual: {e_zen}]")

                    # 2.2 TENTATIVA VIA SCRAPERAPI (SE O ZENROWS FALHOU OU NÃO OBTEVE OS DADOS E É UMA URL)
                    if (not dados_man or not (dados_man.get("roteiro") or dados_man.get("desenho") or dados_man.get("resumo"))) and texto_extraido.startswith("http"):
                        with st.spinner("🌐 3/4: Tentando acessar e extrair via ScraperAPI (Failover Anti-Bloqueio)..."):
                            try:
                                html_scraper = gemini_service.buscar_html_scraperapi(texto_extraido)
                                if html_scraper and (gemini_service.eh_html_valido_guia_dos_quadrinhos(html_scraper) or len(html_scraper) > 500):
                                    dados_scraper = gemini_service.extrair_dados_html_guia_dos_quadrinhos(html_scraper, url_orig=url_manual_gq)
                                    if not dados_scraper or not (dados_scraper.get("roteiro") or dados_scraper.get("desenho") or dados_scraper.get("resumo")):
                                        dados_scraper = gemini_service.extrair_dados_texto_ou_html_gq(html_scraper, url_orig=url_manual_gq)
                                    if dados_scraper and (dados_scraper.get("roteiro") or dados_scraper.get("desenho") or dados_scraper.get("resumo")):
                                        dados_man = dados_scraper
                                        origem_manual = "scraperapi"
                                        mod_manual_usado = "ScraperAPI Scraper (HTML Oficial Guia dos Quadrinhos)"
                            except Exception as e_scraper:
                                print(f"[Aviso ScraperAPI manual: {e_scraper}]")

                    # 3. CASO NADA MAIS FUNCIONE, USE A IA PARA EXTRAIR (FALLBACK GEMINI)
                    if not dados_man or not dados_man.get("resumo") or not (dados_man.get("roteiro") or dados_man.get("desenho")):
                        with st.spinner("🤖 4/4: Extraindo dados com IA Gemini (Fallback Inteligente)..."):
                            texto_auxiliar = texto_extraido
                            if texto_extraido.startswith("http") and not ("<div" in texto_extraido or "historia" in texto_extraido.lower()):
                                try:
                                    m_slug = re.search(r'/edicao/([^/]+)/', url_manual_gq)
                                    slug_pesq = m_slug.group(1).replace("-n-", " ").replace("-", " ") if m_slug else titulo
                                    res_gq = gemini_service.pesquisar_reserp_google(f"site:guiadosquadrinhos.com \"{slug_pesq}\"")
                                    if not res_gq:
                                        res_gq = gemini_service.pesquisar_reserp_google(f"site:guiadosquadrinhos.com {slug_pesq}")
                                    if res_gq:
                                        texto_auxiliar = "\n\n".join([f"{item.get('title', '')}\n{item.get('snippet', '')}\n{item.get('text', '')}" for item in res_gq[:4]])
                                except Exception:
                                    pass

                            prompt_man = f"""Você é o especialista mestre na enciclopédia Guia dos Quadrinhos (guiadosquadrinhos.com) e nos quadrinhos publicados no Brasil.
O usuário forneceu um link ou conteúdo para catalogar esta edição:
{f'URL Oficial da Edição: {url_manual_gq}' if url_manual_gq else ''}
Título de referência: "{titulo}"
Edição de referência: "{edicao}"
Editora de referência: "{editora}"

Conteúdo/Resultados:
---
{texto_auxiliar[:14000]}
---
REGRAS DE EXTRAÇÃO:
- Identifique a edição correspondente e extraia cada história individual com detalhes.
- Monte o resumo completo com todas as histórias contidas nesta edição (Título, Publicação Original, Roteiro, Arte, Personagens e Sinopse).
- Extraia roteiro (nomes de todos os roteiristas separados por vírgula), ilustrador (todos os desenhistas/arte separados por vírgula), valor (preço de capa em reais, número float), resumo e link_edicao ({url_manual_gq or 'URL oficial'}).
Retorne ESTRITAMENTE um JSON com as chaves: "roteiro", "ilustrador", "valor", "resumo", "link_edicao"."""
                            cliente = gemini_service.get_gemini_client()
                            resp_man = None
                            for mod in ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash', 'gemini-3.6-flash', 'gemini-3.1-flash-lite']:
                                try:
                                    resp_man = cliente.models.generate_content(model=mod, contents=prompt_man)
                                    if resp_man and resp_man.text:
                                        mod_manual_usado = mod
                                        origem_manual = "ia_gemini"
                                        break
                                except Exception:
                                    continue
                            dados_ia = gemini_service.limpar_e_parsear_json_dict(resp_man.text) if resp_man and resp_man.text else {}
                            if dados_ia:
                                if mod_manual_usado:
                                    dados_ia["_modelo_usado"] = mod_manual_usado
                                    st.session_state[f"fonte_modelo_usado_{val_id}"] = mod_manual_usado
                                if not dados_man:
                                    dados_man = dados_ia
                                else:
                                    for k, v in dados_ia.items():
                                        if not dados_man.get(k) and v:
                                            dados_man[k] = v

                        if dados_man:
                            st.session_state[session_extraidos_key] = dados_man
                            st.session_state[f"fonte_input_roteiro_{val_id}"] = dados_man.get("roteiro") or ""
                            st.session_state[f"fonte_input_ilustrador_{val_id}"] = dados_man.get("ilustrador") or dados_man.get("desenho") or ""
                            try:
                                st.session_state[f"fonte_input_valor_{val_id}"] = float(dados_man.get("valor") or dados_man.get("preco_capa") or 0.0)
                            except Exception:
                                st.session_state[f"fonte_input_valor_{val_id}"] = 0.0
                            st.session_state[f"fonte_input_resumo_{val_id}"] = dados_man.get("resumo") or ""
                            st.session_state[f"fonte_input_link_{val_id}"] = dados_man.get("link_edicao") or dados_man.get("url_edicao") or url_manual_gq or ""
                            
                            capa_man = dados_man.get("capa_b64") or dados_man.get("capa_url") or dados_man.get("capa") or ""
                            if capa_man:
                                if str(capa_man).startswith("http") and ("guiadosquadrinhos.com" in capa_man or "ShowImage.aspx" in capa_man):
                                    with st.spinner("🖼️ Baixando capa em alta resolução (resolvendo bloqueio Cloudflare)..."):
                                        b64_capa = gemini_service.baixar_imagem_url_base64(str(capa_man).strip(), fallback_url=url_manual_gq)
                                        if b64_capa and b64_capa.startswith("data:image"):
                                            capa_man = b64_capa
                                        else:
                                            capa_man = ""
                                if capa_man:
                                    st.session_state[f"fonte_input_capa_{val_id}"] = str(capa_man).strip()
                            
                            # Busca capas online para obter as opções em alta definição
                            termo_capa_busca = f"{titulo} {edicao} {editora}".strip()
                            capas_encontradas = gemini_service.buscar_capas_online(
                                titulo=termo_capa_busca,
                                edicao=edicao,
                                editora=editora,
                                escritor=dados_man.get("roteiro") or "",
                                limite=12,
                                url_edicao=url_manual_gq
                            )
                            if capa_man and (capa_man.startswith("data:image") or not ("guiadosquadrinhos.com" in capa_man or "ShowImage.aspx" in capa_man)):
                                if not any(c.get("url") == capa_man for c in capas_encontradas):
                                    capas_encontradas.insert(0, {
                                        "url": capa_man,
                                        "titulo": f"{titulo} nº {edicao} (Guia dos Quadrinhos Oficial)",
                                        "fonte": "Guia dos Quadrinhos",
                                        "thumbnail": capa_man
                                    })
                            st.session_state[f"fonte_capas_encontradas_{val_id}"] = capas_encontradas
                            if capa_man:
                                st.session_state[f"fonte_input_capa_{val_id}"] = str(capa_man).strip()
                            elif capas_encontradas:
                                st.session_state[f"fonte_input_capa_{val_id}"] = capas_encontradas[0]["url"]
                            elif hq_alvo.get("capa"):
                                st.session_state[f"fonte_input_capa_{val_id}"] = hq_alvo.get("capa")

                            if origem_manual == "html_puro":
                                st.success("✅ Conteúdo extraído com **100% de fidelidade diretamente do HTML/Texto oficial** (Python puro)! Revise os campos abaixo.")
                            elif origem_manual == "zenrows":
                                st.success("✅ Conteúdo extraído com sucesso via **ZenRows Scraper** (HTML Oficial Guia dos Quadrinhos)! Revise os campos abaixo.")
                            elif origem_manual == "scraperapi":
                                st.success("✅ Conteúdo extraído com sucesso via **ScraperAPI** (HTML Oficial Guia dos Quadrinhos)! Revise os campos abaixo.")
                            else:
                                st.success(f"✅ Conteúdo processado com sucesso via **{mod_manual_usado or 'Gemini'}**! Revise os campos abaixo.")

        # Se houver dados extraídos (ou dados já existentes), exibe o formulário de validação e edição
        dados_salvar = st.session_state.get(session_extraidos_key)
        if dados_salvar:
            with st.container(border=True):
                st.markdown("### 📝 Validar e Salvar Dados da Edição")
                mod_usado = st.session_state.get(f"fonte_modelo_usado_{val_id}") or (dados_salvar.get("_modelo_usado") if isinstance(dados_salvar, dict) else None)
                if mod_usado:
                    st.info(f"🤖 **Modelo de IA utilizado na extração:** `{mod_usado}`")
                st.caption("Revise ou edite as informações abaixo antes de gravar no banco de dados:")

                if f"fonte_input_capa_{val_id}" not in st.session_state:
                    st.session_state[f"fonte_input_capa_{val_id}"] = hq_alvo.get("capa") or ""
                if f"fonte_input_roteiro_{val_id}" not in st.session_state:
                    st.session_state[f"fonte_input_roteiro_{val_id}"] = hq_alvo.get("escritor") if hq_alvo.get("escritor") != "Não informado" else ""
                if f"fonte_input_ilustrador_{val_id}" not in st.session_state:
                    st.session_state[f"fonte_input_ilustrador_{val_id}"] = hq_alvo.get("ilustrador") if hq_alvo.get("ilustrador") != "Não informado" else ""
                if f"fonte_input_valor_{val_id}" not in st.session_state:
                    st.session_state[f"fonte_input_valor_{val_id}"] = float(hq_alvo.get("valor") or 0.0)
                if f"fonte_input_link_{val_id}" not in st.session_state:
                    st.session_state[f"fonte_input_link_{val_id}"] = hq_alvo.get("link_edicao") or ""
                if f"fonte_input_resumo_{val_id}" not in st.session_state:
                    st.session_state[f"fonte_input_resumo_{val_id}"] = hq_alvo.get("resumo") or ""

                col_form_c1, col_form_c2 = st.columns([1, 1])
                with col_form_c1:
                    st.text_input("✍️ Roteirista(s):", key=f"fonte_input_roteiro_{val_id}")
                    st.text_input("🎨 Ilustrador(es) / Arte:", key=f"fonte_input_ilustrador_{val_id}")
                    st.number_input("💰 Preço de Capa (R$):", min_value=0.0, step=0.50, format="%.2f", key=f"fonte_input_valor_{val_id}")
                with col_form_c2:
                    st.text_input("🔗 Link Oficial da Edição (Guia dos Quadrinhos):", key=f"fonte_input_link_{val_id}")
                    st.text_area("📝 Resumo / Sinopse da Edição:", height=108, key=f"fonte_input_resumo_{val_id}")

                st.markdown("---")
                st.markdown("#### 🖼️ Capa da Edição")
                
                capas_disponiveis = st.session_state.get(f"fonte_capas_encontradas_{val_id}", [])
                capa_selecionada = st.session_state.get(f"fonte_input_capa_{val_id}") or ""
                
                # Exibição da capa selecionada
                if capa_selecionada:
                    col_prev1, col_prev2 = st.columns([1.2, 3])
                    with col_prev1:
                        st.image(obter_imagem_capa(capa_selecionada), width=160, caption="Capa Selecionada")
                    with col_prev2:
                        st.success("✅ **Capa ativa selecionada para este quadrinho.**")
                        st.caption(f"🔗 `{capa_selecionada[:80]}...`" if len(capa_selecionada) > 80 else f"🔗 `{capa_selecionada}`")
                else:
                    st.info("🖼️ Nenhuma capa selecionada ainda.")

                # Galeria de opções de capas encontradas na web
                if capas_disponiveis:
                    st.markdown(f"**Opções de capas encontradas ({len(capas_disponiveis)}):** *Escolha a capa desejada e clique em **Selecionar**.*")
                    for i in range(0, len(capas_disponiveis), 3):
                        cols_c = st.columns(3, gap="small")
                        for j in range(3):
                            idx_c = i + j
                            if idx_c < len(capas_disponiveis):
                                item_c = capas_disponiveis[idx_c]
                                u_c = item_c.get("url") or ""
                                t_c = item_c.get("titulo") or titulo
                                f_c = item_c.get("fonte") or "Web"
                                is_sel = (capa_selecionada == u_c)
                                with cols_c[j]:
                                    with st.container(border=True):
                                        st.image(obter_imagem_capa(u_c), width="stretch")
                                        st.caption(f"**{t_c[:50]}**\n\n*{f_c}*")
                                        if is_sel:
                                            st.button("✅ Selecionada", key=f"btn_capa_sel_{val_id}_{idx_c}", disabled=True, width="stretch")
                                        else:
                                            if st.button("👉 Selecionar", key=f"btn_capa_sel_{val_id}_{idx_c}", width="stretch", type="secondary"):
                                                st.session_state[f"fonte_input_capa_{val_id}"] = u_c

                with st.expander("🔗 Informar URL manual da capa (opcional)", expanded=False):
                    url_manual = st.text_input("URL direta da imagem:", key=f"input_manual_capa_url_{val_id}", placeholder="https://.../capa.jpg")
                    if url_manual:
                        if st.button("Aplicar URL", key=f"btn_aplicar_manual_capa_{val_id}"):
                            st.session_state[f"fonte_input_capa_{val_id}"] = url_manual.strip()

                st.markdown("---")
                col_sv1, col_sv2 = st.columns([2, 1])
                with col_sv1:
                    if st.button("💾 Confirmar e Salvar no Banco de Dados", key=f"btn_confirmar_salvar_fonte_{val_id}", type="primary", use_container_width=True):
                        # Pega valores atuais dos inputs
                        rot_final = (st.session_state.get(f"fonte_input_roteiro_{val_id}") or "").strip()
                        ilu_final = (st.session_state.get(f"fonte_input_ilustrador_{val_id}") or "").strip()
                        val_final = float(st.session_state.get(f"fonte_input_valor_{val_id}") or 0.0)
                        link_final = (st.session_state.get(f"fonte_input_link_{val_id}") or "").strip()
                        res_final = (st.session_state.get(f"fonte_input_resumo_{val_id}") or "").strip()
                        capa_final = (st.session_state.get(f"fonte_input_capa_{val_id}") or "").strip()

                        campos_update = []
                        valores_update = []
                        
                        if rot_final:
                            campos_update.append("escritor = ?")
                            valores_update.append(rot_final)
                        if ilu_final:
                            campos_update.append("ilustrador = ?")
                            valores_update.append(ilu_final)
                        if res_final:
                            campos_update.append("resumo = ?")
                            valores_update.append(res_final)
                        if val_final > 0:
                            campos_update.append("valor = ?")
                            valores_update.append(val_final)
                        if capa_final and (capa_final.startswith("http") or capa_final.startswith("data:image")):
                            capa_salvar = capa_final
                            if capa_final.startswith("http"):
                                try:
                                    b64_dl = gemini_service.baixar_imagem_url_base64(capa_final)
                                    if b64_dl:
                                        capa_salvar = b64_dl
                                except Exception:
                                    pass
                            campos_update.append("capa = ?")
                            valores_update.append(capa_salvar)
                        if link_final and link_final.startswith("http"):
                            campos_update.append("link_edicao = ?")
                            valores_update.append(link_final)

                        if campos_update:
                            valores_update.append(val_id)
                            sql_update = f"UPDATE hqs SET {', '.join(campos_update)} WHERE id = ?"
                            try:
                                if database.is_using_turso():
                                    database.executar_turso_query(sql_update, valores_update)
                                else:
                                    conn = database.get_sqlite_connection()
                                    try:
                                        c = conn.cursor()
                                        c.execute(sql_update, tuple(valores_update))
                                        conn.commit()
                                    finally:
                                        conn.close()

                                # Limpa estados temporários
                                st.session_state.pop(session_extraidos_key, None)
                                st.session_state.pop(session_reserp_key, None)
                                st.session_state.pop(termo_cache_key, None)
                                st.session_state.pop(f"fonte_capas_encontradas_{val_id}", None)
                                st.session_state.pop(f"fonte_input_capa_{val_id}", None)
                                st.session_state.pop(f"fonte_input_roteiro_{val_id}", None)
                                st.session_state.pop(f"fonte_input_ilustrador_{val_id}", None)
                                st.session_state.pop(f"fonte_input_valor_{val_id}", None)
                                st.session_state.pop(f"fonte_input_link_{val_id}", None)
                                st.session_state.pop(f"fonte_input_resumo_{val_id}", None)
                                st.session_state.pop(f"fonte_modelo_usado_{val_id}", None)
                                st.success("🎉 Edição atualizada com sucesso no banco de dados!")
                                time.sleep(1.5)
                                st.rerun()
                            except Exception as ex_db:
                                st.error(f"Erro ao salvar no banco de dados: {ex_db}")
                        else:
                            st.warning("Nenhum dado informado para atualizar.")

                with col_sv2:
                    if st.button("❌ Cancelar", key=f"btn_canc_form_fonte_{val_id}", use_container_width=True):
                        st.session_state.pop(session_extraidos_key, None)
                        st.session_state.pop(f"fonte_capas_encontradas_{val_id}", None)
                        st.session_state.pop(f"fonte_input_capa_{val_id}", None)
                        st.session_state.pop(f"fonte_modelo_usado_{val_id}", None)
                        st.rerun()

    else:
        st.warning("Nenhuma fonte encontrada automaticamente via Reserp.ai. Você pode ajustar o termo de busca acima ou colar o conteúdo manualmente abaixo.")



@st.dialog("🔍 Buscar Dados (Guia dos Quadrinhos)", width="large")
def dialog_buscar_dados(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    id_para_busca = st.number_input("Informe o ID da HQ:", min_value=1, step=1, value=val_id, key=f"dlg_input_buscar_dados_id_{id_padrao or 'padrao'}")
    hq_alvo = database.obter_hq_por_id(int(id_para_busca))
    if not hq_alvo:
        st.warning(f"Quadrinho com ID #{id_para_busca} não encontrado.")
        if st.button("❌ Fechar", key="btn_close_busca_dados_empty", use_container_width=True):
            st.rerun()
        return

    st.markdown(f"#### 📖 {hq_alvo['titulo']}")
    detalhes_str = []
    if hq_alvo.get("edicao"):
        detalhes_str.append(f"**Edição:** {hq_alvo['edicao']}")
    if hq_alvo.get("editora"):
        detalhes_str.append(f"**Editora:** {hq_alvo['editora']}")
    if hq_alvo.get("escritor") and str(hq_alvo["escritor"]).lower() not in ["não informado", "nao informado", ""]:
        detalhes_str.append(f"**Roteiro Atual:** `{hq_alvo['escritor']}`")
    if hq_alvo.get("ilustrador") and str(hq_alvo["ilustrador"]).lower() not in ["não informado", "nao informado", ""]:
        detalhes_str.append(f"**Desenho Atual:** `{hq_alvo['ilustrador']}`")
    if hq_alvo.get("valor") and float(hq_alvo["valor"]) > 0:
        detalhes_str.append(f"**Preço Atual:** `R$ {float(hq_alvo['valor']):.2f}`".replace(".", ","))
    if detalhes_str:
        st.caption(" • ".join(detalhes_str))

    # Campos de pesquisa refinada
    c_tit, c_ed, c_edi = st.columns([2.5, 1.2, 1.5])
    with c_tit:
        termo_tit = st.text_input("Título:", value=hq_alvo["titulo"], key=f"dlg_tit_gq_{hq_alvo['id']}")
    with c_ed:
        termo_ed = st.text_input("Edição / Vol:", value=hq_alvo.get("edicao") or "", key=f"dlg_ed_gq_{hq_alvo['id']}")
    with c_edi:
        termo_edi = st.text_input("Editora:", value=hq_alvo.get("editora") or "", key=f"dlg_edi_gq_{hq_alvo['id']}")

    termo_url = st.text_input(
        "🔗 Link Direto da Edição no Guia dos Quadrinhos (opcional):",
        value=hq_alvo.get("link_edicao") or "",
        key=f"dlg_url_gq_{hq_alvo['id']}",
        placeholder="Ex: https://www.guiadosquadrinhos.com/edicao/universo-dc-3-serie-n-0/un011300/104735",
        help="Cole o link direto da página da edição no Guia dos Quadrinhos para carregar os dados."
    )

    with st.expander("📋 Ou colar texto/ficha da página do Guia dos Quadrinhos (Extração 100% Exata)", expanded=False):
        st.caption("Se estiver com a página aberta no navegador, selecione e copie o texto ou a tabela de Histórias/Ficha Técnica e cole abaixo:")
        txt_copiado_gq = st.text_area("Texto copiado da página:", height=90, key=f"dlg_txt_paste_{hq_alvo['id']}", placeholder="Cole o texto da página ou as histórias...")
        if st.button("⚡ Extrair do Texto Colado", key=f"btn_ext_txt_{hq_alvo['id']}", use_container_width=True):
            if txt_copiado_gq.strip():
                fn_txt_ext = getattr(gemini_service, "extrair_dados_texto_ou_html_gq", None)
                if fn_txt_ext:
                    d_txt = fn_txt_ext(txt_copiado_gq, termo_url.strip())
                    if d_txt:
                        s_key = f"dados_gq_encontrados_{hq_alvo['id']}"
                        st.session_state[s_key] = d_txt
                        st.session_state[f"gq_input_roteiro_{hq_alvo['id']}"] = d_txt.get("roteiro") or ""
                        st.session_state[f"gq_input_desenho_{hq_alvo['id']}"] = d_txt.get("desenho") or ""
                        st.session_state[f"gq_input_preco_{hq_alvo['id']}"] = float(d_txt.get("preco_capa") or 0.0)
                        st.session_state[f"gq_input_resumo_{hq_alvo['id']}"] = d_txt.get("resumo") or ""
                        if d_txt.get("url_edicao"):
                            st.session_state[f"gq_input_link_{hq_alvo['id']}"] = d_txt.get("url_edicao")
                        if d_txt.get("capa_url"):
                            st.session_state[f"capa_gq_selecionada_{hq_alvo['id']}"] = d_txt.get("capa_url")
                        # Evita que a busca automática sobreponha os dados extraídos
                        st.session_state[f"termo_gq_cache_{hq_alvo['id']}"] = f"{termo_tit}|{termo_ed}|{termo_edi}|{termo_url}"
                        st.success("✅ Informações da ficha técnica extraídas com sucesso!")
                        try:
                            st.rerun(scope="fragment")
                        except Exception:
                            pass

    with st.expander("🖼️ Definir Capa (Link Web ou Enviar Imagem)", expanded=False):
        st.caption("Insira o link de uma imagem da internet ou envie o arquivo da capa:")
        col_img_gq1, col_img_gq2 = st.columns([3, 1])
        with col_img_gq1:
            url_capa_direta_gq = st.text_input(
                "Link direto da imagem:",
                placeholder="Ex: https://.../capa.jpg (Links ShowImage.aspx do GQ são bloqueados por hotlink)",
                key=f"dlg_input_img_gq_direta_{hq_alvo['id']}",
                label_visibility="collapsed"
            )
        with col_img_gq2:
            if st.button("🖼️ Usar Link", key=f"btn_set_capa_gq_direta_{hq_alvo['id']}", use_container_width=True):
                if url_capa_direta_gq.strip():
                    u_clean = url_capa_direta_gq.strip()
                    b64 = gemini_service.baixar_imagem_url_base64(u_clean)
                    if b64 and b64.startswith("data:image"):
                        st.session_state[f"capa_gq_selecionada_{hq_alvo['id']}"] = b64
                        st.session_state[f"termo_gq_cache_{hq_alvo['id']}"] = f"{termo_tit}|{termo_ed}|{termo_edi}|{termo_url}"
                        st.success("✅ Imagem da web baixada e aplicada com sucesso!")
                    else:
                        if "guiadosquadrinhos.com" in u_clean or "ShowImage.aspx" in u_clean:
                            st.warning("⚠️ O servidor do Guia dos Quadrinhos bloqueia acesso externo direto (Cloudflare/Hotlink). Salve a imagem no seu PC e use o campo de envio de arquivo abaixo!")
                        else:
                            st.warning("⚠️ Não foi possível baixar a imagem deste link. Tente enviar o arquivo diretamente.")
                    try:
                        st.rerun(scope="fragment")
                    except Exception:
                        pass

        arq_capa_modal = st.file_uploader(
            "📁 Enviar imagem ou colar da área de transferência (Ctrl + V):",
            type=["jpg", "jpeg", "png", "webp"],
            key=f"dlg_upload_capa_{hq_alvo['id']}",
            help="Dica: Após clicar em 'Copiar imagem' no navegador, clique aqui e pressione Ctrl + V para colar a imagem diretamente sem salvar no disco!"
        )
        if arq_capa_modal is not None:
            try:
                img_pil = Image.open(arq_capa_modal)
                b64_up = processar_imagem_capa(img_pil)
                if b64_up:
                    st.session_state[f"capa_gq_selecionada_{hq_alvo['id']}"] = b64_up
                    st.session_state[f"termo_gq_cache_{hq_alvo['id']}"] = f"{termo_tit}|{termo_ed}|{termo_edi}|{termo_url}"
                    st.success("✅ Imagem colada / carregada com sucesso!")
            except Exception as ex_up:
                st.error(f"Erro ao processar imagem: {ex_up}")

    btn_pesquisar_gq = st.button("🔎 Buscar no Guia dos Quadrinhos", key=f"dlg_btn_pesquisar_gq_{hq_alvo['id']}", use_container_width=True, type="primary")

    session_res_key = f"dados_gq_encontrados_{hq_alvo['id']}"
    termo_cache_key = f"termo_gq_cache_{hq_alvo['id']}"
    chave_termo = f"{termo_tit}|{termo_ed}|{termo_edi}|{termo_url}"
    termo_mudou = st.session_state.get(termo_cache_key) != chave_termo

    if btn_pesquisar_gq or termo_mudou or session_res_key not in st.session_state:
        with st.spinner("🔍 Carregando dados no Guia dos Quadrinhos (Roteiro, Desenho, Preço de Capa, Capa e Histórias)..."):
            fn_gq = getattr(gemini_service, "buscar_dados_guia_dos_quadrinhos", None)
            dados_obtidos = {}
            if fn_gq:
                try:
                    sel_mod = st.session_state.get("seletor_modelo_gemini")
                    mod_gq = sel_mod if sel_mod and sel_mod != "Automático (Otimizado)" else "gemini-3.7-flash"
                    dados_obtidos = fn_gq(
                        titulo=termo_tit,
                        edicao=termo_ed,
                        editora=termo_edi,
                        api_key=st.session_state.get("gemini_api_key") or os.getenv("GEMINI_API_KEY"),
                        modelo=mod_gq,
                        url_edicao=termo_url.strip(),
                        usar_ia=True
                    )
                except Exception as ex_gq:
                    st.error(f"Erro ao buscar no Guia dos Quadrinhos: {ex_gq}")
            st.session_state[session_res_key] = dados_obtidos
            st.session_state[termo_cache_key] = chave_termo
            # Sincroniza e reseta os estados dos inputs do modal para refletir os dados obtidos
            capa_inicial = (
                dados_obtidos.get("capa_b64")
                or dados_obtidos.get("capa_url")
                or (dados_obtidos.get("capas_alternativas", [{}])[0].get("url") if dados_obtidos.get("capas_alternativas") else "")
                or ""
            )
            st.session_state[f"capa_gq_selecionada_{hq_alvo['id']}"] = capa_inicial
            st.session_state[f"gq_input_roteiro_{hq_alvo['id']}"] = dados_obtidos.get("roteiro") or ""
            st.session_state[f"gq_input_desenho_{hq_alvo['id']}"] = dados_obtidos.get("desenho") or ""
            st.session_state[f"gq_input_preco_{hq_alvo['id']}"] = float(dados_obtidos.get("preco_capa") or 0.0)
            st.session_state[f"gq_input_resumo_{hq_alvo['id']}"] = dados_obtidos.get("resumo") or ""
            if dados_obtidos.get("url_edicao"):
                st.session_state[f"gq_input_link_{hq_alvo['id']}"] = dados_obtidos.get("url_edicao") or ""

    dados = st.session_state.get(session_res_key, {})

    if not dados:
        st.info("ℹ️ Clique no botão **'Buscar no Guia dos Quadrinhos'** acima para iniciar a pesquisa.")
        if st.button("❌ Fechar", key=f"dlg_btn_close_busca_empty_{hq_alvo['id']}", use_container_width=True):
            st.rerun()
        return

    st.markdown("---")
    st.markdown(f"##### 🎯 Conteúdo Encontrado no Guia dos Quadrinhos (`{dados.get('metodo', 'Guia dos Quadrinhos')}`)")

    col_capa_gq, col_dados_gq = st.columns([1.2, 2.8], gap="medium")

    # Coluna 1: Capa encontrada e alternativas
    with col_capa_gq:
        capa_atual_sess = (
            st.session_state.get(f"capa_gq_selecionada_{hq_alvo['id']}")
            or dados.get("capa_b64")
            or dados.get("capa_url")
            or (dados.get("capas_alternativas", [{}])[0].get("url") if dados.get("capas_alternativas") else "")
            or ""
        )
        placeholder_capa = st.empty()
        if capa_atual_sess:
            placeholder_capa.image(obter_imagem_capa(capa_atual_sess), caption="Capa Selecionada", width="stretch")
        else:
            img_padrao = obter_imagem_capa(hq_alvo.get("capa"))
            placeholder_capa.image(img_padrao, caption="Sem capa encontrada", width="stretch")

        capas_alt = dados.get("capas_alternativas", [])
        if len(capas_alt) >= 1:
            with st.expander(f"🖼️ Escolher entre outras opções de capa ({len(capas_alt)} disponíveis)", expanded=False):
                for i_alt in range(0, len(capas_alt), 2):
                    cols_alt = st.columns(2, gap="small")
                    for j_alt in range(2):
                        idx_c = i_alt + j_alt
                        if idx_c < len(capas_alt):
                            alt = capas_alt[idx_c]
                            u_img = alt.get("url") or alt.get("thumbnail") or ""
                            if u_img:
                                with cols_alt[j_alt]:
                                    with st.container(border=True):
                                        st.image(obter_imagem_capa(u_img), width="stretch")
                                        tit_c = alt.get("titulo") or f"Opção #{idx_c+1}"
                                        fonte_c = alt.get("fonte") or "Web"
                                        st.caption(f"**{tit_c}**\n\n*{fonte_c}*")
                                        if st.button(f"✅ Usar Capa #{idx_c+1}", key=f"btn_alt_capa_{hq_alvo['id']}_{idx_c}", width="stretch", type="primary" if idx_c == 0 else "secondary"):
                                            with st.spinner(f"Carregando capa #{idx_c+1}..."):
                                                b64_alt = gemini_service.baixar_imagem_url_base64(u_img)
                                                capa_escolhida = b64_alt if (b64_alt and b64_alt.startswith("data:image")) else u_img
                                                st.session_state[f"capa_gq_selecionada_{hq_alvo['id']}"] = capa_escolhida
                                                placeholder_capa.image(obter_imagem_capa(capa_escolhida), caption=f"Capa #{idx_c+1} Selecionada", width="stretch")
                                                st.success(f"✅ Capa #{idx_c+1} selecionada! Clique em 'Armazenar tudo' abaixo para salvar.")
                                                try:
                                                    st.rerun(scope="fragment")
                                                except Exception:
                                                    pass

        with st.expander("📁 Enviar / Colar Capa (Ctrl+V)", expanded=False):
            arq_col = st.file_uploader(
                "Selecione ou cole com Ctrl+V:",
                type=["jpg", "jpeg", "png", "webp"],
                key=f"dlg_upload_col_{hq_alvo['id']}",
                help="Clique aqui e pressione Ctrl + V para colar a imagem copiada diretamente."
            )
            if arq_col is not None:
                try:
                    img_col = Image.open(arq_col)
                    b64_c = processar_imagem_capa(img_col)
                    if b64_c:
                        st.session_state[f"capa_gq_selecionada_{hq_alvo['id']}"] = b64_c
                        st.session_state[f"termo_gq_cache_{hq_alvo['id']}"] = f"{termo_tit}|{termo_ed}|{termo_edi}|{termo_url}"
                        st.success("✅ Capa colada / carregada!")
                except Exception as ex_col:
                    st.error(f"Erro: {ex_col}")

    # Coluna 2: Roteiro, Desenho, Preço de Capa, Resumo e Link
    with col_dados_gq:
        k_rot = f"gq_input_roteiro_{hq_alvo['id']}"
        if k_rot not in st.session_state:
            st.session_state[k_rot] = dados.get("roteiro") or ""
        roteiro_edit = st.text_input("✍️ Roteiro:", key=k_rot, help="Roteirista(s) oficial(is) creditados na edição")

        k_des = f"gq_input_desenho_{hq_alvo['id']}"
        if k_des not in st.session_state:
            st.session_state[k_des] = dados.get("desenho") or ""
        desenho_edit = st.text_input("🎨 Desenho / Ilustrador:", key=k_des, help="Desenhista(s) / Arte oficial creditados na edição")

        k_prc = f"gq_input_preco_{hq_alvo['id']}"
        if k_prc not in st.session_state:
            st.session_state[k_prc] = float(dados.get("preco_capa") or 0.0)
        preco_edit = st.number_input("🏷️ Preço de capa (R$):", min_value=0.0, step=0.50, format="%.2f", key=k_prc, help="Valor oficial impresso na capa da edição")

        k_res = f"gq_input_resumo_{hq_alvo['id']}"
        if k_res not in st.session_state:
            st.session_state[k_res] = dados.get("resumo") or ""
        resumo_edit = st.text_area("📝 Resumo / Sinopse:", height=120, key=k_res, help="Sinopse e visão geral da edição")

        url_link_gq = hq_alvo.get("link_edicao") or dados.get("url_edicao") or ""
        ids_alucinados = ["/14102", "/14107", "/li00401/", "/13926", "/ptd0031/", "busca-avancada"]
        if not url_link_gq or any(inv in url_link_gq for inv in ids_alucinados):
            fn_res_url = getattr(gemini_service, "resolver_url_guia_dos_quadrinhos", None)
            if fn_res_url:
                url_link_gq = fn_res_url(
                    titulo=hq_alvo["titulo"],
                    edicao=hq_alvo.get("edicao") or "",
                    editora=hq_alvo.get("editora") or "",
                    url_candidata=dados.get("url_edicao") or ""
                )
            else:
                editora_termo_fallback = hq_alvo.get('editora') if hq_alvo.get('editora') and str(hq_alvo['editora']).lower() not in ['desconhecida', 'não informada', 'nao informada', ''] else ""
                termo_fallback = f'site:guiadosquadrinhos.com "{hq_alvo["titulo"]}" {hq_alvo.get("edicao") or ""} {editora_termo_fallback}'.strip()
                url_link_gq = f"https://www.google.com/search?q={urllib.parse.quote(termo_fallback)}"

        k_lnk = f"gq_input_link_{hq_alvo['id']}"
        if k_lnk not in st.session_state:
            st.session_state[k_lnk] = url_link_gq
        link_edicao_edit = st.text_input(
            "🔗 Link Oficial no Guia dos Quadrinhos:",
            key=k_lnk,
            help="URL oficial da página desta edição no Guia dos Quadrinhos"
        )

        # Query de alta precisão no Google: site:guiadosquadrinhos.com "{titulo}" {edicao} {editora}
        editora_termo_g = hq_alvo.get('editora') if hq_alvo.get('editora') and str(hq_alvo['editora']).lower() not in ['desconhecida', 'não informada', 'nao informada', ''] else ""
        termo_g = f"site:guiadosquadrinhos.com \"{hq_alvo['titulo']}\" {hq_alvo.get('edicao') or ''} {editora_termo_g}".strip()
        url_google_gq = f"https://www.google.com/search?q={urllib.parse.quote(termo_g)}"

        col_lnk1, col_lnk2 = st.columns(2)
        with col_lnk1:
            if link_edicao_edit and link_edicao_edit.startswith("http") and "google.com" not in link_edicao_edit:
                st.markdown(f"🔗 [Abrir no Guia dos Quadrinhos ➔]({link_edicao_edit})")
            else:
                st.caption("ℹ️ Nenhum link direto salvo.")
        with col_lnk2:
            st.markdown(f"🔍 [Pesquisar esta Edição no Google ➔]({url_google_gq})")

    st.markdown("---")

    # BOTÃO PRINCIPAL: Armazenar tudo
    col_save1, col_save2 = st.columns([3, 1], gap="medium")
    with col_save1:
        if st.button("💾 Armazenar tudo", key=f"btn_armazenar_tudo_{hq_alvo['id']}", use_container_width=True, type="primary"):
            sucesso_total = True
            erros = []

            # 1. Armazena Roteiro e Desenho
            rot_salvar = roteiro_edit.strip() or "Não informado"
            des_salvar = desenho_edit.strip() or "Não informado"
            if not database.definir_escritor_ilustrador(int(hq_alvo["id"]), rot_salvar, des_salvar):
                sucesso_total = False
                erros.append("Roteiro/Desenho")

            # 2. Armazena Preço de Capa
            if preco_edit > 0:
                if not database.definir_valor(int(hq_alvo["id"]), float(preco_edit)):
                    sucesso_total = False
                    erros.append("Preço")

            # 3. Armazena Resumo
            if resumo_edit and resumo_edit.strip():
                if not database.definir_resumo(int(hq_alvo["id"]), resumo_edit.strip()):
                    sucesso_total = False
                    erros.append("Resumo")

            # 4. Armazena Capa
            capa_final = (
                st.session_state.get(f"capa_gq_selecionada_{hq_alvo['id']}")
                or dados.get("capa_b64")
                or dados.get("capa_url")
                or (dados.get("capas_alternativas", [{}])[0].get("url") if dados.get("capas_alternativas") else "")
                or ""
            )
            if capa_final and (capa_final.startswith("data:image") or capa_final.startswith("http")):
                if not database.definir_capa(int(hq_alvo["id"]), capa_final):
                    sucesso_total = False
                    erros.append("Capa")

            # 5. Armazena Link Oficial da Edição no Guia dos Quadrinhos
            if link_edicao_edit and link_edicao_edit.strip() and "busca-avancada" not in link_edicao_edit:
                fn_link = getattr(database, "definir_link_edicao", None)
                if fn_link:
                    fn_link(int(hq_alvo["id"]), link_edicao_edit.strip())

            if sucesso_total:
                st.success("🎉 Todos os dados foram armazenados com sucesso no catálogo!")
                # Limpa cache do modal
                for k in [
                    session_res_key,
                    termo_cache_key,
                    f"capa_gq_selecionada_{hq_alvo['id']}",
                    f"gq_input_roteiro_{hq_alvo['id']}",
                    f"gq_input_desenho_{hq_alvo['id']}",
                    f"gq_input_preco_{hq_alvo['id']}",
                    f"gq_input_resumo_{hq_alvo['id']}",
                    f"gq_input_link_{hq_alvo['id']}"
                ]:
                    if k in st.session_state:
                        del st.session_state[k]
                time.sleep(1.0)
                st.rerun()
            else:
                st.warning(f"Alguns campos não puderam ser salvos: {', '.join(erros)}")

    with col_save2:
        if st.button("❌ Fechar", key=f"dlg_btn_close_busca_{hq_alvo['id']}", use_container_width=True):
            for k in [
                session_res_key,
                termo_cache_key,
                f"capa_gq_selecionada_{hq_alvo['id']}",
                f"gq_input_roteiro_{hq_alvo['id']}",
                f"gq_input_desenho_{hq_alvo['id']}",
                f"gq_input_preco_{hq_alvo['id']}",
                f"gq_input_resumo_{hq_alvo['id']}",
                f"gq_input_link_{hq_alvo['id']}"
            ]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()


@st.dialog("🖼️ Buscar Capa da HQ Online", width="large")
def dialog_buscar_capa(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    id_para_capa = st.number_input("Informe o ID da HQ:", min_value=1, step=1, value=val_id, key=f"dlg_input_buscar_capa_id_{id_padrao or 'padrao'}")
    hq_alvo = database.obter_hq_por_id(int(id_para_capa))
    if not hq_alvo:
        st.warning(f"Quadrinho com ID #{id_para_capa} não encontrado.")
        if st.button("❌ Fechar", key="btn_close_busca_capa_empty", use_container_width=True):
            st.rerun()
        return

    st.markdown(f"#### 📖 {hq_alvo['titulo']}")
    detalhes_str = []
    if hq_alvo.get("edicao"):
        detalhes_str.append(f"**Edição:** {hq_alvo['edicao']}")
    if hq_alvo.get("editora"):
        detalhes_str.append(f"**Editora:** {hq_alvo['editora']}")
    if hq_alvo.get("escritor") and str(hq_alvo["escritor"]).lower() not in ["não informado", "nao informado", ""]:
        detalhes_str.append(f"**Roteiro:** {hq_alvo['escritor']}")
    if detalhes_str:
        st.caption(" • ".join(detalhes_str))

    termo_default = f"{hq_alvo['titulo']} {hq_alvo.get('edicao') or ''} {hq_alvo.get('editora') or ''}".strip()
    
    col_t1, col_t2 = st.columns([3.5, 1.2])
    with col_t1:
        termo_busca = st.text_input("Termo de busca da capa na web:", value=termo_default, key=f"dlg_termo_capa_{hq_alvo['id']}")
    with col_t2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        btn_pesquisar = st.button("🔎 Pesquisar", key=f"dlg_btn_pesquisar_capa_{hq_alvo['id']}", use_container_width=True, type="primary")

    session_res_key = f"capas_encontradas_{hq_alvo['id']}"
    termo_cache_key = f"termo_capa_anterior_{hq_alvo['id']}"
    
    termo_mudou = st.session_state.get(termo_cache_key) != termo_busca.strip()
    
    # Busca automaticamente ao abrir ou quando o termo mudar ou ao clicar no botão
    if btn_pesquisar or termo_mudou or session_res_key not in st.session_state:
        with st.spinner("🔍 Buscando capas no Google e Guia dos Quadrinhos via Reserp.ai..."):
            resultados = gemini_service.buscar_capas_online(
                titulo=termo_busca,
                edicao=hq_alvo.get("edicao") or "",
                editora=hq_alvo.get("editora") or "",
                escritor=hq_alvo.get("escritor") or "",
                limite=15
            )
            st.session_state[session_res_key] = resultados
            st.session_state[termo_cache_key] = termo_busca.strip()

    capas = st.session_state.get(session_res_key, [])

    if capas:
        st.markdown(f"**Capas encontradas ({len(capas)}):** *Escolha a capa desejada e clique em **Cadastrar** para atualizar esta HQ.*")
        
        # Grid 2 colunas para exibição visual ampla
        for i in range(0, len(capas), 2):
            cols = st.columns(2, gap="medium")
            for j in range(2):
                idx = i + j
                if idx < len(capas):
                    item = capas[idx]
                    with cols[j]:
                        with st.container(border=True):
                            st.image(obter_imagem_capa(item["url"]), width="stretch")
                            st.caption(f"**{item.get('titulo', hq_alvo['titulo'])}**\n\n*Fonte: {item.get('fonte', 'Web')}*")
                            if st.button("✅ Cadastrar esta Capa", key=f"btn_salvar_capa_item_{hq_alvo['id']}_{idx}", width="stretch", type="primary"):
                                with st.spinner("💾 Otimizando e salvando foto da capa..."):
                                    capa_b64 = gemini_service.baixar_imagem_url_base64(item["url"])
                                    if database.definir_capa(int(hq_alvo["id"]), capa_b64):
                                        st.success("🎉 Capa cadastrada com sucesso!")
                                        if session_res_key in st.session_state:
                                            del st.session_state[session_res_key]
                                        st.rerun()
                                    else:
                                        st.error("Não foi possível salvar a capa no banco de dados.")
    else:
        st.info("ℹ️ Nenhuma capa encontrada automaticamente. Tente alterar o termo de busca acima ou colar o link direto da imagem.")

    st.markdown("---")
    with st.expander("🔗 Cadastrar manualmente por link (URL direta de imagem)"):
        url_direta = st.text_input("URL da imagem (jpg, png, webp):", key=f"dlg_input_url_direta_{hq_alvo['id']}")
        if url_direta:
            st.image(obter_imagem_capa(url_direta), width=160, caption="Pré-visualização da URL")
            if st.button("💾 Salvar Capa por URL", key=f"btn_salvar_url_direta_{hq_alvo['id']}", type="primary"):
                with st.spinner("Salvando capa..."):
                    capa_b64 = gemini_service.baixar_imagem_url_base64(url_direta)
                    if database.definir_capa(int(hq_alvo["id"]), capa_b64):
                        st.success("🎉 Capa salva com sucesso!")
                        if session_res_key in st.session_state:
                            del st.session_state[session_res_key]
                        st.rerun()

    if st.button("❌ Fechar / Cancelar", key=f"dlg_btn_close_busca_capa_{hq_alvo['id']}", use_container_width=True):
        if session_res_key in st.session_state:
            del st.session_state[session_res_key]
        st.rerun()


# Aliases de compatibilidade
dialog_buscar_autores = dialog_buscar_dados
dialog_buscar_resumo = dialog_buscar_dados



@st.dialog("💰 Buscar Preço da HQ Online", width="large")
def dialog_buscar_preco(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    id_para_preco = st.number_input("Informe o ID da HQ:", min_value=1, step=1, value=val_id, key=f"dlg_input_buscar_preco_id_{id_padrao or 'padrao'}")
    hq_alvo = database.obter_hq_por_id(int(id_para_preco))
    if not hq_alvo:
        st.warning(f"Quadrinho com ID #{id_para_preco} não encontrado.")
        if st.button("❌ Fechar", key="btn_close_busca_preco_empty", use_container_width=True):
            st.rerun()
        return

    st.markdown(f"#### 📖 {hq_alvo['titulo']}")
    detalhes_str = []
    if hq_alvo.get("edicao"):
        detalhes_str.append(f"**Edição:** {hq_alvo['edicao']}")
    if hq_alvo.get("editora"):
        detalhes_str.append(f"**Editora:** {hq_alvo['editora']}")
    val_atual = float(hq_alvo.get("valor") or 0.0)
    if val_atual > 0:
        detalhes_str.append(f"**Preço Atual Cadastrado:** `R$ {val_atual:.2f}`")
    else:
        detalhes_str.append(f"**Preço Atual Cadastrado:** `Não informado`")

    if detalhes_str:
        st.caption(" • ".join(detalhes_str))

    termo_default = f"{hq_alvo['titulo']} {hq_alvo.get('edicao') or ''} {hq_alvo.get('editora') or ''}".strip()

    col_t1, col_t2 = st.columns([3.5, 1.2])
    with col_t1:
        termo_busca = st.text_input("Termo de busca na web:", value=termo_default, key=f"dlg_termo_preco_{hq_alvo['id']}")
    with col_t2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        btn_pesquisar = st.button("🔎 Pesquisar", key=f"dlg_btn_pesquisar_preco_{hq_alvo['id']}", use_container_width=True, type="primary")

    session_res_key = f"precos_encontrados_{hq_alvo['id']}"

    if btn_pesquisar or session_res_key not in st.session_state:
        with st.spinner("🔍 Buscando cotações e preços online..."):
            try:
                if not hasattr(gemini_service, "buscar_precos_online"):
                    import importlib
                    importlib.reload(gemini_service)
                fn_buscar = getattr(gemini_service, "buscar_precos_online", None)
                if fn_buscar:
                    resultados = fn_buscar(
                        titulo=termo_busca,
                        edicao=hq_alvo.get("edicao") or "",
                        editora=hq_alvo.get("editora") or "",
                        api_key=st.session_state.get("gemini_api_key")
                    )
                else:
                    resultados = []
            except Exception as e_busca:
                st.warning(f"Não foi possível consultar cotações externas no momento ({e_busca}).")
                resultados = []
            st.session_state[session_res_key] = resultados

    precos = st.session_state.get(session_res_key, [])

    if precos:
        st.markdown(f"**Ofertas e Preços Encontrados ({len(precos)}):** *Clique em **Selecionar este Preço** para atualizar o valor desta HQ no catálogo.*")

        for idx, item in enumerate(precos):
            with st.container(border=True):
                col_info, col_valor, col_btn = st.columns([3, 1.5, 1.8], gap="medium")
                with col_info:
                    st.markdown(f"**{item['titulo']}**")
                    link_txt = f"[Abrir anúncio na loja ➔]({item['link']})" if item.get("link") else ""
                    st.caption(f"🏬 Loja / Fonte: **{item.get('fonte', 'Online')}** {(' • ' + link_txt) if link_txt else ''}")
                with col_valor:
                    st.markdown(f"### 🏷️ `{item['preco_formatado']}`")
                with col_btn:
                    st.write("")
                    if st.button(f"✅ Selecionar Preço", key=f"btn_sel_preco_{hq_alvo['id']}_{idx}", use_container_width=True, type="primary"):
                        if database.definir_valor(int(hq_alvo["id"]), item["preco"]):
                            st.success(f"🎉 Preço atualizado para **{item['preco_formatado']}** com sucesso!")
                            if session_res_key in st.session_state:
                                del st.session_state[session_res_key]
                            st.rerun()
                        else:
                            st.error("Não foi possível salvar o valor no banco de dados.")
    else:
        st.info("ℹ️ Nenhum preço automático encontrado para este termo. Tente refinar o termo de busca ou insira o valor manualmente abaixo.")

    st.markdown("---")
    with st.expander("✍️ Inserir ou ajustar valor manualmente (R$)"):
        col_m1, col_m2 = st.columns([2, 1.2])
        with col_m1:
            valor_manual = st.number_input(
                "Valor da HQ (R$):",
                min_value=0.0,
                value=float(hq_alvo.get("valor") or 0.0),
                step=0.5,
                format="%.2f",
                key=f"dlg_input_valor_manual_{hq_alvo['id']}"
            )
        with col_m2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("💾 Salvar Valor Manual", key=f"btn_salvar_valor_manual_{hq_alvo['id']}", type="primary", use_container_width=True):
                if database.definir_valor(int(hq_alvo["id"]), valor_manual):
                    st.success(f"🎉 Valor atualizado para **R$ {valor_manual:.2f}** com sucesso!")
                    if session_res_key in st.session_state:
                        del st.session_state[session_res_key]
                    st.rerun()

    if st.button("❌ Fechar / Cancelar", key=f"dlg_btn_close_busca_preco_{hq_alvo['id']}", use_container_width=True):
        st.rerun()


# =============================================================
# ALIASES DE COMPATIBILIDADE: BUSCA UNIFICADA DE DADOS
# =============================================================
dialog_buscar_autores = dialog_buscar_dados
dialog_buscar_resumo = dialog_buscar_dados



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
def dialog_avaliar_hq(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    id_para_avaliar = st.number_input("Informe o ID da HQ:", min_value=1, step=1, value=val_id, key=f"dlg_input_rate_id_{id_padrao or 'padrao'}")
    hq_rate = database.obter_hq_por_id(int(id_para_avaliar))
    if hq_rate:
        tit_hq = hq_rate.get("titulo") or "Sem título"
        ed_hq = hq_rate.get("edicao") or ""
        ed_str = f" ({ed_hq})" if ed_hq else ""
        st.markdown(f"📖 **HQ:** **{tit_hq}**{ed_str} `(ID #{id_para_avaliar})`")
        nota_atual = int(hq_rate.get("avaliacao") or 0)
        nova_nota = st.selectbox(
            "Selecione a Nota:",
            options=[0, 1, 2, 3, 4, 5],
            index=nota_atual,
            key=f"dlg_sel_fast_nota_{id_padrao or 'padrao'}",
            format_func=lambda x: "⚪ Sem Avaliação (0)" if x == 0 else f"{'⭐' * x} ({x} de 5)"
        )
        col_av1, col_av2 = st.columns(2)
        with col_av1:
            if st.button("💾 Salvar Nota", type="primary", use_container_width=True, key=f"dlg_btn_save_nota_{id_padrao or 'padrao'}"):
                database.definir_avaliacao(int(id_para_avaliar), nova_nota)
                st.success("Avaliação salva com sucesso!")
                st.rerun()
        with col_av2:
            if st.button("❌ Fechar", key=f"dlg_btn_cancel_nota_{id_padrao or 'padrao'}", use_container_width=True):
                st.rerun()
    else:
        st.info(f"Nenhum quadrinho com o ID #{id_para_avaliar} foi encontrado.")
        if st.button("❌ Fechar", key=f"dlg_btn_close_rate_empty_{id_padrao or 'padrao'}", use_container_width=True):
            st.rerun()

@st.dialog("📖 Alterar Status de Leitura")
def dialog_alternar_leitura(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    id_para_toggle = st.number_input("Informe o ID da HQ:", min_value=1, step=1, value=val_id, key=f"dlg_input_toggle_id_{id_padrao or 'padrao'}")
    hq_toggle = database.obter_hq_por_id(int(id_para_toggle))
    if hq_toggle:
        tit_hq = hq_toggle.get("titulo") or "Sem título"
        ed_hq = f" ({hq_toggle.get('edicao')})" if hq_toggle.get("edicao") else ""
        st.markdown(f"📖 **HQ:** **{tit_hq}**{ed_hq} `(ID #{id_para_toggle})`")
        status_atual = hq_toggle.get("lido") or "Não Lido"
        st.caption(f"Status atual: **{status_atual}**")
        
        st.markdown("Selecione o novo status:")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            if st.button("⏳ Não Lido", use_container_width=True, type="primary" if status_atual == "Não Lido" else "secondary", key="btn_dlg_status_nl"):
                database.definir_status_leitura(int(id_para_toggle), "Não Lido")
                st.success("Status alterado para **Não Lido**!")
                st.rerun()
        with col_s2:
            if st.button("📚 Lendo", use_container_width=True, type="primary" if status_atual == "Lendo" else "secondary", key="btn_dlg_status_lendo"):
                database.definir_status_leitura(int(id_para_toggle), "Lendo")
                st.success("Status alterado para **Lendo**!")
                st.rerun()
        with col_s3:
            if st.button("✅ Lido", use_container_width=True, type="primary" if status_atual == "Lido" else "secondary", key="btn_dlg_status_lido"):
                database.definir_status_leitura(int(id_para_toggle), "Lido")
                st.success("Status alterado para **Lido**!")
                st.rerun()
    else:
        st.info(f"Nenhum quadrinho com o ID #{id_para_toggle} foi encontrado.")
        if st.button("❌ Fechar", key="dlg_btn_close_toggle_empty", use_container_width=True):
            st.rerun()

@st.dialog("🗑️ Excluir HQ")
def dialog_excluir_hq(id_padrao: Optional[int] = None):
    val_id = int(id_padrao) if id_padrao and id_padrao > 0 else 1
    id_para_excluir = st.number_input("Informe o ID da HQ a excluir:", min_value=1, step=1, value=val_id, key=f"dlg_input_delete_id_{id_padrao or 'padrao'}")
    hq_del = database.obter_hq_por_id(int(id_para_excluir))
    if hq_del:
        tit_hq = hq_del.get("titulo") or "Sem título"
        ed_hq = hq_del.get("edicao") or ""
        tit_completo = f"{tit_hq} ({ed_hq})" if ed_hq else tit_hq
        st.warning(f"⚠️ Deseja realmente excluir **'{tit_completo}'** `(ID #{id_para_excluir})` da sua coleção?")
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

    # 🚀 Hub de IA e Navegação Rápida
    st.markdown("#### 🚀 Hub de IA & Navegação")
    pag_atual = st.session_state.get("pagina_atual", "principal")

    def navegar_para(nome_pagina: str):
        st.session_state["pagina_atual"] = nome_pagina
        if nome_pagina == "auditoria_duplicatas":
            st.session_state["cache_duplicatas"] = None
        if nome_pagina == "principal" and "pagina" in st.query_params:
            del st.query_params["pagina"]
        elif nome_pagina != "principal":
            st.query_params["pagina"] = nome_pagina
        st.rerun()

    c_nav1, c_nav2 = st.columns(2)
    with c_nav1:
        if st.button("📚 Catálogo", use_container_width=True, type="primary" if pag_atual == "principal" else "secondary", key="nav_btn_cat"):
            navegar_para("principal")
        if st.button("🔍 Duplicatas", use_container_width=True, type="primary" if pag_atual == "auditoria_duplicatas" else "secondary", help="Auditoria e Limpeza de Duplicatas no Acervo", key="nav_btn_dups"):
            navegar_para("auditoria_duplicatas")
        if st.button("🧭 Ordem Leitura", use_container_width=True, type="primary" if pag_atual == "ordem_leitura" else "secondary", help="Guia de Ordem de Leitura e Cronologia de Sagas", key="nav_btn_ordem"):
            navegar_para("ordem_leitura")
        if st.button("🎙️ Storyteller", use_container_width=True, type="primary" if pag_atual == "storyteller" else "secondary", help="Aquecimento de Leitura e Narração por IA", key="nav_btn_story"):
            navegar_para("storyteller")
        if st.button("📦 Importação Lote", use_container_width=True, type="primary" if pag_atual == "importacao_lote" else "secondary", help="Importar coleções inteiras com curadoria da IA", key="nav_btn_lote"):
            navegar_para("importacao_lote")
    with c_nav2:
        if st.button("📖 Em Leitura", use_container_width=True, type="primary" if pag_atual == "em_leitura" else "secondary", key="nav_btn_lendo"):
            navegar_para("em_leitura")
        if st.button("📄 Importar Arquivo", use_container_width=True, type="primary" if pag_atual == "importacao_arquivo" else "secondary", help="Importação de HQs a partir de arquivo texto (.txt)", key="nav_btn_import_txt"):
            navegar_para("importacao_arquivo")
        if st.button("🔍 Detetive DNA", use_container_width=True, type="primary" if pag_atual == "dna_colecao" else "secondary", help="Diagnóstico do DNA da Coleção e Gaps Faltantes", key="nav_btn_dna"):
            navegar_para("dna_colecao")
        if st.button("🧠 Quiz Acervo", use_container_width=True, type="primary" if pag_atual == "quiz_acervo" else "secondary", help="Trivia & Quiz do seu Próprio Acervo", key="nav_btn_quiz"):
            navegar_para("quiz_acervo")

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
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.8-flash",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-3.1-pro-preview",
            "gemini-pro-latest"
        ],
        index=0,
        key="seletor_modelo_gemini",
        help="Automático: gemini-3.7-flash / 3.6 com fallback inteligente para máxima velocidade, curadoria e precisão de metadados."
    )

    def resolver_modelo(tipo: str) -> str:
        if modelo_selecionado != "Automático (Otimizado)":
            return modelo_selecionado
        return "gemini-3.7-flash"

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
        st.metric("⭐ Média Aval.", f"{stats.get('media_avaliacao', 0.0):.1f} / 5" if stats.get("media_avaliacao", 0.0) > 0 else "-")
    with col_m2:
        st.markdown(
            """
            <style>
            div.st-key-btn_metric_prat,
            div.st-key-btn_metric_em_leitura {
                margin-bottom: 0.5rem !important;
            }
            div.st-key-btn_metric_prat button,
            div.st-key-btn_metric_em_leitura button {
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
            div.st-key-btn_metric_prat button *,
            div.st-key-btn_metric_em_leitura button,
            div.st-key-btn_metric_em_leitura button * {
                font-size: 2.25rem !important;
                font-weight: 700 !important;
                line-height: 1.15 !important;
                color: inherit !important;
            }
            div.st-key-btn_metric_prat button:hover,
            div.st-key-btn_metric_prat button:hover *,
            div.st-key-btn_metric_em_leitura button:hover,
            div.st-key-btn_metric_em_leitura button:hover * {
                color: #ff4b4b !important;
                text-decoration: underline !important;
            }
            div.st-key-btn_metric_prat button:active,
            div.st-key-btn_metric_prat button:focus,
            div.st-key-btn_metric_em_leitura button:active,
            div.st-key-btn_metric_em_leitura button:focus {
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

        st.markdown(
            """
            <div data-testid="stMetricLabel" style="margin-bottom: 2px;">
                <p style="margin: 0; font-size: 14px; font-weight: 400; line-height: 1.25; color: inherit; opacity: 0.8;">📚 Em Leitura</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button(str(stats.get("total_lendo", 0)), key="btn_metric_em_leitura", help="Clique no número para abrir a seção de HQs Em Leitura"):
            st.session_state["pagina_atual"] = "em_leitura"
            st.rerun()

        st.metric("⏳ Não Lidos", stats.get("total_nao_lidos", 0))

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


# -------------------------------------------------------------
# PÁGINA DEDICADA: HQS EM LEITURA
# -------------------------------------------------------------
def renderizar_pagina_em_leitura():
    col_nav_t, col_nav_b = st.columns([3, 1.2])
    with col_nav_t:
        st.title("📖 HQs Em Leitura")
        st.markdown("Acompanhe e gerencie todos os quadrinhos que você está lendo no momento.")
    with col_nav_b:
        st.write("")
        if st.button("⬅️ Voltar ao Catálogo", type="primary", use_container_width=True, key="btn_voltar_em_leitura_top"):
            voltar_ao_catalogo()

    st.markdown("---")

    hqs_lendo = database.obter_hqs_em_leitura()

    if not hqs_lendo:
        with st.container(border=True):
            st.info("📚 **Não existe nenhuma HQ sendo lida no momento.**", icon="ℹ️")
            st.markdown(
                "Para colocar uma edição em leitura, altere o status dela para **'Lendo'** na tabela do catálogo, nos detalhes da edição ou por comando de voz/IA com o assistente."
            )
        st.markdown("---")
        if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_em_leitura_vazio", use_container_width=True):
            voltar_ao_catalogo()
        return

    st.markdown(f"### 📚 Quadrinhos em Andamento ({len(hqs_lendo)})")

    for idx, hq_item in enumerate(hqs_lendo):
        hq_id = int(hq_item["id"])
        with st.container(border=True):
            col_capa, col_detalhes = st.columns([1.1, 3.2], gap="medium")

            with col_capa:
                img_capa = obter_imagem_capa(hq_item.get("capa"))
                tem_capa = bool(hq_item.get("capa") and str(hq_item["capa"]).strip())
                legenda_capa = "Foto da Capa" if tem_capa else "Capa Padrão (Não cadastrada)"
                st.image(img_capa, caption=legenda_capa, use_container_width=True)

                col_cb1, col_cb2 = st.columns(2)
                with col_cb1:
                    if st.button("🔍 Buscar Dados", key=f"btn_buscar_dados_lendo_{hq_id}_{idx}", use_container_width=True, type="primary" if not tem_capa else "secondary", help="Buscar Roteiro, Desenho, Preço e Capa no Guia dos Quadrinhos"):
                        dialog_buscar_dados(hq_id)
                with col_cb2:
                    if st.button("🖼️ Buscar Capa", key=f"btn_buscar_capa_lendo_{hq_id}_{idx}", use_container_width=True, help="Buscar opções de capa desta HQ na internet"):
                        dialog_buscar_capa(hq_id)

                label_foto = "📷 Enviar Foto" if not tem_capa else "📷 Alterar Foto"
                if st.button(label_foto, key=f"btn_foto_capa_lendo_{hq_id}_{idx}", use_container_width=True, help="Tirar foto ou upload da capa"):
                    dialog_cadastrar_capa(hq_id)

            with col_detalhes:
                st.subheader(f"📖 {hq_item['titulo']}")

                meta_itens = []
                if hq_item.get("edicao"):
                    meta_itens.append(f"🔖 **Edição/Vol:** {hq_item['edicao']}")
                if hq_item.get("editora"):
                    meta_itens.append(f"🏢 **Editora:** {hq_item['editora']}")
                if hq_item.get("genero"):
                    meta_itens.append(f"🏷️ **Gênero:** {hq_item['genero']}")
                if hq_item.get("escritor") and hq_item["escritor"] != "Não informado":
                    meta_itens.append(f"✍️ **Roteiro:** {hq_item['escritor']}")
                if hq_item.get("ilustrador") and hq_item["ilustrador"] != "Não informado":
                    meta_itens.append(f"🎨 **Arte:** {hq_item['ilustrador']}")
                if hq_item.get("prateleira"):
                    meta_itens.append(f"📍 **Prateleira:** `{hq_item['prateleira']}`")

                if meta_itens:
                    st.markdown(" • ".join(meta_itens))

                status_leitura = hq_item.get("lido", "Lendo")
                aval = int(hq_item.get("avaliacao") or 0)
                aval_texto = ("⭐" * aval + f" ({aval}/5)") if aval > 0 else "⚪ Sem avaliação"
                st.caption(f"Status: **📚 {status_leitura}** | Avaliação: **{aval_texto}**")

                st.markdown("---")

                st.markdown("#### 📝 Resumo")
                resumo_texto = (hq_item.get("resumo") or "").strip()
                if resumo_texto:
                    st.markdown(f"> {resumo_texto}")
                else:
                    st.info("ℹ️ *Esta edição ainda não possui um resumo cadastrado. Você pode adicioná-lo clicando em 'Editar HQ'.*")

                resenha_texto = (hq_item.get("resenha") or "").strip()
                if resenha_texto:
                    st.markdown("#### ✍️ Resenha / Opinião")
                    st.markdown(f"> {resenha_texto}")

                st.markdown("")

                col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns([1.8, 1.4, 1.2, 1.2, 1.2])
                with col_b1:
                    if st.button("✅ Concluir (Lido)", key=f"btn_concluir_lendo_{hq_id}_{idx}", use_container_width=True, type="primary", help="Marcar esta HQ como 'Lido'"):
                        database.definir_status_leitura(hq_id, "Lido")
                        st.success(f"🎉 Leitura de **'{hq_item['titulo']}'** concluída com sucesso!")
                        st.rerun()
                with col_b2:
                    if st.button("🎙️ Storyteller", key=f"btn_story_lendo_{hq_id}_{idx}", use_container_width=True, help="Ouvir aquecimento narrativo antes de ler"):
                        st.session_state["storyteller_hq_id"] = hq_id
                        st.session_state["pagina_atual"] = "storyteller"
                        st.rerun()
                with col_b3:
                    if st.button("✍️ Resenha", key=f"btn_resenha_lendo_{hq_id}_{idx}", use_container_width=True, help="Escrever resenha ou avaliar"):
                        dialog_resenha(hq_id)
                with col_b4:
                    if st.button("✏️ Editar", key=f"btn_editar_lendo_{hq_id}_{idx}", use_container_width=True, help="Editar informações desta HQ"):
                        dialog_editar_hq(hq_id)
                with col_b5:
                    if st.button("⏳ Pausar", key=f"btn_pausar_lendo_{hq_id}_{idx}", use_container_width=True, help="Mudar status para 'Não Lido'"):
                        database.definir_status_leitura(hq_id, "Não Lido")
                        st.info(f"Status de **'{hq_item['titulo']}'** alterado para 'Não Lido'.")
                        st.rerun()

    st.markdown("---")
    if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_em_leitura_bottom", use_container_width=True):
        voltar_ao_catalogo()


def player_audio_speech(texto_locucao: str):
    """
    Renderiza um player de narração em áudio de alta fidelidade utilizando a Web Speech API do navegador.
    Suporta reproduzir, pausar, parar e controle de velocidade nativo em português (pt-BR).
    """
    import html
    texto_limpo = (texto_locucao or "").strip().replace("\r", " ")
    texto_escaped = html.escape(texto_limpo).replace("\n", " ").replace("'", "\\'").replace('"', '\\"')
    
    html_code = f"""
    <div style="background: linear-gradient(135deg, #1b172b 0%, #291a38 100%); border: 1px solid #9d4edd; border-radius: 12px; padding: 16px 20px; margin: 15px 0; color: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 4px 14px rgba(0,0,0,0.35);">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 24px;">🎙️</span>
                <div>
                    <strong style="font-size: 15px; color: #e0aaff; display: block;">Narrador Imersivo de HQs</strong>
                    <span style="font-size: 12px; color: #c77dff;">Aquecimento de Leitura por Voz</span>
                </div>
            </div>
            <span id="speech-status" style="font-size: 12px; background: rgba(157, 78, 221, 0.25); border: 1px solid #7b2cbf; color: #e0aaff; padding: 4px 12px; border-radius: 20px; font-weight: 500;">Pronto para narrar</span>
        </div>
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
            <button id="btn-play" onclick="falarTexto()" style="background: #7b2cbf; color: white; border: none; padding: 9px 18px; border-radius: 8px; font-weight: bold; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: 0.2s;">
                ▶️ Ouvir Narração
            </button>
            <button id="btn-pause" onclick="pausarTexto()" style="background: #3c096c; color: white; border: 1px solid #5a189a; padding: 9px 14px; border-radius: 8px; cursor: pointer;">
                ⏸️ Pausar
            </button>
            <button id="btn-stop" onclick="pararTexto()" style="background: #240046; color: #ff9e00; border: 1px solid #3c096c; padding: 9px 14px; border-radius: 8px; cursor: pointer;">
                ⏹️ Parar
            </button>
            <div style="margin-left: auto; display: flex; align-items: center; gap: 6px; font-size: 12px; color: #c77dff;">
                <span>Velocidade:</span>
                <select id="sel-rate" onchange="mudarRate(this.value)" style="background: #240046; color: #e0aaff; border: 1px solid #5a189a; border-radius: 6px; padding: 4px 8px; font-size: 12px; outline: none;">
                    <option value="0.9">0.9x (Dramático)</option>
                    <option value="1.0" selected>1.0x (Normal)</option>
                    <option value="1.15">1.15x (Dinâmico)</option>
                    <option value="1.3">1.3x (Rápido)</option>
                </select>
            </div>
        </div>
    </div>
    <script>
    let synth = window.speechSynthesis;
    let utterance = null;
    let currentRate = 1.0;
    
    function mudarRate(v) {{
        currentRate = parseFloat(v);
        if (synth && synth.speaking) {{
            pararTexto();
            falarTexto();
        }}
    }}
    
    function falarTexto() {{
        if (!synth) {{
            alert('Seu navegador não suporta a síntese de voz (Web Speech API).');
            return;
        }}
        if (synth.paused) {{
            synth.resume();
            document.getElementById('speech-status').innerText = '🎙️ Narrando...';
            return;
        }}
        synth.cancel();
        const texto = "{texto_escaped}";
        utterance = new SpeechSynthesisUtterance(texto);
        utterance.lang = 'pt-BR';
        utterance.rate = currentRate;
        utterance.pitch = 0.95;
        
        let voices = synth.getVoices();
        let ptVoice = voices.find(v => v.lang === 'pt-BR' || v.lang.startsWith('pt'));
        if (ptVoice) utterance.voice = ptVoice;
        
        utterance.onstart = () => {{ document.getElementById('speech-status').innerText = '🎙️ Narrando...'; }};
        utterance.onend = () => {{ document.getElementById('speech-status').innerText = '✅ Narração concluída'; }};
        utterance.onerror = (e) => {{ document.getElementById('speech-status').innerText = 'Status: ' + (e.error || 'Pronto'); }};
        
        synth.speak(utterance);
    }}
    
    function pausarTexto() {{
        if (synth && synth.speaking) {{
            if (synth.paused) {{
                synth.resume();
                document.getElementById('speech-status').innerText = '🎙️ Narrando...';
            }} else {{
                synth.pause();
                document.getElementById('speech-status').innerText = '⏸️ Pausado';
            }}
        }}
    }}
    
    function pararTexto() {{
        if (synth) {{
            synth.cancel();
            document.getElementById('speech-status').innerText = '⏹️ Parado';
        }}
    }}
    </script>
    """
    st.components.v1.html(html_code, height=140)


# -------------------------------------------------------------
# PÁGINA DEDICADA: GUIA DE ORDEM DE LEITURA & CRONOLOGIA DE SAGAS
# -------------------------------------------------------------
def renderizar_pagina_ordem_leitura():
    col_nav_t, col_nav_b = st.columns([3, 1.2])
    with col_nav_t:
        st.title("🧭 Guia de Ordem de Leitura & Cronologia de Sagas")
        st.markdown("Descubra a sequência canônica ideal de leitura para qualquer saga, universo ou personagem, cruzando automaticamente com as edições que você já tem na estante.")
    with col_nav_b:
        st.write("")
        if st.button("⬅️ Voltar ao Catálogo", type="primary", use_container_width=True, key="btn_voltar_ordem_top"):
            voltar_ao_catalogo()

    st.markdown("---")

    catalogo_atual = database.obter_contexto_hqs_para_chat()

    with st.container(border=True):
        st.subheader("🎯 Qual saga ou personagem você deseja explorar?")
        
        # Sugestões rápidas
        st.caption("Sugestões populares para 1 clique:")
        col_sug1, col_sug2, col_sug3 = st.columns(3)
        tema_sugerido = None
        with col_sug1:
            if st.button("🦇 Batman: Ano Um até Asilo Arkham", use_container_width=True, key="btn_sug_batman"):
                tema_sugerido = "Batman: Da origem em Ano Um até Asilo Arkham e Vitória Sombria"
            if st.button("⏳ Sandman: Cronologia do Sonhar", use_container_width=True, key="btn_sug_sandman"):
                tema_sugerido = "Sandman: Cronologia completa de Neil Gaiman e Prelúdio"
        with col_sug2:
            if st.button("🌌 Saga do Infinito (Thanos)", use_container_width=True, key="btn_sug_infinito"):
                tema_sugerido = "Saga do Infinito da Marvel: Desafio Infinito até Guerra Infinita"
            if st.button("⚔️ Berserk: Da Era de Ouro ao Espadachim Negro", use_container_width=True, key="btn_sug_berserk"):
                tema_sugerido = "Berserk: Ordem canônica dos arcos do mangá de Kentaro Miura"
        with col_sug3:
            if st.button("⚡ Crise nas Infinitas Terras", use_container_width=True, key="btn_sug_crise"):
                tema_sugerido = "Crise nas Infinitas Terras e os antecedentes da DC Comics"
            if st.button("🧬 X-Men: Era do Apocalipse", use_container_width=True, key="btn_sug_xmen"):
                tema_sugerido = "X-Men: A Saga da Era do Apocalipse e Dias de um Futuro Esquecido"

        col_in_t, col_in_b = st.columns([3.5, 1.2])
        with col_in_t:
            input_tema_leitura = st.text_input(
                "Digite o nome da saga, herói, arco ou universo:",
                value=tema_sugerido or "",
                placeholder="Ex: Demolidor de Frank Miller, Guerras Secretas, Cavaleiro da Lua, Monstro do Pântano...",
                key="input_tema_ordem_leitura"
            )
        with col_in_b:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            btn_gerar_ordem = st.button("🧭 Gerar Guia com IA", type="primary", use_container_width=True, key="btn_exec_ordem_leitura")

    tema_para_processar = tema_sugerido or (input_tema_leitura.strip() if btn_gerar_ordem and input_tema_leitura.strip() else None)

    if tema_para_processar:
        if not os.getenv("GEMINI_API_KEY"):
            st.error("Chave de API do Gemini não configurada! Configure-a na barra lateral.")
        else:
            with st.spinner(f"🤖 Mapeando continuidade e cruzando com suas {len(catalogo_atual)} HQs..."):
                resultado = gemini_service.gerar_ordem_leitura(
                    tema_ou_saga=tema_para_processar,
                    catalogo_hqs=catalogo_atual,
                    api_key=os.getenv("GEMINI_API_KEY"),
                    modelo=resolver_modelo("chat")
                )
                st.session_state["ordem_leitura_resultado"] = resultado

    if st.session_state.get("ordem_leitura_resultado"):
        res = st.session_state["ordem_leitura_resultado"]
        
        st.markdown(f"## 📖 {res.get('saga_identificada', 'Guia de Leitura')}")
        universo_badge = res.get("universo", "Geral")
        st.caption(f"Universo: **{universo_badge}** | Análise gerada com base no seu acervo pessoal")
        
        if res.get("introducao"):
            st.info(f"💡 **Contexto da Cronologia:**\n\n{res['introducao']}", icon="✨")

        etapas = res.get("etapas", [])
        if etapas:
            st.markdown(f"### 🚀 Roteiro Passo a Passo ({len(etapas)} Edições)")
            
            for item in etapas:
                ordem_num = item.get("ordem", 1)
                tit_item = item.get("titulo", "Sem título")
                ed_item = item.get("edicao_recomendada", "")
                imp = item.get("importancia", "Essencial")
                sinopse = item.get("sinopse_rapida", "")
                status_col = item.get("status_colecao", "faltante")
                hq_id = item.get("hq_id")
                prat = item.get("prateleira")
                lido_st = item.get("lido", "Não Lido")
                termo_compra = item.get("termo_busca_compra") or f"{tit_item} {ed_item}".strip()

                with st.container(border=True):
                    col_num, col_corpo, col_acoes = st.columns([0.6, 3.2, 1.4])
                    
                    with col_num:
                        st.markdown(f"<div style='font-size: 2.2rem; font-weight: bold; color: #9d4edd; text-align: center; line-height: 1.2;'>#{ordem_num}</div>", unsafe_allow_html=True)
                        st.caption(f"<div style='text-align: center;'>{imp}</div>", unsafe_allow_html=True)
                        
                    with col_corpo:
                        ed_str = f" • *{ed_item}*" if ed_item else ""
                        st.markdown(f"#### {tit_item}{ed_str}")
                        if sinopse:
                            st.write(sinopse)
                            
                        if status_col == "no_acervo":
                            st.success(f"✅ **Você possui na estante!** Localização: `{prat or 'Catálogo'}` (ID #{hq_id}) | Status: **{lido_st}**", icon="📍")
                        else:
                            st.warning(f"🛒 **Edição Faltante (Gap):** Esta obra é recomendada para completar a saga.", icon="⚠️")
                            
                    with col_acoes:
                        st.write("")
                        if status_col == "no_acervo" and hq_id:
                            if st.button("🎙️ Storyteller", key=f"btn_story_ordem_{ordem_num}_{hq_id}", use_container_width=True, help="Ouvir aquecimento narrativo desta edição"):
                                st.session_state["storyteller_hq_id"] = int(hq_id)
                                st.session_state["pagina_atual"] = "storyteller"
                                st.rerun()
                            if lido_st != "Lido":
                                if st.button("✅ Marcar Lido", key=f"btn_lido_ordem_{ordem_num}_{hq_id}", use_container_width=True):
                                    database.definir_status_leitura(int(hq_id), "Lido")
                                    st.success("Marcado como Lido!")
                                    st.rerun()
                        else:
                            if st.button("⭐ Add Desejos", key=f"btn_wish_ordem_{ordem_num}", use_container_width=True, help="Adicionar à Lista de Desejos"):
                                database.adicionar_item_lista_desejos(
                                    titulo=tit_item,
                                    edicao=ed_item,
                                    editora="",
                                    observacoes=f"Sugerido no Guia de Leitura de '{res.get('saga_identificada')}'"
                                )
                                st.success("Adicionado à Lista de Desejos!")
                                st.rerun()
                            if st.button("🔍 Ver Preços", key=f"btn_preco_ordem_{ordem_num}", use_container_width=True, help="Consultar preço no Google Shopping"):
                                with st.spinner("Buscando preços..."):
                                    cot = gemini_service.pesquisar_precos_serpapi(termo_compra)
                                    st.session_state["radar_precos_resultado"] = cot
                                    st.success(f"Encontradas {cot.get('total_encontrados', 0)} ofertas!")

        gaps = res.get("gaps_criticos", [])
        if gaps:
            with st.expander(f"🛒 Gaps Críticos da Saga ({len(gaps)} edições não encontradas no seu acervo)", expanded=False):
                for g in gaps:
                    st.write(f"- 📕 **{g.get('titulo')}** ({g.get('edicao', '')}): *{g.get('motivo', '')}*")

        if res.get("dica_curador"):
            st.markdown("---")
            st.info(f"💡 **Dica do Curador Geek:** {res['dica_curador']}", icon="🎩")

    st.markdown("---")
    if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_ordem_bottom", use_container_width=True):
        voltar_ao_catalogo()


# -------------------------------------------------------------
# PÁGINA DEDICADA: DETETIVE DE COLEÇÃO & DNA DO COLECIONADOR
# -------------------------------------------------------------
def renderizar_pagina_dna_colecao():
    col_nav_t, col_nav_b = st.columns([3, 1.2])
    with col_nav_t:
        st.title("🔍 Detetive de Coleção & DNA do Colecionador")
        st.markdown("Diagnóstico profundo dos seus hábitos de leitura, arquétipo de colecionador e **detecção automática de volumes e séries incompletas**.")
    with col_nav_b:
        st.write("")
        if st.button("⬅️ Voltar ao Catálogo", type="primary", use_container_width=True, key="btn_voltar_dna_top"):
            voltar_ao_catalogo()

    st.markdown("---")

    catalogo_atual = database.obter_contexto_hqs_para_chat()

    col_btn_diag, _ = st.columns([1.8, 3])
    with col_btn_diag:
        btn_exec_dna = st.button("🧬 Analisar DNA do Meu Acervo & Gaps", type="primary", use_container_width=True, key="btn_exec_dna_act")

    if btn_exec_dna or (st.session_state.get("dna_colecao_resultado") is None and catalogo_atual):
        if not os.getenv("GEMINI_API_KEY"):
            st.error("Chave de API do Gemini não configurada! Insira na barra lateral.")
        else:
            with st.spinner(f"🤖 Realizando raio-X completo das suas {len(catalogo_atual)} HQs..."):
                diag = gemini_service.analisar_dna_colecao_e_gaps(
                    catalogo_hqs=catalogo_atual,
                    api_key=os.getenv("GEMINI_API_KEY"),
                    modelo=resolver_modelo("chat")
                )
                st.session_state["dna_colecao_resultado"] = diag

    if st.session_state.get("dna_colecao_resultado"):
        dna = st.session_state["dna_colecao_resultado"]

        # Hero Banner do Arquétipo
        with st.container(border=True):
            st.markdown(f"### 🌟 Seu Arquétipo: <span style='color: #9d4edd;'>{dna.get('arquetipo_colecionador', 'Colecionador Eclético')}</span>", unsafe_allow_html=True)
            if dna.get("resumo_dna"):
                st.markdown(dna["resumo_dna"])

        col_d1, col_d2 = st.columns([1.5, 1.5], gap="medium")

        with col_d1:
            with st.container(border=True):
                st.markdown("#### 📊 Distribuição de Estilos & Gêneros")
                dist = dna.get("distribuicao_estilos", [])
                if dist:
                    for d in dist:
                        cat_nome = d.get("categoria", "Geral")
                        pct = int(d.get("porcentagem", 20))
                        st.write(f"**{cat_nome}** — `{pct}%`")
                        st.progress(min(1.0, max(0.0, pct / 100.0)))
                else:
                    st.caption("Sem dados de distribuição disponíveis.")

        with col_d2:
            with st.container(border=True):
                st.markdown("#### 🏆 Pontos Fortes da Sua Coleção")
                pontos = dna.get("pontos_fortes_acervo", [])
                if pontos:
                    for p in pontos:
                        st.markdown(f"- ✅ {p}")
                else:
                    st.caption("Pontos fortes ainda não calculados.")

        st.markdown("---")

        # Detetive de Gaps
        st.markdown("### 🔍 Detetive de Gaps (Volumes e Séries Faltantes)")
        st.caption("Identificação de volumes intermediários ou conclusões de séries que estão faltando na sua estante:")
        gaps_lista = dna.get("gaps_detectados", [])

        if not gaps_lista:
            st.success("🎉 **Nenhum gap crítico detectado!** Suas séries identificadas parecem completas ou em dia.", icon="✨")
        else:
            for idx_g, gap_it in enumerate(gaps_lista):
                with st.container(border=True):
                    col_g_info, col_g_act = st.columns([3, 1.2])
                    with col_g_info:
                        serie = gap_it.get("serie", "Série")
                        possuidos = gap_it.get("volumes_possuidos", "")
                        faltante = gap_it.get("volume_faltante", "")
                        prio = gap_it.get("prioridade", "Alta")
                        motivo = gap_it.get("motivo", "")
                        termo = gap_it.get("termo_busca") or f"{serie} {faltante}".strip()

                        st.markdown(f"#### 📕 {serie} — <span style='color: #ff007f;'>Falta: {faltante}</span>", unsafe_allow_html=True)
                        st.markdown(f"📚 **Você já possui:** `{possuidos}` | Prioridade: **{prio}**")
                        st.write(f"💡 *{motivo}*")

                    with col_g_act:
                        st.write("")
                        if st.button("⭐ Salvar nos Desejos", key=f"btn_wish_gap_{idx_g}", use_container_width=True):
                            database.adicionar_item_lista_desejos(
                                titulo=serie,
                                edicao=faltante,
                                editora="",
                                observacoes=f"Detectado pelo Detetive de Gaps: {motivo}"
                            )
                            st.success("Adicionado à Lista de Desejos!")
                            st.rerun()

                        if st.button("🛒 Ver Ofertas", key=f"btn_preco_gap_{idx_g}", use_container_width=True):
                            with st.spinner("Buscando preços..."):
                                cot = gemini_service.pesquisar_precos_serpapi(termo)
                                st.session_state["radar_precos_resultado"] = cot
                                st.success(f"Encontradas {cot.get('total_encontrados', 0)} ofertas!")

        st.markdown("---")

        # Recomendações Cirúrgicas
        st.markdown("### 🎯 Recomendações Cirúrgicas de Próximas Compras")
        st.caption("Obras selecionadas a dedo pela IA conectando diretamente com seus quadrinhos mais bem avaliados:")
        recs = dna.get("recomendacoes_cirurgicas", [])

        if recs:
            for idx_r, rec in enumerate(recs):
                with st.container(border=True):
                    c_r_info, c_r_act = st.columns([3, 1.2])
                    with c_r_info:
                        st.markdown(f"#### 📖 {rec.get('titulo')} *(Editora: {rec.get('editora', 'Desconhecida')})*")
                        st.caption(f"✍️ Autor/Arte: **{rec.get('autor', 'Não informado')}**")
                        st.write(f"💡 **Por que você vai amar:** {rec.get('por_que_comprar', '')}")
                    with c_r_act:
                        st.write("")
                        if st.button("⭐ Add aos Desejos", key=f"btn_wish_rec_{idx_r}", use_container_width=True):
                            database.adicionar_item_lista_desejos(
                                titulo=rec.get("titulo", ""),
                                edicao="",
                                editora=rec.get("editora", ""),
                                observacoes=f"Recomendação de DNA: {rec.get('por_que_comprar', '')}"
                            )
                            st.success("Adicionado à Lista de Desejos!")
                            st.rerun()
                        if st.button("🔍 Buscar Preço", key=f"btn_preco_rec_{idx_r}", use_container_width=True):
                            termo_r = rec.get("termo_busca") or rec.get("titulo", "")
                            with st.spinner("Buscando preços..."):
                                cot = gemini_service.pesquisar_precos_serpapi(termo_r)
                                st.session_state["radar_precos_resultado"] = cot
                                st.success(f"Encontradas {cot.get('total_encontrados', 0)} ofertas!")

    st.markdown("---")
    if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_dna_bottom", use_container_width=True):
        voltar_ao_catalogo()


# -------------------------------------------------------------
# PÁGINA DEDICADA: STORYTELLER & AQUECIMENTO DE LEITURA POR IA
# -------------------------------------------------------------
def renderizar_pagina_storyteller():
    col_nav_t, col_nav_b = st.columns([3, 1.2])
    with col_nav_t:
        st.title("🎙️ Storyteller & Aquecimento de Leitura")
        st.markdown("Recapitulação narrativa imersiva estilo *\"Previously on...\"* com **narração por voz da IA** para você entrar no clima antes de abrir as páginas.")
    with col_nav_b:
        st.write("")
        if st.button("⬅️ Voltar ao Catálogo", type="primary", use_container_width=True, key="btn_voltar_story_top"):
            voltar_ao_catalogo()

    st.markdown("---")

    catalogo = database.obter_contexto_hqs_para_chat()
    if not catalogo:
        st.info("Nenhuma HQ cadastrada para gerar narrativa. Adicione algumas edições ao acervo primeiro.")
        return

    # Seletor de HQ
    opcoes_hqs = {f"#{h['id']} - {h['titulo']} ({h.get('edicao') or 'Sem Vol'})": int(h["id"]) for h in catalogo}
    hq_selecionada_id = st.session_state.get("storyteller_hq_id")
    
    # Encontra index inicial
    idx_init = 0
    if hq_selecionada_id:
        for i, val in enumerate(opcoes_hqs.values()):
            if val == hq_selecionada_id:
                idx_init = i
                break

    col_sel, col_btn = st.columns([3, 1.3])
    with col_sel:
        hq_label_sel = st.selectbox(
            "📖 Escolha a HQ que você vai começar a ler:",
            options=list(opcoes_hqs.keys()),
            index=idx_init,
            key="sel_storyteller_hq"
        )
        hq_alvo_id = opcoes_hqs[hq_label_sel]
    with col_btn:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        btn_gerar_story = st.button("🎙️ Gerar Aquecimento de Leitura", type="primary", use_container_width=True, key="btn_exec_story")

    hq_obj = database.obter_hq_por_id(hq_alvo_id)

    if btn_gerar_story or (st.session_state.get("storyteller_resultado") is None and hq_obj):
        if not os.getenv("GEMINI_API_KEY"):
            st.error("Chave de API do Gemini não configurada! Insira na barra lateral.")
        else:
            with st.spinner(f"🎙️ Criando narrativa imersiva para '{hq_obj['titulo']}'..."):
                hqs_lidas = [h for h in catalogo if h.get("lido") == "Lido"]
                story = gemini_service.gerar_recap_narrativo(
                    hq_alvo=hq_obj,
                    historico_hqs_lidas=hqs_lidas,
                    api_key=os.getenv("GEMINI_API_KEY"),
                    modelo=resolver_modelo("chat")
                )
                st.session_state["storyteller_resultado"] = story
                st.session_state["storyteller_hq_id"] = hq_alvo_id

    if st.session_state.get("storyteller_resultado") and hq_obj:
        story = st.session_state["storyteller_resultado"]

        col_capa, col_main_story = st.columns([1.1, 3], gap="medium")
        with col_capa:
            img_c = obter_imagem_capa(hq_obj.get("capa"))
            st.image(img_c, use_container_width=True, caption=hq_obj["titulo"])
            st.caption(f"📍 Prateleira: `{hq_obj.get('prateleira')}`\n\nStatus: **{hq_obj.get('lido', 'Não Lido')}**")

            if hq_obj.get("lido") != "Lendo":
                if st.button("📚 Colocar em 'Lendo'", use_container_width=True, type="primary"):
                    database.definir_status_leitura(hq_obj["id"], "Lendo")
                    st.success("Status alterado para 'Lendo'!")
                    st.rerun()

        with col_main_story:
            st.markdown(f"## 🎬 {story.get('titulo_recap', 'Aquecimento de Leitura')}")
            if story.get("clima_narrativo"):
                st.markdown(f"> *\"{story['clima_narrativo']}\"*")

            # Player de Áudio Speech
            texto_loc = story.get("texto_locucao") or story.get("o_que_esperar", "")
            if texto_loc:
                player_audio_speech(texto_loc)

            pilares = story.get("pilares_da_trama", [])
            if pilares:
                st.markdown("#### 🏛️ Pilares da Trama & Antecedentes")
                for p in pilares:
                    with st.container(border=True):
                        st.markdown(f"**⚡ {p.get('titulo', 'Ponto da Trama')}**")
                        st.write(p.get("descricao", ""))

            if story.get("o_que_esperar"):
                st.markdown("#### 👁️ O Que Prestar Atenção Nesta Edição")
                st.info(story["o_que_esperar"], icon="💡")

            if story.get("frase_de_impacto"):
                st.markdown(f"<div style='font-size: 1.15rem; font-weight: bold; color: #ff007f; text-align: center; padding: 10px;'>\"{story['frase_de_impacto']}\"</div>", unsafe_allow_html=True)

    st.markdown("---")
    if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_story_bottom", use_container_width=True):
        voltar_ao_catalogo()


# -------------------------------------------------------------
# PÁGINA DEDICADA: TRIVIA & QUIZ DO PRÓPRIO ACERVO
# -------------------------------------------------------------
def renderizar_pagina_quiz_acervo():
    col_nav_t, col_nav_b = st.columns([3, 1.2])
    with col_nav_t:
        st.title("🧠 Trivia & Quiz Interativo do seu Acervo")
        st.markdown("Teste seus conhecimentos com perguntas inteligentes baseadas **estritamente nas histórias, autores e curiosidades das HQs que você tem na estante**!")
    with col_nav_b:
        st.write("")
        if st.button("⬅️ Voltar ao Catálogo", type="primary", use_container_width=True, key="btn_voltar_quiz_top"):
            voltar_ao_catalogo()

    st.markdown("---")

    catalogo = database.obter_contexto_hqs_para_chat()
    if not catalogo:
        st.info("Cadastre pelo menos uma HQ no catálogo para poder jogar o Quiz do Acervo.")
        return

    with st.container(border=True):
        col_q1, col_q2, col_q3 = st.columns([1.5, 1.5, 1.5])
        with col_q1:
            nivel_sel = st.selectbox("Nível de Dificuldade:", ["Fácil", "Médio", "Hardcore"], index=1, key="sel_quiz_dif")
        with col_q2:
            qtd_sel = st.selectbox("Quantidade de Perguntas:", [3, 5, 8], index=1, key="sel_quiz_qtd")
        with col_q3:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            btn_iniciar_quiz = st.button("🎮 Gerar Novo Quiz", type="primary", use_container_width=True, key="btn_gerar_quiz_act")

    if btn_iniciar_quiz or (st.session_state.get("quiz_acervo_resultado") is None and catalogo):
        if not os.getenv("GEMINI_API_KEY"):
            st.error("Chave de API do Gemini não configurada! Insira na barra lateral.")
        else:
            with st.spinner("🤖 Elaborando perguntas exclusivas a partir dos quadrinhos do seu acervo..."):
                quiz_data = gemini_service.gerar_quiz_acervo(
                    catalogo_hqs=catalogo,
                    dificuldade=nivel_sel,
                    qtd_perguntas=qtd_sel,
                    api_key=os.getenv("GEMINI_API_KEY"),
                    modelo=resolver_modelo("chat")
                )
                st.session_state["quiz_acervo_resultado"] = quiz_data
                st.session_state["quiz_respostas_usuario"] = {}
                st.session_state["quiz_finalizado"] = False

    if st.session_state.get("quiz_acervo_resultado"):
        quiz = st.session_state["quiz_acervo_resultado"]
        perguntas = quiz.get("perguntas", [])

        if not perguntas:
            st.warning("Não foi possível gerar perguntas para o quiz. Tente novamente.")
        else:
            st.markdown(f"### 🏆 {quiz.get('tema_quiz', 'Quiz do Acervo')} — Nível: `{quiz.get('nivel', 'Médio')}`")
            
            with st.form("form_quiz_usuario"):
                for p in perguntas:
                    p_id = p.get("id", 1)
                    hq_rel = p.get("hq_titulo", "HQ do Acervo")
                    pergunta_texto = p.get("pergunta", "")
                    opcoes = p.get("opcoes", [])

                    st.markdown(f"#### ❓ Pergunta #{p_id}")
                    st.caption(f"📚 Obra relacionada: **{hq_rel}**")
                    st.markdown(f"**{pergunta_texto}**")

                    key_rad = f"quiz_rad_{p_id}"
                    val_atual = st.session_state.get("quiz_respostas_usuario", {}).get(p_id)
                    idx_val = 0
                    if val_atual and opcoes:
                        for i_op, op_t in enumerate(opcoes):
                            if op_t.startswith(val_atual):
                                idx_val = i_op
                                break

                    escolha = st.radio(
                        "Selecione sua resposta:",
                        options=opcoes,
                        key=key_rad,
                        label_visibility="collapsed"
                    )
                    # Letra selecionada (A, B, C ou D)
                    letra_escolhida = escolha[0] if escolha else "A"
                    st.session_state["quiz_respostas_usuario"][p_id] = letra_escolhida
                    st.markdown("---")

                btn_submeter_quiz = st.form_submit_button("🏁 Finalizar & Conferir Pontuação", type="primary", use_container_width=True)

            if btn_submeter_quiz:
                st.session_state["quiz_finalizado"] = True

            if st.session_state.get("quiz_finalizado"):
                acertos = 0
                total = len(perguntas)

                for p in perguntas:
                    p_id = p.get("id", 1)
                    resp_correta = str(p.get("resposta_correta", "A")).strip().upper()
                    user_resp = str(st.session_state.get("quiz_respostas_usuario", {}).get(p_id, "")).strip().upper()
                    if user_resp == resp_correta or (user_resp and user_resp[0] == resp_correta):
                        acertos += 1

                pct_acerto = (acertos / total) * 100 if total > 0 else 0

                st.markdown("---")
                if pct_acerto == 100:
                    st.balloons()
                    st.success(f"🏆 **INCRÍVEL! Pontuação Perfeita:** Você acertou **{acertos} de {total}** perguntas ({pct_acerto:.0f}%)! Você é um verdadeiro mestre do seu acervo!", icon="🌟")
                elif pct_acerto >= 60:
                    st.success(f"🎉 **Parabéns!** Você acertou **{acertos} de {total}** perguntas ({pct_acerto:.0f}%)!", icon="👏")
                else:
                    st.info(f"📚 **Resultado:** Você acertou **{acertos} de {total}** perguntas ({pct_acerto:.0f}%). Uma boa desculpa para reler algumas HQs da estante!", icon="🤓")

                st.markdown("### 📋 Gabarito & Curiosidades de Bastidores (Lore)")
                for p in perguntas:
                    p_id = p.get("id", 1)
                    resp_correta = str(p.get("resposta_correta", "A")).strip().upper()
                    user_resp = str(st.session_state.get("quiz_respostas_usuario", {}).get(p_id, "")).strip().upper()
                    eh_correta = (user_resp == resp_correta or (user_resp and user_resp[0] == resp_correta))

                    with st.container(border=True):
                        st.markdown(f"**Pergunta #{p_id}:** {p.get('pergunta')}")
                        if eh_correta:
                            st.success(f"✅ Sua resposta: **{user_resp}** (Correto!)", icon="✅")
                        else:
                            st.error(f"❌ Sua resposta: **{user_resp}** | Resposta correta: **{resp_correta}**", icon="❌")

                        lore = p.get("explicacao_lore")
                        if lore:
                            st.info(f"💡 **Lore & Curiosidade:** {lore}", icon="📖")

    st.markdown("---")
    if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_quiz_bottom", use_container_width=True):
        voltar_ao_catalogo()


def renderizar_pagina_importacao_lote():
    col_nav_t, col_nav_b = st.columns([3, 1.2])
    with col_nav_t:
        st.title("📦 Importação em Lote com Curadoria IA")
        st.markdown(
            "Cadastre coleções inteiras, sagas completas ou sequências de volumes de uma só vez "
            "(como a **Coleção Salvat 1 ao 64**, mangás, sagas Marvel/DC ou encadernados). "
            "A IA pesquisa todos os metadados (roteirista, desenhista, editora, gênero, sinopse e capas) "
            "e você revisa e aprova a listagem antes de salvar no seu acervo."
        )
    with col_nav_b:
        st.write("")
        if st.button("⬅️ Voltar ao Catálogo", type="primary", use_container_width=True, key="btn_voltar_lote_top"):
            voltar_ao_catalogo()

    st.markdown("---")

    # Sugestões rápidas de 1 clique
    st.markdown("#### 💡 Sugestões de Coleções e Sagas Populares:")
    col_sug1, col_sug2, col_sug3 = st.columns(3)
    
    proposta_sugerida = None
    with col_sug1:
        if st.button("🦸‍♂️ Marvel Salvat (1 ao 64)", use_container_width=True, key="sug_salvat"):
            proposta_sugerida = "Incluir a coleção Coleção Oficial de Graphic Novels Marvel (Salvat) do número 1 ao 64"
        if st.button("⚔️ Mangá Berserk (1 ao 40)", use_container_width=True, key="sug_berserk"):
            proposta_sugerida = "Importar a coleção do mangá Berserk da Panini dos volumes 1 ao 40"
    with col_sug2:
        if st.button("🦇 DC Eaglemoss (1 ao 20)", use_container_width=True, key="sug_eaglemoss"):
            proposta_sugerida = "Incluir a Coleção DC Comics Graphic Novels (Eaglemoss) do número 1 ao 20"
        if st.button("🪓 Chainsaw Man (1 ao 11)", use_container_width=True, key="sug_chainsaw"):
            proposta_sugerida = "Importar mangá Chainsaw Man da Panini volumes 1 a 11"
    with col_sug3:
        if st.button("⏳ Sandman Definitivo (1 ao 5)", use_container_width=True, key="sug_sandman"):
            proposta_sugerida = "Importar coleção Sandman Edição Definitiva volumes 1 a 5 da Panini"
        if st.button("📜 Clássica Marvel (1 ao 20)", use_container_width=True, key="sug_classica"):
            proposta_sugerida = "Incluir Coleção Clássica Marvel da Panini do número 1 ao 20"

    with st.container(border=True):
        st.subheader("📝 1. Defina a Coleção ou Lote a Ser Importado")
        
        texto_padrao = proposta_sugerida or st.session_state.get("importacao_lote_input_txt", "")
        proposta_input = st.text_area(
            "Descreva a coleção, sequência ou volumes desejados:",
            value=texto_padrao,
            placeholder='Ex: "Incluir a coleção Coleção Oficial de Graphic Novels Marvel (Salvat) do número 1 ao 64" ou "Cadastrar mangá One Piece volumes 1 a 12"',
            help="Especifique o nome da coleção ou série e o intervalo de volumes desejado.",
            height=85,
            key="input_proposta_lote_area"
        )

        col_cfg1, col_cfg2, col_cfg3 = st.columns([2, 1.2, 1.8])
        
        prateleiras_existentes = [p for p in database.obter_prateleiras() if p and p != "Estante 1 - Prateleira 1"]
        with col_cfg1:
            opcoes_p = ["➕ Digitar nova prateleira..."] + list(prateleiras_existentes)
            escolha_p = st.selectbox(
                "📍 Prateleira de Destino:",
                options=opcoes_p,
                index=1 if prateleiras_existentes else 0,
                key="sel_prateleira_lote"
            )
            if escolha_p == "➕ Digitar nova prateleira...":
                prateleira_destino = st.text_input("Nome da nova prateleira:", value="Estante de Coleções", key="txt_nova_prat_lote")
            else:
                prateleira_destino = escolha_p

        with col_cfg2:
            status_leitura_padrao = st.selectbox(
                "📖 Status Inicial:",
                options=["Não Lido", "Lido", "Lendo", "Quero Ler"],
                index=0,
                key="sel_status_lote"
            )

        with col_cfg3:
            st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
            buscar_capas_auto = st.checkbox(
                "🖼️ Buscar capas na internet",
                value=False,
                help="Busca capas oficiais em alta resolução (Apple Books / OpenLibrary) automaticamente.",
                key="chk_capas_lote"
            )

        col_btn_gerar, _ = st.columns([1.5, 2])
        with col_btn_gerar:
            btn_pesquisar_ia = st.button("🤖 1. Consultar IA & Gerar Prévia do Lote", type="primary", use_container_width=True, key="btn_exec_lote_ia")

    if btn_pesquisar_ia and proposta_input.strip():
        if not os.getenv("GEMINI_API_KEY"):
            st.error("❌ Chave de API do Gemini não configurada! Insira-a na barra lateral.")
        else:
            status_box = st.empty()
            def _atualizar_progresso(msg: str):
                status_box.info(msg, icon="⏳")

            with st.spinner("🤖 IA pesquisando a coleção e estruturando metadados..."):
                try:
                    itens_retornados = gemini_service.gerar_importacao_lote(
                        proposta=proposta_input.strip(),
                        prateleira_padrao=prateleira_destino.strip() or "Estante de Coleções",
                        lido_padrao=status_leitura_padrao,
                        api_key=os.getenv("GEMINI_API_KEY"),
                        modelo=resolver_modelo("chat"),
                        buscar_capas_auto=buscar_capas_auto,
                        progresso_callback=_atualizar_progresso
                    )
                    
                    if not itens_retornados:
                        st.warning("⚠️ A IA não conseguiu identificar edições para a proposta informada. Tente detalhar melhor o nome da coleção ou série.")
                    else:
                        status_box.empty()
                        # Enriquece com verificação de duplicidade determinística e probabilística (JEV)
                        catalogo_completo = database.obter_todos_quadrinhos()
                        itens_enriquecidos = []
                        for it in itens_retornados:
                            dup = database.verificar_hq_duplicada(
                                it.get("titulo", ""),
                                it.get("edicao", ""),
                                it.get("editora", "")
                            )
                            decisao_jev = jev_engine.decidir_duplicata_probabilistica(it, catalogo_completo)
                            
                            it_copy = dict(it)
                            if dup:
                                it_copy["incluir"] = False
                                it_copy["ja_no_acervo"] = True
                                it_copy["status_acervo"] = f"⚠️ Já no Acervo (ID #{dup['id']})"
                            elif decisao_jev.is_duplicate and decisao_jev.existing_id:
                                it_copy["incluir"] = False
                                it_copy["ja_no_acervo"] = True
                                it_copy["status_acervo"] = f"⚠️ Provável Duplicata (ID #{decisao_jev.existing_id} - {int(decisao_jev.confidence*100)}% match)"
                            elif decisao_jev.requires_human_confirmation:
                                it_copy["incluir"] = True
                                it_copy["ja_no_acervo"] = False
                                it_copy["status_acervo"] = f"🔍 Similar ao ID #{decisao_jev.existing_id} ({int(decisao_jev.confidence*100)}%)"
                            else:
                                it_copy["incluir"] = True
                                it_copy["ja_no_acervo"] = False
                                it_copy["status_acervo"] = "✨ Nova Edição"

                            if not it_copy.get("prateleira"):
                                it_copy["prateleira"] = prateleira_destino.strip() or "Estante de Coleções"
                            itens_enriquecidos.append(it_copy)

                        st.session_state["importacao_lote_dados"] = {
                            "itens": itens_enriquecidos,
                            "proposta": proposta_input.strip(),
                            "prateleira": prateleira_destino.strip() or "Estante de Coleções",
                            "lido": status_leitura_padrao
                        }
                        st.rerun()
                except Exception as ex:
                    status_box.empty()
                    st.error(f"❌ Ocorreu um erro ao consultar a IA: {ex}")

    # Exibição da Lista para Revisão & Aprovação
    if st.session_state.get("importacao_lote_dados"):
        dados_lote = st.session_state["importacao_lote_dados"]
        itens_lista = dados_lote.get("itens", [])

        if itens_lista:
            st.markdown("---")
            st.subheader(f"📋 2. Revisão & Aprovação do Lote ({len(itens_lista)} Edições Identificadas)")
            
            total_itens = len(itens_lista)
            total_existentes = sum(1 for it in itens_lista if it.get("ja_no_acervo"))
            total_novos = total_itens - total_existentes

            c_met1, c_met2, c_met3 = st.columns(3)
            with c_met1:
                st.metric("Total de Edições no Lote", total_itens)
            with c_met2:
                st.metric("Novas para Adicionar", total_novos)
            with c_met3:
                st.metric("Já no Acervo (Duplicadas)", total_existentes)

            st.info(
                "💡 **Revise e aprove antes de salvar:** Você pode desmarcar a caixa **'Incluir?'** para itens que não deseja adicionar "
                "e editar qualquer informação (Título, Volume, Roteirista, Sinopse, etc.) diretamente na tabela abaixo.",
                icon="✍️"
            )

            # Prepara DataFrame para exibição e edição interativa
            df_lote = pd.DataFrame(itens_lista)
            
            # Garante colunas esperadas
            colunas_esperadas = ["incluir", "edicao", "titulo", "editora", "genero", "escritor", "ilustrador", "prateleira", "resumo", "status_acervo"]
            for col in colunas_esperadas:
                if col not in df_lote.columns:
                    df_lote[col] = ""

            df_lote = df_lote[colunas_esperadas]

            df_editado = st.data_editor(
                df_lote,
                column_config={
                    "incluir": st.column_config.CheckboxColumn("Incluir?", help="Marque para cadastrar este item no banco de dados", default=True),
                    "edicao": st.column_config.TextColumn("Vol/Edição", width="small"),
                    "titulo": st.column_config.TextColumn("Título da Edição", width="large", required=True),
                    "editora": st.column_config.TextColumn("Editora", width="medium"),
                    "genero": st.column_config.TextColumn("Gênero", width="medium"),
                    "escritor": st.column_config.TextColumn("Roteirista", width="medium"),
                    "ilustrador": st.column_config.TextColumn("Desenhista", width="medium"),
                    "prateleira": st.column_config.TextColumn("Prateleira", width="medium"),
                    "resumo": st.column_config.TextColumn("Sinopse / Resumo", width="large"),
                    "status_acervo": st.column_config.TextColumn("Status no Acervo", disabled=True, width="medium"),
                },
                use_container_width=True,
                num_rows="dynamic",
                key="editor_tabela_lote"
            )

            # Seção expansível para visualização rica em cartões
            with st.expander(f"👁️ Visualizar Cards Detalhados ({len(itens_lista)} itens)", expanded=False):
                for idx_c, it_c in enumerate(itens_lista, 1):
                    with st.container(border=True):
                        c_card_capa, c_card_info = st.columns([1, 4])
                        with c_card_capa:
                            if it_c.get("capa"):
                                st.image(obter_imagem_capa(it_c["capa"]), width="stretch")
                            else:
                                st.caption("🖼️ Sem capa online")
                        with c_card_info:
                            st.markdown(f"**#{idx_c} - {it_c.get('titulo', 'Sem Título')}** (Vol: `{it_c.get('edicao', '-')}`)")
                            st.caption(f"🏢 **Editora:** {it_c.get('editora', '-')} | 🏷️ **Gênero:** {it_c.get('genero', '-')} | ✍️ **Roteiro:** {it_c.get('escritor', '-')} | 🎨 **Arte:** {it_c.get('ilustrador', '-')}")
                            if it_c.get("resumo"):
                                st.markdown(f"> *{it_c['resumo']}*")

            st.markdown("---")

            # Contagem dos itens marcados como 'incluir'
            itens_selecionados_df = df_editado[df_editado["incluir"] == True]
            qtd_para_salvar = len(itens_selecionados_df)

            col_salvar, col_limpar = st.columns([2, 1.2])
            with col_salvar:
                btn_confirmar_lote = st.button(
                    f"✅ 2. Aprovar e Cadastrar {qtd_para_salvar} HQs no Banco de Dados",
                    type="primary",
                    use_container_width=True,
                    disabled=(qtd_para_salvar == 0),
                    key="btn_aprovar_lote_banco"
                )

            with col_limpar:
                if st.button("🗑️ Descartar Prévia", use_container_width=True, key="btn_descartar_lote"):
                    del st.session_state["importacao_lote_dados"]
                    st.rerun()

            if btn_confirmar_lote:
                # Converte os itens aprovados do DataFrame para lista de dicionários
                itens_finais_para_banco = []
                for _, row in itens_selecionados_df.iterrows():
                    # Recupera URL da capa original se existir
                    idx_original = row.name if row.name in df_lote.index else None
                    capa_val = ""
                    if idx_original is not None and idx_original < len(itens_lista):
                        capa_val = itens_lista[idx_original].get("capa", "")

                    item_dict = {
                        "titulo": str(row.get("titulo", "")).strip(),
                        "edicao": str(row.get("edicao", "")).strip(),
                        "editora": str(row.get("editora", "")).strip(),
                        "genero": str(row.get("genero", "")).strip() or "Outro",
                        "escritor": str(row.get("escritor", "")).strip() or "Não informado",
                        "ilustrador": str(row.get("ilustrador", "")).strip() or "Não informado",
                        "prateleira": str(row.get("prateleira", "")).strip() or dados_lote.get("prateleira", "Estante de Coleções"),
                        "lido": dados_lote.get("lido", "Não Lido"),
                        "avaliacao": 0,
                        "capa": capa_val,
                        "resumo": str(row.get("resumo", "")).strip()
                    }
                    itens_finais_para_banco.append(item_dict)

                with st.spinner("💾 Gravando quadrinhos aprovados no banco de dados..."):
                    resultado_salvar = database.salvar_hqs(
                        itens=itens_finais_para_banco,
                        prateleira=dados_lote.get("prateleira", "Estante de Coleções"),
                        lido_padrao=dados_lote.get("lido", "Não Lido"),
                        ignorar_duplicadas=True,
                        retornar_detalhes=True
                    )

                st.balloons()
                del st.session_state["importacao_lote_dados"]

                num_salvos = resultado_salvar.get("salvos", 0) if isinstance(resultado_salvar, dict) else resultado_salvar
                num_dup = resultado_salvar.get("duplicados", 0) if isinstance(resultado_salvar, dict) else 0

                st.success(
                    f"🎉 **Lote importado com sucesso!** Foram cadastradas **{num_salvos} novas edições** no seu acervo."
                    + (f" ({num_dup} edições duplicadas foram ignoradas automaticamente)." if num_dup > 0 else ""),
                    icon="✅"
                )

                col_ir_cat, _ = st.columns([1.5, 2])
                with col_ir_cat:
                    if st.button("📚 Ir para o Catálogo e Ver Coleção", type="primary", use_container_width=True, key="btn_ir_cat_pos_lote"):
                        voltar_ao_catalogo()

    st.markdown("---")
    if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_lote_bottom", use_container_width=True):
        voltar_ao_catalogo()


# -------------------------------------------------------------
# PÁGINA DEDICADA: IMPORTAÇÃO DE ARQUIVO TEXTO (.TXT)
# -------------------------------------------------------------
def renderizar_pagina_importacao_arquivo():
    col_nav_t, col_nav_b = st.columns([3, 1.2])
    with col_nav_t:
        st.title("📄 Importação de Arquivo de HQs (.txt)")
        st.markdown(
            "Importe sua lista de quadrinhos a partir de um arquivo de texto. "
            "A IA fará o **de x para** de títulos e editoras, recuperará os metadados (gêneros, autores, sinopses e capas) "
            "e registrará os volumes no acervo com status **'Não Lido'** e o valor atribuído ao primeiro volume de cada série."
        )
    with col_nav_b:
        st.write("")
        if st.button("⬅️ Voltar ao Catálogo", type="primary", use_container_width=True, key="btn_voltar_import_txt_top"):
            voltar_ao_catalogo()

    st.markdown("---")

    # 1. Configuração de Destino e Opções
    # 1. Configuração da Prateleira de Destino
    with st.container(border=True):
        st.subheader("📍 1. Configuração da Prateleira de Destino")
        lista_prats = [p for p in database.obter_prateleiras() if p and p != "Estante 1 - Prateleira 1"]
        opcoes_prat_imp = ["-- Selecione uma prateleira --"] + list(lista_prats) + ["➕ Outra / Digitar nova prateleira..."]
        prat_imp_sel = st.selectbox("📍 Prateleira de destino para estas HQs:", options=opcoes_prat_imp, key="sel_prat_import_arquivo")
        
        prat_arquivo_final = "Não especificada"
        if prat_imp_sel == "➕ Outra / Digitar nova prateleira...":
            nova_p = st.text_input("✍️ Digite o nome da nova prateleira:", placeholder="Ex: Estante Principal - Prateleira 1", key="input_nova_prat_arquivo").strip()
            if nova_p:
                prat_arquivo_final = nova_p
        elif prat_imp_sel != "-- Selecione uma prateleira --":
            prat_arquivo_final = prat_imp_sel.strip()

    # 2. Entrada do Arquivo ou Texto
    st.markdown("### 📥 2. Envio do Arquivo ou Texto")
    tab_up_txt, tab_colar_txt = st.tabs(["📁 Enviar Arquivo .txt", "✍️ Colar Texto Diretamente"])

    conteudo_texto_importar = ""

    with tab_up_txt:
        arquivo_up = st.file_uploader(
            "Selecione um arquivo de texto (.txt):",
            type=["txt", "text", "tsv", "csv"],
            key="uploader_arquivo_hqs"
        )
        if arquivo_up is not None:
            try:
                conteudo_texto_importar = arquivo_up.getvalue().decode("utf-8")
            except UnicodeDecodeError:
                conteudo_texto_importar = arquivo_up.getvalue().decode("latin-1", errors="ignore")

    with tab_colar_txt:
        texto_colado = st.text_area(
            "Cole o conteúdo do arquivo texto abaixo:",
            value="",
            height=200,
            placeholder="""1984 /Companhia das Letras Valor: R$ 84,90\tQuantidade: 1
\tEstado: Excelente

300 de Esparta, Os (2ª Edição) /Devir Valor: R$ 89,90\tQuantidade: 1
\tEstado: Excelente

52 /Panini Valor: R$ 90,80\tQuantidade: 13
 nº 1\tEstado: Excelente \tStatus: Não li
 nº 2\tEstado: Excelente
 nº 3\tEstado: Excelente""",
            key="area_texto_importar_arquivo"
        )
        if texto_colado.strip():
            conteudo_texto_importar = texto_colado

    # 3. Parser e "De x Para" Local Instantâneo (Sem IA)
    if conteudo_texto_importar.strip():
        import hashlib
        hash_atual = hashlib.md5((conteudo_texto_importar + "___" + prat_arquivo_final).encode("utf-8", errors="ignore")).hexdigest()

        if st.session_state.get("importacao_txt_hash") != hash_atual:
            itens_brutos = gemini_service.parsear_arquivo_texto_hqs(conteudo_texto_importar)
            if itens_brutos:
                itens_processados = gemini_service.processar_de_para_local_hqs(
                    itens_parseados=itens_brutos,
                    prateleira_padrao=prat_arquivo_final
                )
                st.session_state["importacao_txt_itens"] = itens_processados
                st.session_state["importacao_txt_hash"] = hash_atual
            else:
                st.session_state["importacao_txt_itens"] = []
                st.session_state["importacao_txt_hash"] = hash_atual

        itens_processados = st.session_state.get("importacao_txt_itens", [])
        if itens_processados:

            total_volumes = len(itens_processados)
            obras_distintas = len(set((it["titulo"], it["editora"]) for it in itens_processados))
            valor_total_lote = sum(float(it.get("valor") or 0.0) for it in itens_processados)
            novas_cadastrar = sum(1 for it in itens_processados if not it.get("ja_no_acervo"))
            dups_encontradas = sum(1 for it in itens_processados if it.get("ja_no_acervo"))

            with st.container(border=True):
                st.markdown(f"#### 🔍 3. Revisão e Aprovação das HQs ({total_volumes} volumes identificados)")
                c_m1, c_m2, c_m3, c_m4 = st.columns(4)
                with c_m1:
                    st.metric("Total de Volumes", total_volumes)
                with c_m2:
                    st.metric("Obras Distintas", obras_distintas)
                with c_m3:
                    st.metric("Valor Total do Lote", f"R$ {valor_total_lote:.2f}")
                with c_m4:
                    st.metric("Novas a Cadastrar", novas_cadastrar, delta=f"{dups_encontradas} no acervo" if dups_encontradas > 0 else None)

                st.info(
                    "💡 **Revise e aprove antes de salvar:** Edições novas já estão marcadas para cadastro com status **'Não Lido'**. "
                    "Para séries com múltiplos volumes, o valor é registrado somente no 1º volume. "
                    "Você pode alterar qualquer campo (Título, Volume, Editora, Valor, Estado, Prateleira) diretamente na tabela abaixo.",
                    icon="✏️"
                )

                df_rev = pd.DataFrame(itens_processados)
                colunas_rev = ["incluir", "titulo", "edicao", "editora", "valor", "estado_conservacao", "prateleira", "status_acervo"]
                for c in colunas_rev:
                    if c not in df_rev.columns:
                        df_rev[c] = ""

                df_rev = df_rev[colunas_rev]

                df_rev_editado = st.data_editor(
                    df_rev,
                    use_container_width=True,
                    num_rows="dynamic",
                    column_config={
                        "incluir": st.column_config.CheckboxColumn("Cadastrar?", help="Marque para cadastrar esta HQ no catálogo", default=True),
                        "titulo": st.column_config.TextColumn("Título da HQ *", required=True, width="large"),
                        "edicao": st.column_config.TextColumn("Edição / Vol.", width="small"),
                        "editora": st.column_config.TextColumn("Editora", width="medium"),
                        "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", min_value=0.0, step=0.5),
                        "estado_conservacao": st.column_config.SelectboxColumn(
                            "Estado de Conservação",
                            options=["Excelente", "Muito Bom", "Bom", "Regular", "Ruim", "Novo / Lacrado"],
                            required=True
                        ),
                        "prateleira": st.column_config.TextColumn("Prateleira"),
                        "status_acervo": st.column_config.TextColumn("Status no Acervo", disabled=True),
                    },
                    key="editor_tabela_revisao_arquivo"
                )

                # Salvar no banco
                itens_aprovados_df = df_rev_editado[df_rev_editado["incluir"] == True]
                qtd_aprovadas = len(itens_aprovados_df)

                st.markdown("---")
                col_salv, col_desc = st.columns([2, 1.2])
                with col_salv:
                    btn_salvar_banco = st.button(
                        f"💾 4. Confirmar & Cadastrar {qtd_aprovadas} HQs no Catálogo",
                        type="primary",
                        use_container_width=True,
                        disabled=(qtd_aprovadas == 0),
                        key="btn_confirmar_salvar_arquivo_db"
                    )

                with col_desc:
                    if st.button("🗑️ Limpar / Recomeçar", use_container_width=True, key="btn_descartar_rev_arquivo"):
                        st.session_state.pop("importacao_txt_hash", None)
                        st.session_state.pop("importacao_txt_itens", None)
                        st.rerun()

                if btn_salvar_banco:
                    itens_finais_banco = []
                    for _, row in itens_aprovados_df.iterrows():
                        idx_orig = row.name if row.name in df_rev.index else None
                        item_base = itens_processados[idx_orig] if (idx_orig is not None and idx_orig < len(itens_processados)) else {}

                        item_final = {
                            "titulo": str(row.get("titulo", "")).strip(),
                            "edicao": str(row.get("edicao", "")).strip(),
                            "editora": str(row.get("editora", "")).strip(),
                            "genero": str(item_base.get("genero") or "Outro").strip(),
                            "escritor": str(item_base.get("escritor") or "Não informado").strip(),
                            "ilustrador": str(item_base.get("ilustrador") or "Não informado").strip(),
                            "prateleira": str(row.get("prateleira", "")).strip() or prat_arquivo_final,
                            "lido": "Não Lido",
                            "avaliacao": 0,
                            "valor": float(row.get("valor") or 0.0),
                            "estado_conservacao": str(row.get("estado_conservacao") or "Excelente").strip(),
                            "capa": str(item_base.get("capa") or "").strip(),
                            "resumo": str(item_base.get("resumo") or "").strip(),
                            "resenha": ""
                        }
                        itens_finais_banco.append(item_final)

                    prog_container = st.container()
                    with prog_container:
                        barra_progresso = st.progress(0, text=f"💾 Preparando gravação de {len(itens_finais_banco)} HQs...")
                        texto_status_salvamento = st.empty()

                    def callback_progresso(atual, total):
                        if total > 0:
                            percentual = min(1.0, atual / total)
                            barra_progresso.progress(percentual, text=f"💾 Gravando no banco: {atual} de {total} HQs ({int(percentual*100)}%)...")
                            texto_status_salvamento.caption(f"⚡ Inserindo em lotes: **{atual}** / **{total}** edições salvas...")

                    res_salvar = database.salvar_hqs(
                        itens=itens_finais_banco,
                        prateleira=prat_arquivo_final,
                        lido_padrao="Não Lido",
                        ignorar_duplicadas=True,
                        retornar_detalhes=True,
                        progresso_callback=callback_progresso
                    )

                    barra_progresso.empty()
                    texto_status_salvamento.empty()
                    st.session_state.pop("importacao_txt_hash", None)
                    st.session_state.pop("importacao_txt_itens", None)

                    st.balloons()
                    num_salvos = res_salvar.get("salvos", 0) if isinstance(res_salvar, dict) else res_salvar
                    num_dup = res_salvar.get("duplicados", 0) if isinstance(res_salvar, dict) else 0

                    st.success(
                        f"🎉 **Importação concluída com sucesso!** Foram cadastradas **{num_salvos} novas edições** com status 'Não Lido'."
                        + (f" ({num_dup} edições duplicadas foram ignoradas automaticamente)." if num_dup > 0 else ""),
                        icon="✅"
                    )

                    col_ir, _ = st.columns([1.5, 2])
                    with col_ir:
                        if st.button("📚 Ir para o Catálogo e Ver Inventário", type="primary", use_container_width=True, key="btn_ir_cat_pos_arquivo"):
                            voltar_ao_catalogo()
        else:
            st.warning("⚠️ Nenhuma HQ pôde ser interpretada do texto. Verifique se o formato segue `Título /Editora Valor: R$ XX,XX`.")

    st.markdown("---")
    if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_import_bottom", use_container_width=True):
        voltar_ao_catalogo()


# -------------------------------------------------------------
# PÁGINA DEDICADA: AUDITORIA E LIMPEZA DE DUPLICATAS
# -------------------------------------------------------------
def renderizar_pagina_auditoria_duplicatas():
    col_nav_t, col_nav_b = st.columns([3, 1.2])
    with col_nav_t:
        st.title("🔍 Auditoria & Limpeza de Duplicatas")
        st.markdown("Identifique e remova edições duplicadas do seu catálogo selecionando as que deseja excluir na lista abaixo.")
    with col_nav_b:
        st.write("")
        if st.button("⬅️ Voltar ao Catálogo", type="primary", use_container_width=True, key="btn_voltar_auditoria_top"):
            voltar_ao_catalogo()

    if "cache_duplicatas" not in st.session_state or st.session_state.get("cache_duplicatas") is None:
        with st.spinner("🔍 Buscando duplicatas no acervo..."):
            st.session_state["cache_duplicatas"] = database.identificar_duplicatas_no_acervo()

    grupos_dups = st.session_state.get("cache_duplicatas", [])

    if not grupos_dups:
        st.success(
            "🎉 **Excelente! Nenhuma duplicata foi encontrada no seu acervo.**\n\n"
            "Todos os títulos e volumes do catálogo estão únicos!",
            icon="✨"
        )
    else:
        # Monta lista plana para a grid simples e mapa de originais
        linhas_grid = []
        mapa_hqs_originais = {}
        for grp in grupos_dups:
            nome_grupo = f"{grp.get('titulo_base', '')} (Vol: {grp.get('edicao_base', '')})"
            tipo_desc = "🔴 Exata" if grp.get("tipo") == "Exata" else "🟡 Similar"
            for it in grp.get("hqs", []):
                h_id = int(it.get("id"))
                mapa_hqs_originais[h_id] = it
                linhas_grid.append({
                    "excluir": False,
                    "id": h_id,
                    "titulo": it.get("titulo") or "",
                    "edicao": it.get("edicao") or "",
                    "editora": it.get("editora") or "",
                    "prateleira": it.get("prateleira") or "",
                    "valor": float(it.get("valor") or 0.0),
                    "estado_conservacao": it.get("estado_conservacao") or "Excelente",
                    "lido": it.get("lido") or "Não Lido",
                    "tipo_duplicata": tipo_desc,
                    "grupo": nome_grupo
                })

        df_dups = pd.DataFrame(linhas_grid)
        total_encontradas = len(df_dups)
        total_grupos = len(grupos_dups)

        col_m1, col_m2, col_btn_rescan = st.columns([2, 2, 1.5])
        with col_m1:
            st.metric("Total de Edições Duplicadas", total_encontradas)
        with col_m2:
            st.metric("Títulos / Obras Afetadas", total_grupos)
        with col_btn_rescan:
            st.write("")
            if st.button("🔄 Recarregar Lista", use_container_width=True, key="btn_recarregar_dups"):
                st.session_state["cache_duplicatas"] = None
                st.rerun()

        st.info(
            "💡 **Instruções:** Você pode dar dois cliques em qualquer campo (**Nome**, **Volume**, **Editora**, **Prateleira**, etc.) para corrigir e clicar em **'💾 Salvar Alterações'**, ou marcar a caixa **'Excluir'** e clicar em **'🗑️ Excluir selecionadas'**.",
            icon="✏️"
        )

        df_editado = st.data_editor(
            df_dups,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=["id", "tipo_duplicata", "grupo"],
            column_config={
                "excluir": st.column_config.CheckboxColumn("Excluir", help="Marque para selecionar e excluir esta edição", default=False),
                "titulo": st.column_config.TextColumn("Nome", required=True, width="large"),
                "edicao": st.column_config.TextColumn("Volume", width="small"),
                "editora": st.column_config.TextColumn("Editora", width="medium"),
                "prateleira": st.column_config.TextColumn("Prateleira", width="medium"),
                "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", min_value=0.0, step=0.5),
                "estado_conservacao": st.column_config.SelectboxColumn("Estado", options=["Excelente", "Muito Bom", "Bom", "Regular", "Ruim", "Novo / Lacrado"], required=True, width="small"),
                "lido": st.column_config.SelectboxColumn("Status", options=["Não Lido", "Lendo", "Lido"], required=True, width="small"),
                "tipo_duplicata": st.column_config.TextColumn("Tipo", disabled=True, width="small"),
                "grupo": st.column_config.TextColumn("Grupo Duplicado", disabled=True, width="medium"),
                "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            },
            key="grid_auditoria_duplicatas"
        )

        # Detecção de edições nas linhas da tabela
        df_editado_sem_sel = df_editado.drop(columns=["excluir"], errors="ignore")
        df_dups_sem_sel = df_dups.drop(columns=["excluir"], errors="ignore")
        houve_alteracao = not df_editado_sem_sel.equals(df_dups_sem_sel)

        # Itens marcados para exclusão
        selecionados_df = df_editado[df_editado["excluir"] == True]
        qtd_selecionada = len(selecionados_df)

        st.markdown("---")
        col_act_save, col_act_del = st.columns([1.5, 1.5])
        with col_act_save:
            btn_salvar_edicoes = st.button(
                "💾 Salvar Alterações da Grid",
                type="primary" if houve_alteracao else "secondary",
                use_container_width=True,
                disabled=not houve_alteracao,
                key="btn_salvar_dups_editadas"
            )
        with col_act_del:
            texto_btn = f"🗑️ Excluir selecionadas ({qtd_selecionada})" if qtd_selecionada > 0 else "🗑️ Excluir selecionadas"
            btn_excluir = st.button(
                texto_btn,
                type="primary" if qtd_selecionada > 0 else "secondary",
                use_container_width=True,
                disabled=(qtd_selecionada == 0),
                key="btn_excluir_dups_selecionadas"
            )

        if btn_salvar_edicoes and houve_alteracao:
            with st.spinner("💾 Salvando alterações nas edições..."):
                atualizadas_count = 0
                for _, row in df_editado.iterrows():
                    hq_id = int(row["id"])
                    orig = mapa_hqs_originais.get(hq_id, {})

                    mudou = (
                        str(row.get("titulo") or "").strip() != str(orig.get("titulo") or "").strip() or
                        str(row.get("edicao") or "").strip() != str(orig.get("edicao") or "").strip() or
                        str(row.get("editora") or "").strip() != str(orig.get("editora") or "").strip() or
                        str(row.get("prateleira") or "").strip() != str(orig.get("prateleira") or "").strip() or
                        float(row.get("valor") or 0.0) != float(orig.get("valor") or 0.0) or
                        str(row.get("estado_conservacao") or "").strip() != str(orig.get("estado_conservacao") or "").strip() or
                        str(row.get("lido") or "").strip() != str(orig.get("lido") or "").strip()
                    )

                    if mudou:
                        database.atualizar_hq(
                            hq_id=hq_id,
                            titulo=str(row.get("titulo") or "").strip(),
                            edicao=str(row.get("edicao") or "").strip(),
                            editora=str(row.get("editora") or "").strip(),
                            prateleira=str(row.get("prateleira") or orig.get("prateleira") or "").strip(),
                            genero=orig.get("genero") or "Outro",
                            escritor=orig.get("escritor") or "Não informado",
                            ilustrador=orig.get("ilustrador") or "Não informado",
                            lido=str(row.get("lido") or orig.get("lido") or "Não Lido"),
                            avaliacao=int(orig.get("avaliacao") or 0),
                            valor=float(row.get("valor") or 0.0),
                            estado_conservacao=str(row.get("estado_conservacao") or orig.get("estado_conservacao") or "Excelente"),
                            capa=orig.get("capa") or "",
                            resenha=orig.get("resenha") or "",
                            resumo=orig.get("resumo") or ""
                        )
                        atualizadas_count += 1

            st.session_state["cache_duplicatas"] = None
            st.success(f"🎉 **{atualizadas_count} HQ(s) atualizada(s) com sucesso!**", icon="✅")
            st.rerun()

        if btn_excluir and qtd_selecionada > 0:
            ids_para_excluir = [int(r["id"]) for _, r in selecionados_df.iterrows()]
            with st.spinner(f"🗑️ Excluindo {len(ids_para_excluir)} edições duplicadas..."):
                excluidas_count = 0
                for h_id in ids_para_excluir:
                    if database.excluir_hq_por_id(h_id):
                        excluidas_count += 1

            st.session_state["cache_duplicatas"] = None
            st.success(f"🎉 **{excluidas_count} HQ(s) duplicada(s) excluída(s) com sucesso!**", icon="✅")
            st.rerun()

    st.markdown("---")
    if st.button("⬅️ Voltar ao Catálogo Principal", key="btn_voltar_auditoria_bottom", use_container_width=True):
        voltar_ao_catalogo()


# Controle de exibição de páginas dedicadas
if st.query_params.get("pagina") == "editar_prateleiras" or st.session_state.get("pagina_atual") == "editar_prateleiras":
    renderizar_pagina_editar_prateleiras()
    st.stop()

if st.query_params.get("pagina") == "auditoria_duplicatas" or st.session_state.get("pagina_atual") == "auditoria_duplicatas":
    renderizar_pagina_auditoria_duplicatas()
    st.stop()

if st.query_params.get("pagina") == "em_leitura" or st.session_state.get("pagina_atual") == "em_leitura":
    renderizar_pagina_em_leitura()
    st.stop()

if st.query_params.get("pagina") == "ordem_leitura" or st.session_state.get("pagina_atual") == "ordem_leitura":
    renderizar_pagina_ordem_leitura()
    st.stop()

if st.query_params.get("pagina") == "dna_colecao" or st.session_state.get("pagina_atual") == "dna_colecao":
    renderizar_pagina_dna_colecao()
    st.stop()

if st.query_params.get("pagina") == "storyteller" or st.session_state.get("pagina_atual") == "storyteller":
    renderizar_pagina_storyteller()
    st.stop()

if st.query_params.get("pagina") == "quiz_acervo" or st.session_state.get("pagina_atual") == "quiz_acervo":
    renderizar_pagina_quiz_acervo()
    st.stop()

if st.query_params.get("pagina") == "importacao_lote" or st.session_state.get("pagina_atual") == "importacao_lote":
    renderizar_pagina_importacao_lote()
    st.stop()

if st.query_params.get("pagina") == "importacao_arquivo" or st.session_state.get("pagina_atual") == "importacao_arquivo":
    renderizar_pagina_importacao_arquivo()
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
            
            col_btn_c1, col_btn_c2 = st.columns(2)
            with col_btn_c1:
                if st.button("🌐 Buscar Fonte", key="btn_buscar_fonte_dia", use_container_width=True, type="primary" if not tem_capa else "secondary", help="Busca a fonte da HQ via Google e Reserp.ai"):
                    dialog_buscar_fonte(int(hq_dia["id"]))
            with col_btn_c2:
                if st.button("🖼️ Buscar Capas", key="btn_buscar_capa_dia", use_container_width=True, help="Procurar opções de capa desta HQ na internet"):
                    dialog_buscar_capa(int(hq_dia["id"]))

            col_btn_c3, col_btn_c4 = st.columns(2)
            with col_btn_c3:
                if st.button("💰 Buscar Preço", key="btn_buscar_preco_capa_dia", use_container_width=True, help="Consultar e comparar preços online desta HQ"):
                    dialog_buscar_preco(int(hq_dia["id"]))
            with col_btn_c4:
                label_foto = "📷 Enviar Foto" if not tem_capa else "📷 Alterar Foto"
                if st.button(label_foto, key="btn_add_capa_dia", use_container_width=True, help="Tire uma foto ou faça upload da capa desta edição"):
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
            escritor_dia = str(hq_dia.get("escritor") or "").strip()
            if escritor_dia and escritor_dia.lower() not in ["não informado", "nao informado", "none", "null", "-"]:
                meta_itens.append(f"✍️ **Roteirista:** {escritor_dia}")
            else:
                meta_itens.append("✍️ **Roteirista:** `Não informado`")

            ilustrador_dia = str(hq_dia.get("ilustrador") or "").strip()
            if ilustrador_dia and ilustrador_dia.lower() not in ["não informado", "nao informado", "none", "null", "-"]:
                meta_itens.append(f"🎨 **Ilustrador:** {ilustrador_dia}")
            else:
                meta_itens.append("🎨 **Ilustrador:** `Não informado`")
            if hq_dia.get("prateleira"):
                meta_itens.append(f"📍 **Prateleira:** `{hq_dia['prateleira']}`")

            valor_dia = float(hq_dia.get("valor") or 0.0)
            if valor_dia > 0:
                meta_itens.append(f"💰 **Valor:** `R$ {valor_dia:.2f}`")
            else:
                meta_itens.append(f"💰 **Valor:** `Não informado`")

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

            if hq_dia.get("link_edicao") and str(hq_dia["link_edicao"]).startswith("http"):
                st.markdown(f"🔗 [Abrir ficha desta edição no Guia dos Quadrinhos ➔]({hq_dia['link_edicao']})")

            st.markdown("")

            col_b1, col_b2, col_b3, col_b4, col_b5, col_b6 = st.columns([1.1, 1.1, 1.3, 1.0, 1.0, 1.0])
            with col_b1:
                if st.button("🎲 Sortear Outra", key="btn_sortear_outra_dia", use_container_width=True, help="Sortear aleatoriamente outro quadrinho da sua coleção sem repetir recentes"):
                    outra_hq = database.sortear_edicao_do_dia(excluir_id=int(hq_dia["id"]), data_destaque=data_hoje)
                    if outra_hq:
                        st.session_state["edicao_do_dia_id"] = outra_hq["id"]
                        st.rerun()
            with col_b2:
                if st.button("🎙️ Storyteller", key="btn_story_dia", use_container_width=True, help="Ouvir o aquecimento narrativo desta edição com narração por voz de IA"):
                    st.session_state["storyteller_hq_id"] = int(hq_dia["id"])
                    st.session_state["pagina_atual"] = "storyteller"
                    st.rerun()
            with col_b3:
                is_lido = str(hq_dia.get("lido", "")).strip().lower() == "lido"
                btn_lido_label = "📖 Marcar Não Lido" if is_lido else "✅ Marcar como Lido"
                btn_lido_help = "Alterar status para Não Lido" if is_lido else "Marcar este quadrinho como Lido na coleção"
                if st.button(btn_lido_label, key="btn_marcar_lido_dia", use_container_width=True, help=btn_lido_help):
                    novo_status_dia = "Não Lido" if is_lido else "Lido"
                    database.definir_status_leitura(int(hq_dia["id"]), novo_status_dia)
                    st.toast(f"Status atualizado para '{novo_status_dia}'!", icon="✅" if novo_status_dia == "Lido" else "📖")
                    st.rerun()
            with col_b4:
                if st.button("⭐ Avaliar HQ", key="btn_avaliar_hq_dia", use_container_width=True, help="Dar uma nota de 1 a 5 estrelas para esta HQ"):
                    dialog_avaliar_hq(int(hq_dia["id"]))
            with col_b5:
                if st.button("✏️ Editar HQ", key="btn_editar_hq_dia", use_container_width=True, help="Editar informações desta HQ"):
                    dialog_editar_hq(int(hq_dia["id"]))
            with col_b6:
                if st.button("🗑️ Excluir HQ", key="btn_excluir_hq_dia", use_container_width=True, help="Excluir este quadrinho da coleção"):
                    dialog_excluir_hq(int(hq_dia["id"]))
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
    st.markdown(
        """
        <style>
        /* Melhora a legibilidade e evita cortes nos menus suspensos de filtros */
        div[data-baseweb="select"] {
            min-width: 100% !important;
        }
        div[data-baseweb="select"] div {
            white-space: normal !important;
            text-overflow: unset !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Linha 1 de Filtros: Busca e Ordenação
    col_filtro_busca, col_filtro_ordem = st.columns([2.5, 1.2])
    with col_filtro_busca:
        busca_texto = st.text_input("🔍 Buscar por título, autor, editora, gênero ou edição:", placeholder="Digite para filtrar...")
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

    # Linha 2 de Filtros: Prateleira, Editora, Gênero, Status e Avaliação
    col_filtro_prat, col_filtro_edit, col_filtro_gen, col_filtro_leitura, col_filtro_aval = st.columns([1.8, 1.4, 1.2, 1.1, 1.1])

    with col_filtro_prat:
        lista_prateleiras = ["Todas"] + database.obter_prateleiras()
        prateleira_selecionada = st.selectbox("📍 Filtrar por Prateleira:", lista_prateleiras)

    with col_filtro_edit:
        lista_editoras = ["Todas"] + database.obter_editoras()
        editora_selecionada = st.selectbox("🏢 Filtrar por Editora:", lista_editoras)

    with col_filtro_gen:
        lista_generos = ["Todos"] + database.obter_generos()
        genero_selecionado = st.selectbox("🏷️ Filtrar por Gênero:", lista_generos)

    with col_filtro_leitura:
        leitura_selecionada = st.selectbox("📖 Status de Leitura:", ["Todos", "Não Lido", "Lendo", "Lido"])

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
        aval_selecionada = st.selectbox("⭐ Avaliação:", list(opcoes_aval.keys()))
        aval_filtro_val = opcoes_aval[aval_selecionada]

    df_hqs = database.listar_todas_hqs(
        busca=busca_texto,
        prateleira_filtro=prateleira_selecionada,
        editora_filtro=editora_selecionada,
        genero_filtro=genero_selecionado,
        status_leitura_filtro=leitura_selecionada,
        avaliacao_filtro=aval_filtro_val,
        ordem_por=ordem_val
    )

    if not df_hqs.empty:
        col_grid_info, col_grid_select_all = st.columns([3.2, 1.3])
        with col_grid_info:
            st.write(f"Exibindo **{len(df_hqs)}** quadrinho(s) cadastrado(s) ordenados por **{ordem_selecionada}**: *(Marque o CheckBox para ações em massa ou dê 2 cliques para editar)*")
        with col_grid_select_all:
            def on_toggle_selecionar_todos():
                if "tabela_inventario_editavel" in st.session_state:
                    del st.session_state["tabela_inventario_editavel"]

            selecionar_todos = st.checkbox(
                "☑️ Selecionar Todos",
                key="chk_selecionar_todos_grid",
                on_change=on_toggle_selecionar_todos,
                help="Marcar ou desmarcar todas as HQs listadas na grid atual para ações em lote"
            )

        # Insere coluna de seleção para ações em massa
        df_hqs_display = df_hqs.copy()
        df_hqs_display.insert(0, "selecionar", bool(selecionar_todos))

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
                "valor": st.column_config.NumberColumn(
                    "Valor (R$)",
                    help="Valor da HQ em Reais (R$)",
                    min_value=0.0,
                    step=0.5,
                    format="R$ %.2f"
                ),
                "estado_conservacao": st.column_config.SelectboxColumn(
                    "Estado de Conservação",
                    help="Estado de conservação da HQ",
                    options=["Excelente", "Muito Bom", "Bom", "Regular", "Ruim", "Novo / Lacrado"],
                    required=True
                ),
                "lido": st.column_config.SelectboxColumn(
                    "Status de Leitura",
                    help="Status de leitura da edição",
                    options=["Não Lido", "Lendo", "Lido"],
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
                col_blk_lido, col_blk_lendo, col_blk_nlido, col_blk_del, col_blk_clear = st.columns([1.5, 1.5, 1.5, 1.5, 1])
                with col_blk_lido:
                    if st.button("📖 Marcar como 'Lido'", type="primary", use_container_width=True, key="btn_bulk_set_lido"):
                        qtd_alt = database.atualizar_status_leitura_em_massa(ids_selecionados, "Lido")
                        st.success(f"🎉 **{qtd_alt} HQ(s)** marcada(s) como **Lido** com sucesso!")
                        st.rerun()
                with col_blk_lendo:
                    if st.button("📚 Marcar como 'Lendo'", type="primary", use_container_width=True, key="btn_bulk_set_lendo"):
                        qtd_alt = database.atualizar_status_leitura_em_massa(ids_selecionados, "Lendo")
                        st.success(f"🎉 **{qtd_alt} HQ(s)** marcada(s) como **Lendo** com sucesso!")
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
                        if "chk_selecionar_todos_grid" in st.session_state:
                            st.session_state["chk_selecionar_todos_grid"] = False
                        if "tabela_inventario_editavel" in st.session_state:
                            del st.session_state["tabela_inventario_editavel"]
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
                        campos = ["titulo", "edicao", "editora", "genero", "escritor", "ilustrador", "prateleira", "lido", "avaliacao", "valor", "estado_conservacao", "capa", "resenha", "resumo"]
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
                                valor=float(row_editada.get("valor") or 0.0),
                                estado_conservacao=str(row_editada.get("estado_conservacao") or "Excelente"),
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
                                    st.image(obter_imagem_capa(thumb_url), width="stretch")
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


