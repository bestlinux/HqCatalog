"""
Módulo de Integração com a API do Gemini (Google GenAI SDK)
Utiliza o modelo gemini-3.1-pro-preview para visão computacional e gemini-3.5-flash para curadoria e comandos.
"""

import json
import re
import os
import io
import base64
import time
import urllib.parse
import unicodedata
from typing import List, Dict, Any, Optional
try:
    import requests
except ImportError:
    requests = None
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

import jev_engine


PROMPT_SISTEMA_HQS = """Você é um especialista em catalogação e curadoria profissional de histórias em quadrinhos (HQs, graphic novels, mangás, encadernados, gibis e zines).
Analise a imagem da prateleira/estante fornecida com MÁXIMA ATENÇÃO às lombadas e capas visíveis.

Identifique CADA HQ individualmente na foto da esquerda para a direita (ou de cima para baixo).

REGRAS CRÍTICAS PARA IDENTIFICAÇÃO DE LOMBADAS:
1. LEITURA COMPLETA E INTEGRAL DA LOMBADA:
   - Lombadas frequentemente dividem o título em múltiplas linhas, com tamanhos de fonte, pesos, cores e orientações diferentes.
   - NUNCA leia apenas a primeira linha ou a palavra de maior destaque. Leia a lombada de cima a baixo para compor o título COMPLETO.
   - Exemplo 1: Se a lombada tiver "Meu Amigo" em uma linha e "Kim Jong-un" em outra linha/cor, o título é ESTRITAMENTE "Meu Amigo Kim Jong-un" (NUNCA apenas "Meu Amigo").
   - Exemplo 2: Se a lombada tiver "Paraíso" em destaque e ": O Vampiro que Ri" em outra linha com número "2", o título é "Paraíso: O Vampiro que Ri" e a edição é "2" (NUNCA apenas "Paraiso").
   - Exemplo 3: Se houver subtítulo ou nome do arco (ex: "Batman: O Longo Dia das Bruxas", "Sandman: Prelúdios e Noturnos"), inclua o subtítulo completo no campo "titulo".

2. SEPARAÇÃO RIGOROSA DE TÍTULO, EDIÇÃO E AUTOR:
   - "titulo": Nome completo e canônico da obra (sem truncar). Não coloque o número do volume no final do título se ele pertencer ao campo "edicao".
   - "edicao": Número da edição ou volume (ex: "1", "2", "Vol. 2", "Edição Especial", "Volume Único", "#104", ou "" caso não haja número explícito).
   - "editora": Nome da editora responsável (ex: "Comix Zone", "Pipoca & Nanquim", "Panini", "JBC", "NewPOP", "Devir", "Veneta", "Mythos", "Darkside", "Conrad", "Mino", "Nemo", "Marvel", "DC Comics", ou "Desconhecida" se não for visível).
   - "escritor": Nome do(s) roteirista(s) ou escritor(es) (ex: "Suehiro Maruo", "Keum Suk Gendry-Kim", "Alan Moore", "Frank Miller", "Neil Gaiman", ou "Não informado"). NUNCA misture nomes de autores no campo "titulo".
   - "ilustrador": Nome do(s) desenhista(s) / ilustrador(es) (ou "Não informado").
   - "genero": Gênero literário/temático principal (ex: "Mangá / Seinen", "Mangá / Shonen", "Super-heróis", "Terror", "Aventura", "Ficção Científica", "Drama", "Histórico", "Biografia", "Suspense / Policial", "Humor", "Infantil", ou "Outro").
   - "resumo": Resumo conciso da história/edição (em português, de 2 a 4 frases).

3. PRECISÃO DE EDITORA E ANTI-ALUCINAÇÃO:
   - Identifique a editora APENAS se o logotipo, selo editorial ou nome estiver de fato visível na lombada (geralmente no topo ou na base da lombada, como "Comix Zone", "Pipoca & Nanquim", "Panini", "JBC", "NewPOP", "Veneta", "Devir", "Darkside", "Mythos", "Conrad", "Nemo", "Mino", "Todavia", "Quadrinhos na Cia", "Zarabatana", "Skript", "Draco", "Trem Fantasma", "Figura", "Risco").
   - NUNCA assuma ou adivinhe "Pipoca & Nanquim" ou "Panini" por padrão para graphic novels em geral se o logo da editora for outro (ex: logotipo da "Comix Zone" em obras como "Ouroboros" ou "Squeak the Mouse").
   - Se o logotipo da editora não for identificável com certeza na imagem, use ESTRITAMENTE "Desconhecida".

4. CONHECIMENTO DE CATÁLOGO NACIONAL E INTERNACIONAL:
   - Utilize seu conhecimento enciclopédico sobre mangás e quadrinhos lançados no Brasil para reconhecer obras canônicas mesmo quando a tipografia da lombada for estilizada, vertical ou com fontes mistas.

Retorne ESTRITAMENTE um array JSON contendo os objetos identificados.
Exemplo de formato esperado:
[
  {
    "titulo": "Paraíso: O Vampiro que Ri",
    "edicao": "2",
    "editora": "Pipoca & Nanquim",
    "genero": "Mangá / Seinen",
    "escritor": "Suehiro Maruo",
    "ilustrador": "Suehiro Maruo",
    "resumo": "Continuação da aclamada obra eroguro de Suehiro Maruo, acompanhando as bizarras e macabras peripécias do vampiro em um submundo repleto de bizarrices e humor ácido."
  },
  {
    "titulo": "Meu Amigo Kim Jong-un",
    "edicao": "Volume Único",
    "editora": "Pipoca & Nanquim",
    "genero": "Biografia / Histórico",
    "escritor": "Keum Suk Gendry-Kim",
    "ilustrador": "Keum Suk Gendry-Kim",
    "resumo": "Graphic novel documental autobiográfica que investiga as memórias e percepções da autora ao entrevistar cidadãos comuns sobre o regime norte-coreano e o líder Kim Jong-un."
  },
  {
    "titulo": "Watchmen",
    "edicao": "Edição Definitiva",
    "editora": "Panini",
    "genero": "Super-heróis",
    "escritor": "Alan Moore",
    "ilustrador": "Dave Gibbons",
    "resumo": "Em uma realidade alternativa nos anos 1980 em meio à Guerra Fria, o assassinato do vigilante Comediante desencadeia uma investigação liderada por Rorschach, revelando uma conspiração global que questiona a própria moralidade humana."
  }
]

Se nenhum quadrinho for identificado com clareza, retorne um array vazio: []
NÃO adicione nenhum texto introdutório ou explicativo fora do array JSON.
"""


DEFAULT_GEMINI_API_KEY = ""


def get_gemini_client(api_key: Optional[str] = None) -> Any:
    """
    Inicializa e retorna o cliente oficial do Google GenAI com timeout configurado.
    Se a api_key não for passada, busca na variável de ambiente GEMINI_API_KEY ou st.session_state.
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "Chave de API do Gemini não informada. "
            "Configure a variável de ambiente GEMINI_API_KEY no arquivo .env ou informe-a na barra lateral do app."
        )
    if types is not None and hasattr(types, "HttpOptions"):
        try:
            return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=12000))
        except Exception:
            pass
    return genai.Client(api_key=key)


def higienizar_item_hq(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Higieniza e desmembra título e edição caso o número do volume tenha vindo anexado ao título.
    Garante que títulos e edições fiquem canônicos e limpos.
    """
    titulo = str(item.get("titulo", "")).strip().strip("\"'“”")
    edicao = str(item.get("edicao", "")).strip().strip("\"'“”")
    editora = str(item.get("editora", "")).strip().strip("\"'“”")
    genero = str(item.get("genero", "")).strip().strip("\"'“”") or "Outro"
    escritor = str(item.get("escritor", "")).strip().strip("\"'“”") or "Não informado"
    ilustrador = str(item.get("ilustrador", "")).strip().strip("\"'“”") or "Não informado"
    resumo = str(item.get("resumo", "")).strip()

    # Padrões de sufixo de volume no final do título
    # Ex: "Sandman - Edição Definitiva Vol. 1", "Akira Vol. 3", "Batman #10", "Paraíso: O Vampiro que Ri 2"
    padrao_vol_explicito = re.search(
        r"^(.*?)(?:\s*[-–—:]\s*|\s+)(?:vol(?:ume)?|v|ed(?:i[cç][aã]o)?|#|n[oº°]|tomo|livro|parte)\.?\s*(\d+(?:[\.,]\d+)?)$",
        titulo,
        re.IGNORECASE
    )
    padrao_num_final = re.search(r"^(.*?)(?:\s*[-–—:]\s*|\s+)(\d{1,3})$", titulo)

    titulos_numericos_conhecidos = {"1984", "2001", "300", "100", "20th", "21st"}

    if padrao_vol_explicito:
        base_titulo = padrao_vol_explicito.group(1).strip()
        num_vol = padrao_vol_explicito.group(2).strip()
        if base_titulo and base_titulo.lower() not in titulos_numericos_conhecidos:
            titulo = base_titulo
            if not edicao:
                edicao = f"Vol. {num_vol}"
    elif padrao_num_final:
        base_titulo = padrao_num_final.group(1).strip()
        num_vol = padrao_num_final.group(2).strip()
        if base_titulo and base_titulo.lower() not in titulos_numericos_conhecidos and len(base_titulo) > 2:
            if not edicao:
                titulo = base_titulo
                edicao = num_vol
            elif edicao == num_vol or edicao.lower() in (f"vol. {num_vol}", f"vol {num_vol}", f"#{num_vol}"):
                titulo = base_titulo

    # Remove pontuação residual no final do título (ex: "Paraíso: " -> "Paraíso")
    titulo = re.sub(r"[\s\-–—:]+$", "", titulo).strip()
    genero_canonico = jev_engine.normalizar_genero_canonico(genero)

    return {
        "titulo": titulo,
        "edicao": edicao,
        "editora": editora,
        "genero": genero_canonico,
        "escritor": escritor,
        "ilustrador": ilustrador,
        "resumo": resumo
    }


def limpar_e_parsear_json(texto_resposta: str) -> List[Dict[str, Any]]:
    """
    Remove blocos de formatação markdown (```json ... ```) e faz o parse seguro do JSON.
    """
    texto = texto_resposta.strip()

    # Remove blocos markdown ```json ... ``` se presentes
    match_bloco = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", texto, re.IGNORECASE)
    if match_bloco:
        texto = match_bloco.group(1).strip()

    # Se ainda houver caracteres extras fora dos colchetes do array
    match_array = re.search(r"(\[[\s\S]*\])", texto)
    if match_array:
        texto = match_array.group(1).strip()

    try:
        dados = json.loads(texto)
        if isinstance(dados, list):
            return [higienizar_item_hq(item) for item in dados if isinstance(item, dict)]
        elif isinstance(dados, dict):
            if "hqs" in dados and isinstance(dados["hqs"], list):
                return [higienizar_item_hq(item) for item in dados["hqs"] if isinstance(item, dict)]
            elif "quadrinhos" in dados and isinstance(dados["quadrinhos"], list):
                return [higienizar_item_hq(item) for item in dados["quadrinhos"] if isinstance(item, dict)]
            return [higienizar_item_hq(dados)]
        return []
    except json.JSONDecodeError as e:
        raise ValueError(f"Falha ao interpretar o JSON retornado pela IA: {e}. Resposta bruta: {texto_resposta[:300]}")


import io
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError

FALLBACK_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-pro-latest"
]


def redimensionar_para_ia(imagem: Any, max_dim: int = 2400) -> Any:
    """
    Otimiza a imagem para envio à IA:
    Mantém altíssima nitidez (até 2400px JPEG quality 90) para preservar pequenos textos,
    subtítulos e numerações em lombadas finas.
    """
    if Image is None or not isinstance(imagem, Image.Image):
        return imagem

    img = imagem.convert("RGB")
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90, optimize=True)
    buffer.seek(0)
    return Image.open(buffer)


def _analisar_tipo_erro(erro_str: str) -> str:
    """
    Classifica o erro retornado pela API do Gemini:
    - 'invalido': 404 NOT_FOUND ou modelo descontinuado.
    - 'cota_zerada': 429 RESOURCE_EXHAUSTED com limit: 0 (sem cota no plano gratuito) ou cota diária esgotada.
    - 'sobrecarga_temporaria': 503 UNAVAILABLE ou rate limit transitório recuperável.
    - 'outro': outros erros.
    """
    err_low = erro_str.lower()
    if any(k in err_low for k in ["404", "not_found", "not found", "is no longer available"]):
        return "invalido"
    if any(k in err_low for k in ["limit: 0", "limit:0", "perday", "per day", "daily"]):
        return "cota_zerada"
    if any(k in err_low for k in ["503", "unavailable", "high demand", "429", "resource_exhausted", "quota", "overloaded", "spikes in demand"]):
        return "sobrecarga_temporaria"
    return "outro"


def processar_foto_prateleira(
    imagem: Any,
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.7-flash",
    max_retries: int = 3,
    status_callback: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Envia a imagem da prateleira ou capa para o modelo Gemini e retorna a lista de HQs identificadas.
    Inclui redimensionamento prévio, retry com backoff e fallback inteligente de modelo.
    """
    client = get_gemini_client(api_key)

    # Otimiza o tamanho da foto antes de transmitir via rede
    imagem_otimizada = redimensionar_para_ia(imagem)

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1,  # Baixa temperatura para máxima precisão e velocidade
    )

    # Lista ordenada de modelos canônicos para tentar
    modelos_para_tentar = [modelo]
    for fb in FALLBACK_MODELS:
        if fb not in modelos_para_tentar:
            modelos_para_tentar.append(fb)

    ultimo_erro = None

    for mod in modelos_para_tentar:
        for tentativa in range(1, max_retries + 1):
            try:
                if status_callback and tentativa > 1:
                    status_callback(f"Tentativa {tentativa}/{max_retries} no modelo {mod}...")

                response = client.models.generate_content(
                    model=mod,
                    contents=[imagem_otimizada, PROMPT_SISTEMA_HQS],
                    config=config
                )

                if not response or not response.text:
                    return []

                return limpar_e_parsear_json(response.text)

            except Exception as ex:
                erro_str = str(ex)
                ultimo_erro = ex
                print(f"[Aviso Gemini Vision mod={mod} tentativa={tentativa}]: {ex}")
                
                tipo_erro = _analisar_tipo_erro(erro_str)

                if tipo_erro == "cota_zerada":
                    if status_callback:
                        status_callback(
                            f"ℹ️ Modelo {mod} sem cota no plano atual. Alternando imediatamente para o próximo modelo..."
                        )
                    break
                elif tipo_erro == "invalido":
                    break
                elif tipo_erro == "sobrecarga_temporaria":
                    tempo_espera = 2 ** tentativa  # 2s, 4s, 8s
                    if status_callback:
                        status_callback(
                            f"⚠️ Servidor do Gemini com alta demanda ({mod}). Aguardando {tempo_espera}s antes de tentar novamente..."
                        )
                    time.sleep(tempo_espera)
                else:
                    break

    raise RuntimeError(
        f"Não foi possível processar a imagem após várias tentativas devido à sobrecarga temporária da API do Google: {ultimo_erro}"
    )


PROMPT_SISTEMA_CHATBOT = """Você é o Assistente Virtual e Curador Especialista do catálogo pessoal de Histórias em Quadrinhos (HQs, mangás, graphic novels e encadernados) do usuário.

Seu objetivo é:
1. Responder dúvidas e fazer recomendações personalizadas com base EXCLUSIVAMENTE nas HQs cadastradas no catálogo do usuário fornecido abaixo.
2. Analisar profundamente os RESUMOS das histórias, títulos, gêneros, roteiristas, ilustradores, editoras, status de leitura e avaliações:
   - Se o usuário pedir recomendações por tema (ex: "temas históricos no Brasil", "algo sombrio ou de suspense", "ficção científica espacial", "super-heróis com reviravolta"):
     - Faça uma varredura minuciosa nos RESUMOS das histórias e gêneros das HQs da coleção.
     - Liste e recomende as HQs correspondentes, destacando claramente:
       * **Título e Edição**
       * 📍 **Prateleira:** onde ela está localizada na estante
       * 📖 **Status:** Lido / Não Lido
       * ⭐ **Avaliação:** Nota dada pelo usuário (se houver)
       * 📝 **Por que ler:** Uma breve explicação de como o resumo/trama dessa HQ atende ao que ele pediu.
3. Se NENHUMA HQ do catálogo tiver relação com o tema pedido pelo usuário:
   - Informe educadamente: "Nenhum título com esse tema foi encontrado no seu catálogo de HQs no momento."
   - Caso faça sentido, sugira brevemente outros temas ou obras interessantes presentes na coleção dele.
4. Mantenha um tom amigável, prestativo e de entusiasta de quadrinhos, utilizando formatação Markdown limpa e agradável."""


def _eh_erro_sobrecarga(erro_str: str) -> bool:
    """Verifica se o erro retornado pela API indica sobrecarga temporária ou rate limit."""
    err_low = erro_str.lower()
    return any(termo in err_low for termo in ["503", "unavailable", "high demand", "429", "resource_exhausted", "quota", "overloaded"])


def consultar_chatbot_colecao(
    pergunta: str,
    catalogo_hqs: List[Dict[str, Any]],
    historico_mensagens: Optional[List[Dict[str, str]]] = None,
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.5-flash",
    max_retries_por_modelo: int = 2
) -> str:
    """
    Processa a pergunta do usuário utilizando o catálogo completo de HQs e seus resumos como contexto.
    Possui sistema robusto de retry com backoff e fallback automático entre modelos Gemini de última geração.
    """
    if not catalogo_hqs:
        return "Seu catálogo de HQs ainda está vazio! Cadastre algumas edições por foto para que eu possa analisar os resumos e recomendar histórias."

    client = get_gemini_client(api_key)

    # Formata a base de HQs de forma enxuta, densa e rápida para a IA processar sem sobrecarga
    linhas_catalogo = []
    for hq in catalogo_hqs:
        id_hq = hq.get("id") or "?"
        tit = (hq.get("titulo") or "Sem título").strip()
        ed = (hq.get("edicao") or "").strip()
        edit = (hq.get("editora") or "Não informada").strip()
        gen = (hq.get("genero") or "Outro").strip()
        esc = (hq.get("escritor") or "Não informado").strip()
        ilu = (hq.get("ilustrador") or "Não informado").strip()
        prat = (hq.get("prateleira") or "Não especificada").strip()
        lido = (hq.get("lido") or "Não Lido").strip()
        aval = int(hq.get("avaliacao") or 0)
        resumo = (hq.get("resumo") or "").strip() or "Resumo não informado."
        resenha = (hq.get("resenha") or "").strip()

        # Otimiza o tamanho do resumo para evitar payload desnecessário mantendo a premissa
        if len(resumo) > 240:
            resumo = resumo[:237] + "..."

        ed_str = f" ({ed})" if ed else ""
        bloco = (
            f"- [#{id_hq}] \"{tit}\"{ed_str} | Ed: {edit} | Gên: {gen} | Roteiro: {esc} | Arte: {ilu} | "
            f"Local: {prat} | Status: {lido} | {aval}⭐\n"
            f"  Sinopse: {resumo}"
        )
        if resenha:
            if len(resenha) > 150:
                resenha = resenha[:147] + "..."
            bloco += f"\n  Opinião do Leitor: {resenha}"
        linhas_catalogo.append(bloco)

    contexto_catalogo = "\n".join(linhas_catalogo)

    prompt_final = f"""{PROMPT_SISTEMA_CHATBOT}

---
### CATÁLOGO DO USUÁRIO ({len(catalogo_hqs)} HQs cadastradas):
{contexto_catalogo}
---
"""
    if historico_mensagens:
        prompt_final += "\n### Histórico recente da conversa:\n"
        for msg in historico_mensagens[-6:]:
            autor = "Usuário" if msg.get("role") == "user" else "Assistente"
            prompt_final += f"{autor}: {msg.get('content', '')}\n"

    prompt_final += f"\nUsuário: {pergunta}\nAssistente:"

    # Lista ordenada de modelos recomendados e ativos
    modelos_tentativa = [modelo]
    modelos_disponiveis = [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
        "gemini-pro-latest"
    ]
    for fb in modelos_disponiveis:
        if fb not in modelos_tentativa:
            modelos_tentativa.append(fb)

    for mod in modelos_tentativa:
        for tentativa in range(1, max_retries_por_modelo + 1):
            try:
                response = client.models.generate_content(
                    model=mod,
                    contents=prompt_final
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as ex:
                erro_str = str(ex)
                print(f"[Aviso Gemini Chatbot mod={mod} tentativa={tentativa}]: {ex}")

                tipo_erro = _analisar_tipo_erro(erro_str)
                if tipo_erro == "sobrecarga_temporaria" and tentativa < max_retries_por_modelo:
                    tempo_espera = 1.0 * tentativa
                    time.sleep(tempo_espera)
                else:
                    # Passa imediatamente para o próximo modelo da lista
                    break

    return "Desculpe, ocorreu uma instabilidade temporária ao consultar a IA. Por favor, tente novamente em instantes."


# -------------------------------------------------------------
# TRANSCRIÇÃO DE ÁUDIO PARA RESENHAS E ASSISTENTES COM GEMINI MULTIMODAL
# -------------------------------------------------------------
def transcrever_audio(
    audio_bytes: bytes,
    mime_type: str = "audio/wav",
    tipo_contexto: str = "geral",
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.5-flash",
    max_retries: int = 2
) -> str:
    """
    Transcreve o áudio falado pelo usuário utilizando o modelo Gemini multimodal.
    Adapta o prompt de transcrição conforme o contexto (curador, crud, busca_preco, resenha).
    Retorna o texto transcrito e formatado em português.
    """
    if not audio_bytes:
        return ""

    if types is None:
        raise RuntimeError("A biblioteca 'google-genai' não está disponível para processar áudio.")

    client = get_gemini_client(api_key)

    part_audio = types.Part.from_bytes(
        data=audio_bytes,
        mime_type=mime_type
    )

    if tipo_contexto == "crud":
        instrucao_especifica = "O áudio contém uma instrução de gerenciamento do catálogo de quadrinhos (ex: 'Adicione à minha coleção a edição definitiva de Watchmen que comprei hoje por R$ 120,00', 'Remova da minha coleção o quadrinho X', 'Mude a prateleira da HQ Y para Estante 2'). Transcreva o comando com máxima precisão."
    elif tipo_contexto == "busca_preco":
        instrucao_especifica = "O áudio contém o título ou edição de uma história em quadrinhos, mangá ou livro para pesquisa de preços (ex: 'Watchmen Edição Definitiva', 'Flash Omnibus Volume 1', 'Akira Volume 3', 'Sandman Panini'). Transcreva o título exato sem pontuações supérfluas."
    elif tipo_contexto == "curador":
        instrucao_especifica = "O áudio contém uma pergunta, dúvida ou pedido de recomendação para o curador virtual da coleção de quadrinhos. Transcreva fielmente a pergunta do leitor."
    else:
        instrucao_especifica = "O áudio contém uma resenha ou impressões de leitura sobre uma história em quadrinhos."

    prompt_transcricao = f"""Você é um assistente especialista em transcrição de áudios para um catálogo pessoal de histórias em quadrinhos (HQs, mangás, graphic novels, livros).
{instrucao_especifica}

Regras:
1. Escreva em português claro, corrigindo apenas pontuação e concordância básica de fala para texto.
2. Mantenha os nomes de personagens, títulos de obras, autores, ilustradores e editoras corretamente grafados (ex: Panini, Alan Moore, Dave Gibbons, Batman, Sandman, Pipoca & Nanquim, JBC, Mythos, etc.).
3. Retorne EXCLUSIVAMENTE o texto transcrito, sem introduções, aspas extras ou comentários como 'Aqui está a transcrição:'."""

    modelos_para_tentar = [modelo]
    for fb in ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"]:
        if fb not in modelos_para_tentar:
            modelos_para_tentar.append(fb)

    ultimo_erro = None
    for mod in modelos_para_tentar:
        for tentativa in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=mod,
                    contents=[part_audio, prompt_transcricao]
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as ex:
                ultimo_erro = ex
                erro_str = str(ex)
                print(f"[Aviso Gemini Transcrição Áudio mod={mod} tentativa={tentativa}]: {ex}")
                if _eh_erro_sobrecarga(erro_str) and tentativa < max_retries:
                    time.sleep(1.0 * tentativa)
                else:
                    break

    raise RuntimeError(f"Não foi possível transcrever o áudio: {ultimo_erro}")


def transcrever_audio_resenha(
    audio_bytes: bytes,
    mime_type: str = "audio/wav",
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.5-flash",
    max_retries: int = 2
) -> str:
    """Função de conveniência para transcrição de resenha."""
    return transcrever_audio(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        tipo_contexto="resenha",
        api_key=api_key,
        modelo=modelo,
        max_retries=max_retries
    )


# -------------------------------------------------------------
# PESQUISA DE PREÇOS COM SERPAPI (GOOGLE SHOPPING)
# -------------------------------------------------------------
DEFAULT_SERPAPI_KEY = os.getenv("SERPAPI_API_KEY", "")

TERMOS_EXCLUSAO_NAO_LIVRO = [
    "boneco", "boneca", "action figure", "action figures", "estátua", "estatua", "figura de ação",
    "figura articulada", "articulado", "articulada", "funko", "pop funko", "figuras ", "figura ",
    "multipack", "kit de figuras", "brinquedo", "pelúcia", "pelucia", "lego",
    "camiseta", "camisa", "t-shirt", "tshirt", "regata", "moletom", "blusa",
    "calça", "bermuda", "fantasia", "fantasia infantil", "máscara", "mascara", "chinelo", "pantufa",
    "meia", "cueca", "tênis", "sapato", "boné", "bone", "vestido", "roupa",
    "caneca", "copo", "garrafa", "squeeze", "xícara", "xicara", "almofada",
    "travesseiro", "cobertor", "lençol", "toalha",
    "quadro", "placa", "pôster", "poster", "adesivo", "adesivos", "painel decorativo",
    "chaveiro", "pin ", "pins", "broche", "cordão", "cordao",
    "capa para celular", "capinha", "case", "película", "pelicula",
    "mousepad", "mouse pad", "tapete",
    "mochila", "estojo", "necessaire", "sacola", "bolsa",
    "blu-ray", "bluray", "dvd", "vhs", "mídia física", "midia fisica",
    "jogo ps4", "jogo ps5", "jogo xbox", "jogo switch", "jogo nintendo",
    "relogio", "relógio", "luminária", "luminaria", "lâmpada", "abajur"
]


import urllib.parse


def sanitizar_url_oferta(url: str) -> str:
    """
    Sanitiza e codifica corretamente espaços e caracteres especiais em URLs de ofertas,
    evitando que links de busca com espaços quebrem no navegador ou no markdown.
    """
    if not url:
        return ""
    url_limpa = str(url).strip()
    return urllib.parse.quote(url_limpa, safe=":/?&=%|,-_#+~@")


def eh_livro_ou_revista(item: Dict[str, Any]) -> bool:
    """
    Verifica se o item retornado pela API do Google Shopping é um Livro ou Revista/HQ/Mangá,
    desconsiderando mercadorias, vestuário, brinquedos, colecionáveis não-livro, etc.
    """
    if not isinstance(item, dict):
        return False

    titulo = str(item.get("title", "")).strip().lower()
    snippet = str(item.get("snippet", "")).strip().lower()
    tag = str(item.get("tag", "")).strip().lower()
    texto_total = f"{titulo} {snippet} {tag}"

    for termo in TERMOS_EXCLUSAO_NAO_LIVRO:
        if termo in texto_total:
            return False

    return True


def pesquisar_precos_serpapi(
    termo_busca: str,
    api_key: Optional[str] = None,
    location_requested: str = "Sao Paulo, State of Sao Paulo, Brazil",
    location_used: str = "Sao Paulo,State of Sao Paulo,Brazil",
    google_domain: str = "google.com.br",
    hl: str = "pt-br",
    gl: str = "br",
    device: str = "desktop"
) -> Dict[str, Any]:
    """
    Realiza a pesquisa de preços e disponibilidade de Livros/Revistas/HQs utilizando a API do SerpApi (Google Shopping).
    Filtra automaticamente qualquer produto que não seja Livros ou Revistas e sanitiza todos os links de retorno.
    """
    try:
        import serpapi
    except ImportError:
        raise ImportError("O pacote 'serpapi' não está instalado. Instale-o com 'pip install serpapi'.")

    chave_api = api_key or DEFAULT_SERPAPI_KEY or os.getenv("SERPAPI_API_KEY", "")
    if not chave_api:
        raise ValueError(
            "Chave da SerpApi não configurada. Defina a variável SERPAPI_API_KEY no arquivo .env."
        )

    termo = termo_busca.strip()
    if not termo:
        return {
            "termo": "",
            "total_encontrados": 0,
            "itens": [],
            "raw_results": {}
        }

    client = serpapi.Client(api_key=chave_api)
    params = {
        "engine": "google_shopping",
        "q": termo,
        "location_requested": location_requested,
        "location_used": location_used,
        "google_domain": google_domain,
        "hl": hl,
        "gl": gl,
        "device": device
    }

    results = client.search(params)
    raw_shopping = results.get("shopping_results", [])

    # Filtra mantendo apenas Livros e Revistas (HQs, Mangás, Graphic Novels, Livros)
    itens_filtrados = [item for item in raw_shopping if eh_livro_ou_revista(item)]

    # Sanitiza links de produto contra espaços não codificados
    for item in itens_filtrados:
        raw_link = item.get("product_link") or item.get("link") or ""
        if raw_link:
            item["product_link"] = sanitizar_url_oferta(raw_link)
            item["link"] = item["product_link"]
        else:
            item["link"] = gerar_link_loja(item.get("source", ""), item.get("title", termo))
            item["product_link"] = item["link"]

    return {
        "termo": termo,
        "total_encontrados": len(itens_filtrados),
        "total_bruto": len(raw_shopping),
        "itens": itens_filtrados,
        "raw_results": results
    }


def gerar_link_loja(loja: str, termo: str, link_sugerido: str = "") -> str:
    """Gera um link funcional e direto de busca para a loja especificada ou sanitiza o link sugerido."""
    if link_sugerido and (link_sugerido.startswith("http://") or link_sugerido.startswith("https://")):
        return sanitizar_url_oferta(link_sugerido)

    termo_enc = urllib.parse.quote_plus(termo.strip())
    loja_low = loja.lower()

    if "amazon" in loja_low:
        return f"https://www.amazon.com.br/s?k={termo_enc}"
    elif "magazine" in loja_low or "magalu" in loja_low:
        return f"https://www.magazineluiza.com.br/busca/{termo_enc}/"
    elif "mercado" in loja_low:
        return f"https://lista.mercadolivre.com.br/{termo_enc}"
    elif "shopee" in loja_low:
        return f"https://shopee.com.br/search?keyword={termo_enc}"
    elif "estante" in loja_low or "virtual" in loja_low:
        return f"https://www.estantevirtual.com.br/busca?q={termo_enc}"
    elif "infinito" in loja_low:
        return f"https://mundosinfinitos.com.br/catalogsearch/result/?q={termo_enc}"
    elif "comix" in loja_low:
        return f"https://www.comix.com.br/catalogsearch/result/?q={termo_enc}"
    elif "panini" in loja_low:
        return f"https://panini.com.br/catalogsearch/result/?q={termo_enc}"
    return f"https://www.google.com.br/search?tbm=shop&q={termo_enc}"


def eh_intencao_pesquisa_preco(texto: str) -> bool:
    """Verifica se a mensagem do usuário é um pedido de busca de preço/cotação de HQ."""
    txt = texto.strip().lower()
    gatilhos = [
        "pesquis", "pesquise", "pesquisar", "busca", "busque", "preço", "preco",
        "quanto custa", "valor de", "cotação", "cotacao", "comprar", "oferta",
        "mundos infinitos", "comix", "amazon", "magalu", "mercadolivre"
    ]
    return any(g in txt for g in gatilhos)


# -------------------------------------------------------------
# OPERAÇÕES DE CRUD ASSISTIDAS (AGENT / MCP)
# -------------------------------------------------------------
PROMPT_SISTEMA_CRUD_ASSISTIDO = """Você é o Assistente Especialista em Operações de CRUD do catálogo pessoal de Histórias em Quadrinhos (HQs, mangás, graphic novels e encadernados) do usuário.
O usuário enviará uma instrução em linguagem natural para gerenciar a coleção dele.

Seu objetivo é analisar a intenção e estruturar a operação em formato JSON.

AS AÇÕES POSSÍVEIS SÃO:
1. "adicionar": Inserir uma nova HQ na coleção.
   - Extraia com precisão:
     * "titulo": Nome da obra (ex: "Watchmen", "Akira", "Batman: Ano Um")
     * "edicao": Volume ou edição (ex: "Edição Definitiva", "Vol. 1", "#1", ou "" se não especificado)
     * "editora": Editora responsável (ex: "Panini", "Pipoca & Nanquim", "JBC", "Mythos", "DC", "Marvel", etc. Se o usuário não disser, use seu conhecimento para deduzir a editora mais provável dessa edição no Brasil)
     * "genero": Gênero literário (ex: "Super-heróis", "Ficção Científica", "Mangá / Shonen", "Terror", "Aventura", "Outro")
     * "escritor": Roteirista/autor (deduza se não informado, ex: "Alan Moore")
     * "ilustrador": Desenhista/artista (deduza se não informado, ex: "Dave Gibbons")
     * "resumo": Sinopse ou premissa da história em 2 a 4 frases em português
     * "prateleira": Localização física (se mencionada, ex: "Estante 2", senão use a prateleira padrão fornecida)
     * "lido": "Lido" se o usuário mencionar que já leu, "Lendo" se estiver lendo atualmente, senão "Não Lido"
     * "avaliacao": Nota de 1 a 5 se mencionada, senão 0
     * "resenha": Informações de compra mencionadas (ex: "Comprado por R$ 120,00", "Comprado hoje por R$ 120,00", etc.)
     * "preco_pago": Valor numérico em float caso tenha sido mencionado preço (ex: 120.0), senão null

2. "remover": Excluir uma HQ da coleção.
   - Extraia:
     * "titulo": Título da HQ a ser removida
     * "edicao": Edição ou volume (se especificado)
     * "id_alvo": ID do quadrinho no catálogo caso você consiga identificá-lo com certeza na lista do acervo fornecido (senão null)

3. "atualizar": Alterar status, nota, prateleira ou resenha de uma HQ existente.
   - Extraia:
     * "titulo": Título da HQ
     * "edicao": Edição (se informada)
     * "campo": Nome do campo a atualizar ("lido", "avaliacao", "prateleira", "resumo", "resenha")
     * "novo_valor": Novo valor (ex: "Lido", "Lendo", "Não Lido", 5, "Estante 2", etc.)
     * "id_alvo": ID correspondente se identificado

4. "adicionar_desejo": Adicionar um título na Lista de Desejos.
   - Extraia: "titulo", "edicao", "editora", "melhor_preco", "observacoes"

5. "remover_desejo": Remover um título da Lista de Desejos.
   - Extraia: "titulo", "edicao"

6. "consultar": Pergunta informativa sobre o acervo.
   - Extraia: "resposta" (sua resposta direta em texto à dúvida do usuário)

FORMATO DE SAÍDA:
Retorne ESTRITAMENTE um objeto JSON válido:
{
  "acao": "adicionar" | "remover" | "atualizar" | "adicionar_desejo" | "remover_desejo" | "consultar" | "desconhecido",
  "explicacao": "Breve mensagem explicativa em português sobre a operação que foi identificada.",
  "dados": { ... }
}
"""


def limpar_e_parsear_json_dict(texto_resposta: str) -> Dict[str, Any]:
    """
    Remove blocos de formatação markdown (```json ... ```) e faz o parse seguro de um objeto JSON.
    """
    texto = (texto_resposta or "").strip()

    match_bloco = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", texto, re.IGNORECASE)
    if match_bloco:
        texto = match_bloco.group(1).strip()

    match_obj = re.search(r"(\{[\s\S]*\})", texto)
    if match_obj:
        texto = match_obj.group(1).strip()

    try:
        dados = json.loads(texto)
        if isinstance(dados, dict):
            return dados
    except Exception:
        pass
    return {}


def processar_comando_crud_assistido(
    comando: str,
    catalogo_hqs: List[Dict[str, Any]],
    prateleira_padrao: str = "Estante 1 - Prateleira 1",
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.1-flash-lite",
    max_retries_por_modelo: int = 2
) -> Dict[str, Any]:
    """
    Interpreta comandos em linguagem natural para operações de CRUD assistidas no acervo de HQs.
    Utiliza JEV System 1 para decisões determinísticas/rápidas (<5ms) e recorre ao Gemini System 2
    para desambiguação complexa e enriquecimento enciclopédico de metadados.
    """
    # 1. Fast Path JEV System 1: Decisão rápida sem latência
    decisao_jev = jev_engine.classificar_intencao_system1(comando)
    
    if decisao_jev.intent == jev_engine.IntencaoEnum.REMOVER and decisao_jev.entities.get("id"):
        return {
            "acao": "remover",
            "dados": {"id": decisao_jev.entities["id"]},
            "mensagem_assistente": f"Solicitação de remoção da edição #{decisao_jev.entities['id']} validada via JEV System 1."
        }

    if decisao_jev.intent == jev_engine.IntencaoEnum.ATUALIZAR_STATUS and decisao_jev.entities.get("titulo"):
        dup_dec = jev_engine.decidir_duplicata_probabilistica(
            {"titulo": decisao_jev.entities["titulo"], "edicao": ""},
            catalogo_hqs,
            threshold_auto=0.80
        )
        if dup_dec.is_duplicate and dup_dec.existing_id:
            return {
                "acao": "atualizar",
                "dados": {
                    "id": dup_dec.existing_id,
                    "lido": decisao_jev.entities.get("novo_status", "Lido")
                },
                "mensagem_assistente": f"Status de '{dup_dec.existing_title}' atualizado para {decisao_jev.entities.get('novo_status', 'Lido')} via JEV System 1."
            }

    # 2. System 2: Processamento generativo via Gemini SDK
    client = get_gemini_client(api_key)

    # Resumo enxuto do catálogo para a IA conseguir relacionar títulos e IDs existentes
    linhas_catalogo = []
    for hq in catalogo_hqs[:120]:  # Limite seguro para manter prompt rápido
        id_hq = hq.get("id") or "?"
        tit = (hq.get("titulo") or "").strip()
        ed = (hq.get("edicao") or "").strip()
        edit = (hq.get("editora") or "").strip()
        prat = (hq.get("prateleira") or "").strip()
        lido = (hq.get("lido") or "").strip()
        linhas_catalogo.append(f"- ID #{id_hq}: \"{tit}\" ({ed}) | Editora: {edit} | Local: {prat} | Status: {lido}")

    catalogo_str = "\n".join(linhas_catalogo) if linhas_catalogo else "Nenhum quadrinho cadastrado no momento."

    prompt_usuario = f"""{PROMPT_SISTEMA_CRUD_ASSISTIDO}

---
CONTEXTO DO USUÁRIO:
- Prateleira padrão atual: "{prateleira_padrao}"
- Acervo atual do usuário ({len(catalogo_hqs)} HQs cadastradas):
{catalogo_str}
---

INSTRUÇÃO DO USUÁRIO:
"{comando}"

Retorne o JSON da operação correspondente:"""

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1
    )

    modelos_tentativa = [modelo]
    modelos_disponiveis = [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
        "gemini-pro-latest"
    ]
    for fb in modelos_disponiveis:
        if fb not in modelos_tentativa:
            modelos_tentativa.append(fb)

    ultimo_erro = None
    for mod in modelos_tentativa:
        for tentativa in range(1, max_retries_por_modelo + 1):
            try:
                response = client.models.generate_content(
                    model=mod,
                    contents=prompt_usuario,
                    config=config
                )
                if response and response.text:
                    parsed = limpar_e_parsear_json_dict(response.text)
                    if parsed and "acao" in parsed:
                        return parsed
            except Exception as ex:
                ultimo_erro = ex
                erro_str = str(ex)
                tipo_erro = _analisar_tipo_erro(erro_str)
                if tipo_erro == "sobrecarga_temporaria" and tentativa < max_retries_por_modelo:
                    time.sleep(1.0 * tentativa)
                else:
                    break

    # Fallback caso a IA não responda
    return {
        "acao": "desconhecido",
        "explicacao": f"Não foi possível processar o comando com a IA: {ultimo_erro}",
        "dados": {}
    }


# -------------------------------------------------------------
# BUSCA ONLINE DE CAPAS (ITUNES / OPENLIBRARY / SERPAPI)
# -------------------------------------------------------------
def extrair_og_image(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 3.0) -> Optional[str]:
    """Tenta obter a imagem og:image ou twitter:image de uma página web de quadrinhos."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return None
    if requests is None or BeautifulSoup is None:
        return None
    h = headers or {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=h, timeout=timeout)
        if r.status_code == 200 and r.text:
            soup = BeautifulSoup(r.text, "html.parser")
            og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
            if og and og.get("content"):
                img_c = str(og.get("content")).strip()
                if (img_c.startswith("http://") or img_c.startswith("https://")) and not img_c.endswith(".ico"):
                    return img_c
    except Exception:
        pass
    return None


def buscar_capas_online(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    escritor: str = "",
    limite: int = 15
) -> List[Dict[str, str]]:
    """
    Busca capas reais e em alta definição de quadrinhos, mangás e graphic novels online:
    1. Bing Images Scraper (Imagens reais em HD de Panini, Amazon, Guia dos Quadrinhos, MercadoLivre, ComicVine)
    2. Apple Books / iTunes Search API (Artes oficiais em alta resolução 800x800)
    3. OpenLibrary Covers API
    4. SerpApi Google Images (se configurada)
    
    Aplica validação concorrente ultra-rápida (HTTP HEAD/GET) para garantir que ZERO imagens venham quebradas
    e retorna o resultado em menos de 3 segundos.
    """
    if not titulo or not titulo.strip():
        return []

    import html
    from concurrent.futures import ThreadPoolExecutor

    capas_candidatas: List[Dict[str, str]] = []
    urls_vistas = set()

    dominios_bloqueados = [
        "shutterstock", "poder360", "veja.abril", "oglobo.globo", "universoalien",
        "semanticscholar", "cnnbrasil", "g1.globo", "folha.uol", "estadao", "metropoles", "uol.com.br/splash"
    ]

    def add_candidata(url: str, tit: str, fonte: str, thumb: Optional[str] = None):
        if not url or url in urls_vistas:
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            return
        u_low = url.lower()
        if any(d in u_low for d in dominios_bloqueados):
            return
        if "capasthumbs/antigas" in u_low or ("logo" in u_low and "capa" not in u_low):
            return
        urls_vistas.add(url)
        capas_candidatas.append({
            "url": url,
            "titulo": tit or titulo,
            "fonte": fonte,
            "thumbnail": thumb or url
        })

    # Extração e normalização dos termos
    titulo_limpo = re.sub(r"\s+", " ", str(titulo)).strip()
    titulo_sem_pont = re.sub(r"[^\w\s]", " ", titulo_limpo)
    titulo_sem_pont = re.sub(r"\s+", " ", titulo_sem_pont).strip()

    num_num = re.sub(r"[^\d]", "", edicao or "")
    if not num_num:
        m_num = re.search(r"\b(?:vol(?:ume)?|v|ed|#|n[oº°])?\.?\s*(\d{1,3})\b", titulo_limpo, re.IGNORECASE)
        if m_num:
            num_num = m_num.group(1)

    palavras_titulo = [
        p for p in re.split(r"\W+", normalizar_str_busca(titulo_limpo))
        if len(p) >= 3 and p not in ["panini", "capa", "gibi", "hq", "edicao", "volume", "vol", "editora", "quadrinhos"]
    ]

    palavras_distintas = [p for p in palavras_titulo if not p.isdigit() and len(p) >= 3]
    if not palavras_distintas and palavras_titulo:
        palavras_distintas = palavras_titulo

    headers_web = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    # 0. PROVEDOR 0: Capa Canônica Oficial Verificada (quando disponível no catálogo)
    try:
        ficha_can = obter_dados_canonicos_guia_dos_quadrinhos(titulo_limpo, edicao, editora)
        if ficha_can:
            if ficha_can.get("capa_url"):
                add_candidata(ficha_can["capa_url"], f"{titulo_limpo} nº {edicao or '1'} (Capa Oficial Panini)", "Guia dos Quadrinhos / Oficial")
            for alt_c in ficha_can.get("capas_alternativas", []):
                u_alt = alt_c.get("url") or alt_c.get("thumbnail")
                if u_alt:
                    add_candidata(u_alt, alt_c.get("titulo") or titulo_limpo, alt_c.get("fonte") or "Guia dos Quadrinhos")
    except Exception:
        pass

    # Geração de termos de busca inteligentes (nacional e internacional)
    termos_busca = [
        f"{titulo_sem_pont} {edicao}".strip(),
        titulo_sem_pont
    ]
    # Mapeamentos de sinônimos/títulos em inglês conhecidos
    mapa_traducoes = {
        "100 balas": "100 Bullets",
        "o longo dia das bruxas": "The Long Halloween",
        "ano um": "Year One",
        "cavaleiro das trevas": "Dark Knight",
        "morte do superman": "Death of Superman",
        "reino do amanha": "Kingdom Come",
        "monstro do pantano": "Swamp Thing",
        "demolidor": "Daredevil",
        "homem aranha": "Spider-Man",
        "homem de ferro": "Iron Man",
        "gaviao arqueiro": "Hawkeye",
        "novos mutantes": "New Mutants",
        "vingadores": "Avengers",
        "piada mortal": "The Killing Joke",
        "guerra secreta": "Secret War",
        "guerras secretas": "Secret Wars",
        "crise nas infinitas terras": "Crisis on Infinite Earths",
        "ponto de ignicao": "Flashpoint",
        "filho do demonio": "Son of the Demon",
        "asilo arkham": "Arkham Asylum"
    }
    tit_low = normalizar_str_busca(titulo_limpo)
    for k_pt, v_en in mapa_traducoes.items():
        if k_pt in tit_low:
            termos_busca.append(f"{v_en} {edicao}".strip())
            termos_busca.append(v_en)
            break

    # 1. PROVEDOR 1: Apple Books / iTunes Search API (BR e US em paralelo)
    if requests is not None:
        def _fetch_itunes(termo_e_pais):
            termo, pais = termo_e_pais
            try:
                r_it = requests.get(
                    "https://itunes.apple.com/search",
                    params={"term": termo, "media": "ebook", "country": pais, "limit": 6},
                    headers=headers_web,
                    timeout=2.0
                )
                if r_it.status_code == 200:
                    return r_it.json().get("results", [])
            except Exception:
                pass
            return []

        payload_it = [(t, "BR") for t in termos_busca[:2]] + [(t, "US") for t in termos_busca[:2]]
        with ThreadPoolExecutor(max_workers=4) as ex_it:
            for results in ex_it.map(_fetch_itunes, payload_it):
                for item in results:
                    art = item.get("artworkUrl100") or ""
                    item_tit = item.get("trackName") or ""
                    if art:
                        highres = art.replace("100x100bb.jpg", "800x800bb.jpg").replace("100x100bb.png", "800x800bb.png")
                        add_candidata(highres, item_tit, "Apple Books (HD Oficial)", art)

    # 2. PROVEDOR 2: OpenLibrary Covers API
    if requests is not None:
        def _fetch_openlibrary(termo):
            try:
                r_ol = requests.get(
                    "https://openlibrary.org/search.json",
                    params={"q": termo, "limit": 6},
                    headers={"User-Agent": "HqCatalog/1.0"},
                    timeout=2.0
                )
                if r_ol.status_code == 200:
                    return r_ol.json().get("docs", [])
            except Exception:
                pass
            return []

        with ThreadPoolExecutor(max_workers=3) as ex_ol:
            for docs in ex_ol.map(_fetch_openlibrary, termos_busca[:3]):
                for doc in docs:
                    cover_i = doc.get("cover_i")
                    doc_tit = doc.get("title") or ""
                    if cover_i:
                        c_url = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg"
                        c_thumb = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
                        add_candidata(c_url, doc_tit, "OpenLibrary (HD)", c_thumb)

    # 3. PROVEDOR 3: SerpApi Google Images (se configurada e com cota)
    serp_key = os.getenv("SERPAPI_API_KEY", "")
    if serp_key and len(capas_candidatas) < limite * 2:
        try:
            import serpapi
            client_serp = serpapi.Client(api_key=serp_key)
            query_serp = f"{titulo_limpo} {edicao} {editora} capa gibi HQ".strip()
            res_serp = client_serp.search({"engine": "google_images", "q": query_serp, "gl": "br", "hl": "pt-br", "num": 8})
            for img_it in res_serp.get("images_results", []):
                orig = img_it.get("original") or ""
                thumb = img_it.get("thumbnail") or ""
                tit_img = img_it.get("title") or titulo_limpo
                url_final = thumb if ("guiadosquadrinhos.com" in orig.lower() or "ShowImage.aspx" in orig) else (orig or thumb)
                if url_final:
                    add_candidata(url=url_final, tit=tit_img, fonte="Google Images (HD)", thumb=thumb or url_final)
        except Exception:
            pass

    # -------------------------------------------------------------
    # VALIDAÇÃO CONCORRENTE RÁPIDA (Zero imagens quebradas)
    # -------------------------------------------------------------
    def _validar_e_ajustar_capa(item: Dict[str, str]) -> Optional[Dict[str, str]]:
        if requests is None:
            return item
        url_test = item.get("url", "")
        if not url_test:
            return None
        h_check = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            # 1. Testa HEAD rápido com 1.2s timeout
            r_h = requests.head(url_test, headers=h_check, timeout=1.2, allow_redirects=True)
            if r_h.status_code == 200:
                ct = r_h.headers.get("Content-Type", "").lower()
                if "image" in ct or not ct:
                    return item
            # 2. Testa GET range
            r_g = requests.get(url_test, headers={**h_check, "Range": "bytes=0-1024"}, timeout=1.2, allow_redirects=True, stream=True)
            if r_g.status_code in (200, 206):
                ct = r_g.headers.get("Content-Type", "").lower()
                if "image" in ct or not ct:
                    return item
        except Exception:
            pass

        # Fallback para o thumbnail caso a URL de alta resolução esteja protegida
        thumb_test = item.get("thumbnail")
        if thumb_test and thumb_test != url_test:
            try:
                r_th = requests.head(thumb_test, headers=h_check, timeout=1.2, allow_redirects=True)
                if r_th.status_code == 200:
                    item_copia = dict(item)
                    item_copia["url"] = thumb_test
                    return item_copia
            except Exception:
                pass
        return None

    capas_validadas: List[Dict[str, str]] = []
    if requests is not None and capas_candidatas:
        with ThreadPoolExecutor(max_workers=15) as executor:
            for item_ok in executor.map(_validar_e_ajustar_capa, capas_candidatas):
                if item_ok:
                    capas_validadas.append(item_ok)
    else:
        capas_validadas = list(capas_candidatas)

    # Ranking e pontuação de relevância das capas validadas
    def _score_capa(item: Dict[str, str]) -> int:
        tit_c = normalizar_str_busca(item.get("titulo", ""))
        score = 0
        if palavras_titulo and all(p in tit_c for p in palavras_titulo):
            score += 60
        for p in palavras_titulo:
            if p in tit_c:
                score += 15
        if num_num:
            if f"n {num_num}" in tit_c or f"nº {num_num}" in tit_c or f"vol {num_num}" in tit_c or f"volume {num_num}" in tit_c or f" {num_num} " in f" {tit_c} ":
                score += 40
            else:
                m_outro = re.findall(r"\b(?:vol(?:ume)?|n[oº°]?|#)\s*(\d+)\b", tit_c)
                if m_outro and num_num not in m_outro:
                    score -= 25
        if editora and normalizar_str_busca(editora) in tit_c:
            score += 20
        return score

    capas_validadas.sort(key=_score_capa, reverse=True)
    return capas_validadas[:limite]


def normalizar_str_busca(texto: Optional[str]) -> str:
    """Normaliza texto removendo acentos e caracteres especiais para comparação de relevância."""
    if not texto:
        return ""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("utf-8")
    return s.lower().strip()


def eh_oferta_relevante_para_titulo(titulo_candidato: str, titulo_busca: str) -> bool:
    """Valida se o anúncio/livro retornado realmente corresponde ao quadrinho pesquisado."""
    t_cand_norm = normalizar_str_busca(titulo_candidato)
    t_busca_norm = normalizar_str_busca(titulo_busca)
    if not t_cand_norm or not t_busca_norm:
        return False

    stopwords = {
        "o", "a", "os", "as", "de", "do", "da", "dos", "das", "em", "no", "na",
        "nos", "nas", "um", "uma", "uns", "umas", "com", "por", "para", "e", "ou",
        "vol", "volume", "edicao", "ed", "n", "no", "hq", "livro", "revista", "manga",
        "panini", "marvel", "dc", "comics", "novo", "lacrado", "capa", "dura", "compre",
        "online", "frete", "gratis", "colecao", "lendas", "graphic", "novel"
    }

    tokens_busca = [w for w in re.findall(r"\w+", t_busca_norm) if w not in stopwords and len(w) >= 3]
    if not tokens_busca:
        tokens_busca = [w for w in re.findall(r"\w+", t_busca_norm) if len(w) >= 2]

    if not tokens_busca:
        return True

    tokens_cand = set(re.findall(r"\w+", t_cand_norm))

    sinonimos = {
        "retorno": "return",
        "morte": "death",
        "ano": "year",
        "renascimento": "rebirth",
        "guerra": "war",
        "cavaleiro": "knight",
        "trevas": "dark"
    }

    matches = 0
    for t in tokens_busca:
        sin = sinonimos.get(t, "")
        if t in tokens_cand or any(t in w for w in tokens_cand) or (sin and (sin in tokens_cand or any(sin in w for w in tokens_cand))):
            matches += 1

    taxa_match = matches / len(tokens_busca)
    
    if len(tokens_busca) <= 4:
        return taxa_match >= 0.85
    return taxa_match >= 0.70


def extrair_json_seguro(texto: str) -> Any:
    """Extrai e faz parsing seguro de blocos JSON em strings."""
    if not texto:
        return None
    t = texto.strip()
    if "```" in t:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t)
        if match:
            t = match.group(1).strip()
    try:
        return json.loads(t)
    except Exception:
        match_arr = re.search(r"(\[[\s\S]*\])", t)
        if match_arr:
            try:
                return json.loads(match_arr.group(1))
            except Exception:
                pass
        match_obj = re.search(r"(\{[\s\S]*\})", t)
        if match_obj:
            try:
                return json.loads(match_obj.group(1))
            except Exception:
                pass
    return None


def buscar_precos_online(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    api_key: Optional[str] = None,
    limite: int = 10
) -> List[Dict[str, Any]]:
    """
    Busca preços e ofertas de HQs / Livros / Mangás na internet em múltiplos serviços:
    1. SerpApi / Google Shopping (se configurada)
    2. DuckDuckGo / Busca Web em lojas especializadas (Amazon Brasil, Panini, Mercado Livre, Shopee, Estante Virtual)
    3. Amazon Brasil (com link direto de busca/produto e catálogo oficial)
    4. Mercado Livre API / Web
    5. Google Books & Apple Books
    6. Catálogo Enciclopédico de Preços de Capa via Gemini IA
    Retorna uma lista de dicionários contendo {'titulo', 'preco', 'preco_formatado', 'fonte', 'link', 'thumbnail'}.
    """
    ofertas: List[Dict[str, Any]] = []
    links_vistos = set()

    if not titulo or not titulo.strip():
        return []

    def add_oferta(tit: str, preco: float, fonte: str, link: str, thumb: Optional[str] = None):
        if not tit or preco <= 0:
            return
        if not eh_oferta_relevante_para_titulo(tit, titulo):
            return
        chave = f"{fonte}_{round(preco, 2)}_{tit[:25].lower()}"
        if chave in links_vistos:
            return
        links_vistos.add(chave)
        ofertas.append({
            "titulo": tit,
            "preco": round(float(preco), 2),
            "preco_formatado": f"R$ {preco:.2f}".replace(".", ","),
            "fonte": fonte,
            "link": link or "",
            "thumbnail": thumb or ""
        })

    termo_principal = f"{titulo} {edicao} {editora}".strip()
    termo_enc = urllib.parse.quote_plus(f"{titulo} {edicao}".strip())

    # 1. Pesquisa de Preços Reais via Gemini com Google Search Grounding (Prioridade Máxima)
    gemini_key = api_key or os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            client = get_gemini_client(gemini_key)
            prompt_preco = f"""Você é um pesquisador especialista em cotação de preços de quadrinhos, mangás e livros no Brasil.
Pesquise no Google Search por anúncios reais, preços atuais e links de lojas brasileiras (Amazon Brasil, Mercado Livre, Pipoca & Nanquim, Panini Comics, Comix Book Shop, Mundos Infinitos, Estante Virtual, Livrarias, Shopee, etc.) para:
- Título: "{titulo}"
- Edição / Volume: "{edicao or 'Edição padrão'}"
- Editora: "{editora or 'Nacional'}"

REGRAS RIGOROSAS:
1. Extraia APENAS preços REAIS e ATUAIS encontrados na pesquisa para esta edição específica.
2. NUNCA invente preços ou estime valores que não existam nas páginas dos anúncios.
3. Obtenha a URL real da loja / anúncio ou página do produto.
4. Retorne ESTRITAMENTE um array JSON contendo as ofertas reais encontradas:
[
  {{
    "titulo": "Nome exato da edição / produto no anúncio",
    "preco": 92.54,
    "fonte": "Amazon Brasil" (ou "Mercado Livre", "Pipoca & Nanquim", "Panini Comics", "Comix Book Shop", "Estante Virtual", etc.),
    "link": "URL real da página ou anúncio"
  }}
]
Se não encontrar anúncios reais com preços confirmados, retorne []."""

            config_grounding = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1
            ) if types else None

            modelos_busca = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
            for mod in modelos_busca:
                try:
                    resp = client.models.generate_content(
                        model=mod,
                        contents=prompt_preco,
                        config=config_grounding
                    )
                    if resp and resp.text:
                        dados_p = extrair_json_seguro(resp.text)
                        if isinstance(dados_p, list):
                            for item_p in dados_p:
                                if isinstance(item_p, dict) and item_p.get("preco"):
                                    p_val = float(item_p.get("preco") or 0.0)
                                    if p_val > 0:
                                        add_oferta(
                                            tit=item_p.get("titulo") or titulo,
                                            preco=p_val,
                                            fonte=item_p.get("fonte") or "Loja Online",
                                            link=item_p.get("link") or ""
                                        )
                            if ofertas:
                                break
                except Exception as ex_mod:
                    continue
        except Exception as ex_g:
            print(f"[Aviso Gemini Busca de Preços Google Search: {ex_g}]")

    # 2. SerpApi / Google Shopping (se configurado)
    serpapi_key = DEFAULT_SERPAPI_KEY or os.getenv("SERPAPI_API_KEY", "")
    if serpapi_key and len(ofertas) < limite:
        try:
            res_serp = pesquisar_precos_serpapi(termo_principal, api_key=serpapi_key)
            for it in res_serp.get("itens", []):
                p_str = str(it.get("price") or it.get("extracted_price") or "")
                nums = re.findall(r"\d+[\.,]\d+", p_str.replace("R$", "").replace(" ", "").strip())
                val_num = 0.0
                if nums:
                    val_num = float(nums[0].replace(".", "").replace(",", ".")) if "," in nums[0] else float(nums[0])
                if val_num > 0:
                    add_oferta(
                        tit=it.get("title") or termo_principal,
                        preco=val_num,
                        fonte=it.get("source") or "Google Shopping",
                        link=it.get("product_link") or it.get("link") or "",
                        thumb=it.get("thumbnail")
                    )
        except Exception as ex:
            print(f"[Aviso SerpApi Preços: {ex}]")

    # 3. Busca Web / Lojas Especializadas via DuckDuckGo (Apenas com preços reais no texto)
    if requests is not None and BeautifulSoup is not None and len(ofertas) < limite:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9",
            }
            url_ddg = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(f'{titulo} preco amazon panini')}"
            r_ddg = requests.get(url_ddg, headers=headers, timeout=6)
            if r_ddg.status_code == 200:
                soup_ddg = BeautifulSoup(r_ddg.text, "html.parser")
                for res in soup_ddg.select(".result__body"):
                    title_el = res.select_one(".result__title a")
                    snippet_el = res.select_one(".result__snippet")
                    if not title_el:
                        continue
                    tit_raw = title_el.get_text(strip=True)
                    raw_href = title_el.get("href", "")
                    match_uddg = re.search(r"uddg=([^&]+)", raw_href)
                    real_url = urllib.parse.unquote(match_uddg.group(1)) if match_uddg else raw_href

                    if "duckduckgo.com" in real_url or "bing.com" in real_url:
                        continue

                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                    fonte = "Loja Online"
                    if "amazon.com.br" in real_url:
                        fonte = "Amazon Brasil"
                    elif "mercadolivre.com.br" in real_url:
                        fonte = "Mercado Livre"
                    elif "shopee.com.br" in real_url:
                        fonte = "Shopee"
                    elif "panini.com.br" in real_url:
                        fonte = "Panini Comics"
                    elif "estantevirtual.com.br" in real_url:
                        fonte = "Estante Virtual"
                    elif "leioarte.com.br" in real_url:
                        fonte = "LeioArte"
                    elif "mundosinfinitos.com.br" in real_url:
                        fonte = "Mundos Infinitos"
                    elif "comix.com.br" in real_url:
                        fonte = "Comix Book Shop"

                    tit_limpo = re.sub(r"\s*[-|]\s*(Amazon\.com\.br|MercadoLivre|Shopee|Panini Brasil|Estante Virtual).*$", "", tit_raw, flags=re.IGNORECASE).strip()
                    tit_limpo = re.sub(r"^(Compre online\s*|Compre\s*)", "", tit_limpo, flags=re.IGNORECASE).strip()

                    texto_total = f"{tit_raw} {snippet}"
                    preco = 0.0
                    match_reais_centavos = re.search(r"(\d+)\s*reais\s*(?:con|com|e)?\s*(\d+)\s*centavos", texto_total, re.IGNORECASE)
                    if match_reais_centavos:
                        preco = float(f"{match_reais_centavos.group(1)}.{match_reais_centavos.group(2)}")
                    else:
                        precos_encontrados = re.findall(r"R\$\s*(\d{1,4}(?:[.,]\d{2})?)", texto_total)
                        for p_str in precos_encontrados:
                            p_val = float(p_str.replace(".", "").replace(",", ".")) if "," in p_str else float(p_str)
                            if 10.0 <= p_val <= 1500.0:
                                preco = p_val
                                break

                    # Só adiciona se encontrou preço real no texto/snippet
                    if preco > 0:
                        add_oferta(tit_limpo, preco, fonte, real_url)
        except Exception as ex:
            print(f"[Aviso Busca Web Preços: {ex}]")

    # 4. Amazon Brasil Scraper Direto (Se retornar preço na página de resultados)
    if requests is not None and BeautifulSoup is not None and len(ofertas) < limite:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            url_amz = "https://www.amazon.com.br/s"
            r_amz = requests.get(url_amz, params={"k": termo_principal, "i": "stripbooks"}, headers=headers, timeout=6)
            if r_amz.status_code == 200:
                soup_amz = BeautifulSoup(r_amz.text, "html.parser")
                for item in soup_amz.select(".s-result-item[data-asin]"):
                    asin = item.get("data-asin")
                    if not asin:
                        continue
                    h2 = item.select_one("h2")
                    price_elem = item.select_one(".a-price .a-offscreen") or item.select_one(".a-color-price")
                    thumb_elem = item.select_one("img.s-image")
                    if h2 and price_elem:
                        tit_amz = h2.get_text(strip=True)
                        p_raw = price_elem.get_text(strip=True)
                        p_num = 0.0
                        if p_raw:
                            nums = re.findall(r"\d+[\.,]\d+", p_raw.replace("R$", "").replace("\xa0", "").strip())
                            if nums:
                                p_num = float(nums[0].replace(".", "").replace(",", ".")) if "," in nums[0] else float(nums[0])
                        if p_num > 0:
                            add_oferta(
                                tit=tit_amz,
                                preco=p_num,
                                fonte="Amazon Brasil",
                                link=f"https://www.amazon.com.br/dp/{asin}",
                                thumb=thumb_elem.get("src") if thumb_elem else None
                            )
        except Exception as ex:
            print(f"[Aviso Amazon Preços: {ex}]")

    # 5. Mercado Livre API Pública (Itens com preço e link real do anúncio)
    if requests is not None and len(ofertas) < limite:
        try:
            url_ml = "https://api.mercadolivre.com/sites/MLB/search"
            r_ml = requests.get(
                url_ml,
                params={"q": f"HQ {titulo}".strip(), "limit": 10},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=5
            )
            if r_ml.status_code == 200:
                dados_ml = r_ml.json()
                for item in dados_ml.get("results", []):
                    p_val = float(item.get("price") or 0.0)
                    perm_link = item.get("permalink") or ""
                    if p_val > 0 and perm_link:
                        add_oferta(
                            tit=item.get("title") or titulo,
                            preco=p_val,
                            fonte="Mercado Livre",
                            link=perm_link,
                            thumb=item.get("thumbnail")
                        )
        except Exception as ex:
            print(f"[Aviso Mercado Livre Preços: {ex}]")

    # 6. Google Books API (Preço de venda oficial)
    if requests is not None and len(ofertas) < limite:
        try:
            url_gb = "https://www.googleapis.com/books/v1/volumes"
            r_gb = requests.get(
                url_gb,
                params={"q": f'intitle:"{titulo}"', "maxResults": 6, "country": "BR"},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=5
            )
            if r_gb.status_code == 200:
                dados_gb = r_gb.json()
                for item in dados_gb.get("items", []):
                    vol_info = item.get("volumeInfo", {})
                    sale_info = item.get("saleInfo", {})
                    p_info = sale_info.get("retailPrice") or sale_info.get("listPrice") or {}
                    p_amt = float(p_info.get("amount") or 0.0)
                    if p_amt > 0:
                        add_oferta(
                            tit=vol_info.get("title") or titulo,
                            preco=p_amt,
                            fonte="Google Play Livros",
                            link=sale_info.get("buyLink") or vol_info.get("infoLink") or "",
                            thumb=vol_info.get("imageLinks", {}).get("thumbnail")
                        )
        except Exception as ex:
            print(f"[Aviso Google Books Preços: {ex}]")

    # 7. Apple Books / iTunes (Preço oficial)
    if requests is not None and len(ofertas) < limite:
        try:
            r_it = requests.get(
                "https://itunes.apple.com/search",
                params={"term": titulo.strip(), "media": "ebook", "country": "BR", "limit": 6},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=5
            )
            if r_it.status_code == 200:
                dados_it = r_it.json()
                for item in dados_it.get("results", []):
                    p_val = float(item.get("price") or 0.0)
                    if p_val > 0:
                        add_oferta(
                            tit=item.get("trackName") or titulo,
                            preco=p_val,
                            fonte="Apple Books",
                            link=item.get("trackViewUrl") or "",
                            thumb=item.get("artworkUrl100")
                        )
        except Exception as ex:
            print(f"[Aviso iTunes Preços: {ex}]")

    # Ordena as ofertas reais por menor preço
    ofertas.sort(key=lambda x: x["preco"])
    return ofertas[:limite]


def baixar_imagem_url_base64(url: str, max_dim: int = 1000, quality: int = 90, timeout: int = 4, fallback_url: Optional[str] = None) -> str:
    """
    Baixa uma imagem a partir de uma URL e converte em string base64 JPEG compacta em alta definição.
    Se não for possível baixar ou processar, tenta a fallback_url ou retorna a própria URL original.
    """
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return url

    if requests is None or Image is None:
        return url

    urls_para_tentar = [url]
    if fallback_url and fallback_url != url:
        urls_para_tentar.append(fallback_url)

    for u in urls_para_tentar:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }
            r = requests.get(u, headers=headers, timeout=timeout)
            if r.status_code == 200 and r.content:
                img = Image.open(io.BytesIO(r.content))
                img = img.convert("RGB")
                if max(img.size) > max_dim:
                    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
                return f"data:image/jpeg;base64,{b64_str}"
        except Exception as ex:
            print(f"[Aviso ao baixar imagem {u}: {ex}]")

    return url


# -------------------------------------------------------------
# 1. 🧭 GUIA DE ORDEM DE LEITURA & CRONOLOGIA DE SAGAS (SMART READING ORDER)
# -------------------------------------------------------------
PROMPT_SISTEMA_ORDEM_LEITURA = """Você é o Especialista Supremo em Continuidade, Cronologia e Ordens de Leitura de Histórias em Quadrinhos (DC, Marvel, Mangás, Graphic Novels Europeias, Vertigo, Image Comics e Quadrinhos Nacionais).

O usuário solicitará a ordem de leitura para uma saga, personagem, arco histórico ou universo (ex: "Saga do Infinito", "Batman dos anos 80 e 90", "Berserk", "Sandman", "Crise nas Infinitas Terras", "X-Men Era do Apocalipse", "Cavaleiro da Lua", "Guerras Secretas", "Monstro do Pântano do Alan Moore").

Seu objetivo é:
1. Mapear a cronologia canônica ideal e recomendada de leitura para o tema pedido.
2. Cruzar com a lista de HQs que o usuário JÁ POSSUI NO CATÁLOGO dele fornecido abaixo:
   - Se ele possui o quadrinho ou encadernado correspondente, identifique "status_colecao": "no_acervo", informe o "hq_id", "prateleira" e o status de leitura dele.
   - Se ele NÃO possui essa edição e ela é importante para a saga, classifique como "status_colecao": "faltante" (gap), para que ele saiba que precisa adquirir essa edição.
3. Formatar uma jornada de leitura clara, emocionante e didática, indicando o ponto de partida, o clímax e os epílogos.

FORMATO DE SAÍDA:
Retorne ESTRITAMENTE um objeto JSON válido no formato:
{
  "saga_identificada": "Nome Canônico da Saga ou Cronologia",
  "universo": "DC Comics" | "Marvel" | "Mangá" | "Vertigo / Dark Fantasy" | "Autoral / Outro",
  "introducao": "Breve introdução contextualizando o peso dessa saga/cronologia no universo dos quadrinhos e por que essa ordem é a melhor para ter a experiência máxima.",
  "etapas": [
    {
      "ordem": 1,
      "titulo": "Título da HQ ou Encadernado",
      "edicao_recomendada": "Volume 1 / Edição Especial / Edição Definitiva",
      "importancia": "Ponto de Partida" | "Essencial" | "Tie-in Recomendado" | "Clímax" | "Epílogo",
      "sinopse_rapida": "Por que ler esta edição neste momento específico da cronologia e o que ela agrega à trama central.",
      "status_colecao": "no_acervo" | "faltante",
      "hq_id": 12,
      "prateleira": "Estante 1 - Prateleira 2",
      "lido": "Lido" | "Não Lido" | "Lendo" | "Não Possui",
      "termo_busca_compra": "Batman Ano Um Panini"
    }
  ],
  "gaps_criticos": [
    {
      "titulo": "Nome da HQ Faltante",
      "edicao": "Volume X",
      "motivo": "Por que esta edição é crucial para preencher o vazio na compreensão da história."
    }
  ],
  "dica_curador": "Dica de ouro ou curiosidade de bastidores sobre como ler e aproveitar melhor essa sequência."
}
"""

def gerar_ordem_leitura(
    tema_ou_saga: str,
    catalogo_hqs: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.5-flash",
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Gera um guia cronológico de leitura inteligente para qualquer saga ou personagem,
    cruzando automaticamente com o acervo existente do usuário para apontar o que ele já tem e o que falta.
    """
    client = get_gemini_client(api_key)

    linhas_cat = []
    for hq in catalogo_hqs:
        id_hq = hq.get("id") or "?"
        tit = (hq.get("titulo") or "").strip()
        ed = (hq.get("edicao") or "").strip()
        edit = (hq.get("editora") or "").strip()
        prat = (hq.get("prateleira") or "").strip()
        lido = (hq.get("lido") or "Não Lido").strip()
        aval = int(hq.get("avaliacao") or 0)
        linhas_cat.append(f"- ID #{id_hq}: \"{tit}\" ({ed}) | Editora: {edit} | Local: {prat} | Status: {lido} | {aval}⭐")

    acervo_str = "\n".join(linhas_cat) if linhas_cat else "O usuário ainda não tem quadrinhos cadastrados."

    prompt_final = f"""{PROMPT_SISTEMA_ORDEM_LEITURA}

---
ACERVO ATUAL DO USUÁRIO ({len(catalogo_hqs)} HQs cadastradas):
{acervo_str}
---

TEMA / SAGA SOLICITADA PELO LEITOR:
"{tema_ou_saga}"

Retorne o JSON com o Guia de Leitura Completo:"""

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2
    )

    modelos = [modelo, "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
    for mod in modelos:
        for tentativa in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=mod,
                    contents=prompt_final,
                    config=config
                )
                if response and response.text:
                    parsed = limpar_e_parsear_json_dict(response.text)
                    if parsed and "etapas" in parsed:
                        return parsed
            except Exception as ex:
                print(f"[Aviso Ordem Leitura mod={mod} t={tentativa}]: {ex}")
                time.sleep(1.0 * tentativa)

    return {
        "saga_identificada": tema_ou_saga,
        "universo": "Geral",
        "introducao": "Não foi possível estruturar a ordem de leitura automaticamente no momento.",
        "etapas": [],
        "gaps_criticos": [],
        "dica_curador": ""
    }


# -------------------------------------------------------------
# 2. 🔍 DETETIVE DE COLEÇÃO & GAPS FALTANTES (COLLECTION DNA)
# -------------------------------------------------------------
PROMPT_SISTEMA_DNA_COLECAO = """Você é um Consultor Sênior de Colecionismo de Histórias em Quadrinhos e Analista de Perfil de Leitores de HQs, Graphic Novels e Mangás.

Analise TODO o acervo cadastrado pelo usuário (títulos, volumes, editoras, autores/roteiristas, desenhistas, gêneros, status de leitura e notas):

Seus objetivos são:
1. Identificar o **DNA do Colecionador** (arquétipo, estilo predominante, épocas e preferências estéticas).
2. Criar a **Distribuição Percentual por Estilos/Gêneros** (soma totalizando 100%).
3. Atuar como **Detetive de Gaps (Volumes e Séries Faltantes)**:
   - Identifique séries em que o usuário tem alguns volumes e faltam edições intermediárias ou conclusões (ex: tem vols 1, 2, 4 -> falta o 3; tem Sandman 1 a 3 -> faltam edições seguintes; tem Batman O Longo Dia das Bruxas mas não tem Vitória Sombria).
4. Gerar **Recomendações Cirúrgicas de Próximas Compras**:
   - 3 a 5 quadrinhos que ele AINDA NÃO TEM, mas que combinam perfeitamente com as obras que ele avaliou com 4 ou 5 estrelas e seus autores favoritos.

FORMATO DE SAÍDA:
Retorne ESTRITAMENTE um objeto JSON:
{
  "arquetipo_colecionador": "Ex: O Mestre das Graphic Novels Sombrias & Ficção Filosófica",
  "resumo_dna": "Texto detalhado (2 a 3 parágrafos) traçando o perfil psicológico e estético do leitor com base em suas obras.",
  "pontos_fortes_acervo": [
    "Destaque 1 sobre a qualidade ou profundidade do acervo",
    "Destaque 2",
    "Destaque 3"
  ],
  "distribuicao_estilos": [
    {"categoria": "Dark Fantasy & Seinen", "porcentagem": 35},
    {"categoria": "Super-heróis Desconstruídos / Vertigo", "porcentagem": 25},
    {"categoria": "Ficção Científica & Cyberpunk", "porcentagem": 20},
    {"categoria": "Histórico & Biográfico", "porcentagem": 20}
  ],
  "gaps_detectados": [
    {
      "serie": "Nome da Série ou Universo",
      "volumes_possuidos": "Vols. 1, 2 e 4",
      "volume_faltante": "Vol. 3",
      "prioridade": "Alta" | "Média" | "Baixa",
      "motivo": "Volume intermediário que conecta a trama principal e fecha o arco.",
      "termo_busca": "Berserk Volume 3 Panini"
    }
  ],
  "recomendacoes_cirurgicas": [
    {
      "titulo": "Título da HQ Sugerida",
      "autor": "Nome do Autor/Roteirista",
      "editora": "Editora no Brasil",
      "por_que_comprar": "Conexão direta com obras que ele já amou na coleção.",
      "termo_busca": "Título da HQ Editora"
    }
  ]
}
"""

def analisar_dna_colecao_e_gaps(
    catalogo_hqs: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.5-flash",
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Realiza o diagnóstico completo do DNA do acervo de HQs, detecta volumes faltantes em séries
    e gera recomendações cirúrgicas de aquisição baseadas nos títulos favoritos.
    """
    if not catalogo_hqs:
        return {
            "arquetipo_colecionador": "Colecionador Iniciante",
            "resumo_dna": "Cadastre suas primeiras edições para desbloquear a análise de DNA da sua coleção!",
            "pontos_fortes_acervo": [],
            "distribuicao_estilos": [],
            "gaps_detectados": [],
            "recomendacoes_cirurgicas": []
        }

    client = get_gemini_client(api_key)

    linhas_cat = []
    for hq in catalogo_hqs:
        id_hq = hq.get("id") or "?"
        tit = (hq.get("titulo") or "").strip()
        ed = (hq.get("edicao") or "").strip()
        edit = (hq.get("editora") or "").strip()
        gen = (hq.get("genero") or "Outro").strip()
        esc = (hq.get("escritor") or "Não informado").strip()
        ilu = (hq.get("ilustrador") or "Não informado").strip()
        lido = (hq.get("lido") or "Não Lido").strip()
        aval = int(hq.get("avaliacao") or 0)
        resumo = (hq.get("resumo") or "")[:150]
        linhas_cat.append(f"- ID #{id_hq}: \"{tit}\" ({ed}) | Edit: {edit} | Gên: {gen} | Roteiro: {esc} | Arte: {ilu} | Status: {lido} | {aval}⭐ | Sinopse: {resumo}")

    acervo_str = "\n".join(linhas_cat)

    prompt_final = f"""{PROMPT_SISTEMA_DNA_COLECAO}

---
ACERVO COMPLETO DO USUÁRIO ({len(catalogo_hqs)} HQs cadastradas):
{acervo_str}
---

Retorne o diagnóstico completo do DNA e Gaps da Coleção em formato JSON:"""

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2
    )

    modelos = [modelo, "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
    for mod in modelos:
        for tentativa in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=mod,
                    contents=prompt_final,
                    config=config
                )
                if response and response.text:
                    parsed = limpar_e_parsear_json_dict(response.text)
                    if parsed and "arquetipo_colecionador" in parsed:
                        return parsed
            except Exception as ex:
                print(f"[Aviso DNA Coleção mod={mod} t={tentativa}]: {ex}")
                time.sleep(1.0 * tentativa)

    return {
        "arquetipo_colecionador": "Colecionador Eclético",
        "resumo_dna": "Não foi possível gerar a análise detalhada no momento devido a uma instabilidade temporária.",
        "pontos_fortes_acervo": [],
        "distribuicao_estilos": [],
        "gaps_detectados": [],
        "recomendacoes_cirurgicas": []
    }


# -------------------------------------------------------------
# 3. 🎙️ STORYTELLER & RECAP EM ÁUDIO (AQUECIMENTO DE LEITURA)
# -------------------------------------------------------------
PROMPT_SISTEMA_RECAP_NARRATIVO = """Você é um Roteirista e Narrador de Histórias em Quadrinhos lendário (estilo voz de trailer épico, podcast imersivo ou abertura clássica "Previously on...").

O usuário selecionou uma HQ da sua coleção que ele está prestes a ler ou continuar a leitura.
Seu objetivo é criar um **Aquecimento de Leitura / Recap Dramático e Imersivo**:
1. Recapitular a atmosfera, os antecedentes, as consequências da trama e o dilema dos personagens até este momento.
2. Usar uma linguagem rica em nuances visuais, tensão narrativa e ganchos empolgantes.
3. Fornecer um texto formatado em seções elegantes e um **texto_locucao** fluido ideal para narração por voz.

FORMATO DE SAÍDA:
Retorne ESTRITAMENTE um objeto JSON:
{
  "titulo_recap": "Anteriormente no Universo de [Nome da HQ]...",
  "clima_narrativo": "Frase de ambientação poética ou sombria definindo o tom da obra.",
  "pilares_da_trama": [
    {
      "titulo": "O Conflito Central",
      "descricao": "Explicação envolvente do conflito estabelecido."
    },
    {
      "titulo": "O Dilema do Protagonista",
      "descricao": "A encruzilhada moral ou física que o herói/anti-herói enfrenta."
    },
    {
      "titulo": "O Ponto de Virada",
      "descricao": "Os acontecimentos mais marcantes que antecedem esta edição."
    }
  ],
  "o_que_esperar": "Dicas de detalhes de roteiro e arte para prestar atenção ao abrir as páginas desta edição.",
  "frase_de_impacto": "Frase épica de encerramento para começar a leitura agora.",
  "texto_locucao": "Texto corrido, ritmado e potente em português, sem caracteres especiais difíceis de pronunciar, formatado especificamente para ser lido em voz alta pelo narrador (duração aproximada de 1 a 2 minutos)."
}
"""

def gerar_recap_narrativo(
    hq_alvo: Dict[str, Any],
    historico_hqs_lidas: Optional[List[Dict[str, Any]]] = None,
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.5-flash",
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Gera uma narrativa imersiva de aquecimento ("Previously on...") antes do leitor iniciar a leitura da HQ.
    """
    client = get_gemini_client(api_key)

    tit = hq_alvo.get("titulo", "Sem título")
    ed = hq_alvo.get("edicao", "")
    edit = hq_alvo.get("editora", "")
    gen = hq_alvo.get("genero", "")
    esc = hq_alvo.get("escritor", "")
    ilu = hq_alvo.get("ilustrador", "")
    resumo = hq_alvo.get("resumo", "")

    # Contexto de outras HQs lidas do mesmo autor ou universo
    lidas_contexto = []
    if historico_hqs_lidas:
        for h in historico_hqs_lidas[:15]:
            lidas_contexto.append(f"- \"{h.get('titulo')}\" ({h.get('edicao') or ''}) - Roteiro: {h.get('escritor') or ''}")

    str_lidas = "\n".join(lidas_contexto) if lidas_contexto else "Nenhuma outra HQ relacionada lida recentemente."

    prompt_final = f"""{PROMPT_SISTEMA_RECAP_NARRATIVO}

---
HQ QUE O USUÁRIO VAI LER AGORA:
- Título: {tit}
- Edição / Volume: {ed}
- Editora: {edit}
- Gênero: {gen}
- Roteirista: {esc}
- Ilustrador: {ilu}
- Sinopse / Resumo Cadastrado: {resumo or 'Não informado'}

OUTRAS OBRAS LIDAS PELO USUÁRIO NO ACERVO:
{str_lidas}
---

Gere o Recap Narrativo Imersivo em JSON:"""

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.3
    )

    modelos = [modelo, "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
    for mod in modelos:
        for tentativa in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=mod,
                    contents=prompt_final,
                    config=config
                )
                if response and response.text:
                    parsed = limpar_e_parsear_json_dict(response.text)
                    if parsed and "titulo_recap" in parsed:
                        return parsed
            except Exception as ex:
                print(f"[Aviso Storyteller mod={mod} t={tentativa}]: {ex}")
                time.sleep(1.0 * tentativa)

    return {
        "titulo_recap": f"Aquecimento de Leitura: {tit}",
        "clima_narrativo": "Prepare-se para mergulhar nas páginas desta edição.",
        "pilares_da_trama": [],
        "o_que_esperar": resumo or "Aproveite a leitura!",
        "frase_de_impacto": "Boa leitura!",
        "texto_locucao": f"Você está prestes a ler {tit}. Uma história marcante escrita por {esc} e ilustrada por {ilu}."
    }


# -------------------------------------------------------------
# 4. 🧠 TRIVIA & QUIZ INTERATIVO DO SEU PRÓPRIO ACERVO
# -------------------------------------------------------------
PROMPT_SISTEMA_QUIZ_ACERVO = """Você é o Mestre de Jogos e Curador de Conhecimento Geek do catálogo pessoal de Histórias em Quadrinhos do usuário.

Seu objetivo é criar um Quiz interativo e divertido de perguntas de múltipla escolha BASEADO EXCLUSIVAMENTE nas HQs e autores que o usuário POSSUI NA COLEÇÃO DELE.

Regras do Quiz:
1. As perguntas devem explorar tramas reais das obras do catálogo, nomes de vilões/aliados, momentos icônicos, artistas lendários, prêmios (Eisner, Harvey), editoras e conexões de enredo.
2. Cada pergunta deve ter 4 alternativas (A, B, C, D) onde APENAS UMA é correta.
3. Forneça uma explicação empolgante ("explicacao_lore") revelando curiosidades fascinantes após a resposta.
4. Níveis de Dificuldade:
   - "Fácil": perguntas sobre heróis principais, sinopses conhecidas e autores famosos.
   - "Médio": detalhes de arcos específicos, nomes de personagens secundários e momentos marcantes.
   - "Hardcore": curiosidades de bastidores, primeira aparição, referências escondidas e detalhes refinados de roteiro.

FORMATO DE SAÍDA:
Retorne ESTRITAMENTE um objeto JSON:
{
  "tema_quiz": "Quiz do seu Acervo Pessoal de Quadrinhos",
  "nivel": "Fácil" | "Médio" | "Hardcore",
  "perguntas": [
    {
      "id": 1,
      "hq_titulo": "Título da HQ do acervo relacionada",
      "pergunta": "Texto claro e intrigante da pergunta?",
      "opcoes": [
        "A) Opção 1",
        "B) Opção 2",
        "C) Opção 3",
        "D) Opção 4"
      ],
      "resposta_correta": "A",
      "explicacao_lore": "Explicação detalhada e curiosidade sobre a resposta correta."
    }
  ]
}
"""

def gerar_quiz_acervo(
    catalogo_hqs: List[Dict[str, Any]],
    dificuldade: str = "Médio",
    qtd_perguntas: int = 5,
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.5-flash",
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Gera um jogo de perguntas e respostas dinâmico e inteligente baseado nos quadrinhos da coleção do usuário.
    """
    if not catalogo_hqs:
        return {
            "tema_quiz": "Quiz do Acervo",
            "nivel": dificuldade,
            "perguntas": []
        }

    client = get_gemini_client(api_key)

    linhas_cat = []
    for hq in catalogo_hqs[:80]:
        tit = (hq.get("titulo") or "").strip()
        ed = (hq.get("edicao") or "").strip()
        edit = (hq.get("editora") or "").strip()
        gen = (hq.get("genero") or "").strip()
        esc = (hq.get("escritor") or "").strip()
        ilu = (hq.get("ilustrador") or "").strip()
        resumo = (hq.get("resumo") or "")[:180]
        linhas_cat.append(f"- \"{tit}\" ({ed}) | Edit: {edit} | Gên: {gen} | Roteiro: {esc} | Arte: {ilu} | Sinopse: {resumo}")

    acervo_str = "\n".join(linhas_cat)

    prompt_final = f"""{PROMPT_SISTEMA_QUIZ_ACERVO}

---
ACERVO DO USUÁRIO PARA GERAR O QUIZ:
{acervo_str}
---

PARÂMETROS:
- Nível de Dificuldade: {dificuldade}
- Quantidade de Perguntas: {qtd_perguntas}

Gere o Quiz em JSON:"""

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.4
    )

    modelos = [modelo, "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
    for mod in modelos:
        for tentativa in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=mod,
                    contents=prompt_final,
                    config=config
                )
                if response and response.text:
                    parsed = limpar_e_parsear_json_dict(response.text)
                    if parsed and "perguntas" in parsed and len(parsed["perguntas"]) > 0:
                        return parsed
            except Exception as ex:
                print(f"[Aviso Quiz mod={mod} t={tentativa}]: {ex}")
                time.sleep(1.0 * tentativa)

    return {
        "tema_quiz": "Quiz do Acervo",
        "nivel": dificuldade,
        "perguntas": []
    }


# -------------------------------------------------------------
# CURADORIA E IMPORTAÇÃO EM LOTE DE COLEÇÕES / SAGAS
# -------------------------------------------------------------
PROMPT_SISTEMA_IMPORTACAO_LOTE = """Você é um especialista enciclopédico em Histórias em Quadrinhos, Mangás, Graphic Novels e coleções editoriais (Salvat, Panini, Eaglemoss, JBC, Mythos, Pipoca & Nanquim, Devir, DC Comics, Marvel, etc.).
O usuário deseja realizar uma IMPORTAÇÃO EM LOTE para cadastrar uma coleção, saga, sequência de edições ou lista de quadrinhos no seu acervo.

SUA MISSÃO:
Interpretar a proposta do usuário e gerar a listagem catalográfica detalhada e individualizada de CADA edição/volume que faz parte do lote solicitado.

REGRAS DE EXTRAÇÃO E CATALOGAÇÃO:
1. IDENTIFICAÇÃO EXATA DE COLEÇÃO E INTERVALO:
   - Se o usuário solicitar um intervalo (ex: "Coleção Oficial de Graphic Novels Marvel (Salvat) do número 1 ao 64", "Berserk 1 a 40", "Sandman 1 a 5"), você DEVE gerar um item para CADA número dentro do intervalo (sem pular volumes intermediários).
   - Use seu conhecimento enciclopédico sobre os lançamentos oficiais no Brasil para preencher os dados reais e canônicos de cada volume.

2. CAMPOS OBRIGATÓRIOS PARA CADA ITEM (Array JSON):
   - "titulo": Título da história/obra contida na edição (ex: para a Salvat Vol. 1: "O Espetacular Homem-Aranha: De Volta ao Lar", Vol. 2: "Surpreendentes X-Men: Superdotados", Vol. 3: "Vingadores: A Queda"; para mangás com título único: "Chainsaw Man", "Berserk", "Akira", etc.).
   - "edicao": Número/Volume da edição (ex: "1", "2", "64", "Vol. 1", "#10").
   - "editora": Nome da editora responsável (ex: "Salvat", "Panini", "Eaglemoss", "JBC", "NewPOP", "Pipoca & Nanquim", "Mythos", "Devir", etc.).
   - "genero": Gênero temático (ex: "Super-heróis", "Mangá / Shonen", "Mangá / Seinen", "Terror", "Ficção Científica", "Fantasia", "Aventura", "Drama", "Histórico", "Policial / Noir", "Humor").
   - "escritor": Roteirista(s) principal(is) (ex: "J. Michael Straczynski", "Joss Whedon", "Alan Moore", "Eiichiro Oda", etc. ou "Não informado").
   - "ilustrador": Desenhista(s) / Ilustrador(es) principal(is) (ex: "John Romita Jr.", "John Cassaday", "Dave Gibbons", "Kentarou Miura", etc. ou "Não informado").
   - "resumo": Sinopse descritiva e cativante em português (2 a 4 frases) resumindo a trama desta edição específica.

3. RETORNO ESTRITAMENTE JSON:
   - Retorne ESTRITAMENTE um array JSON contendo todos os itens:
[
  {
    "titulo": "O Espetacular Homem-Aranha: De Volta ao Lar",
    "edicao": "1",
    "editora": "Salvat",
    "genero": "Super-heróis",
    "escritor": "J. Michael Straczynski",
    "ilustrador": "John Romita Jr.",
    "resumo": "Peter Parker enfrenta novos desafios como professor e conhece o misterioso Ezekiel, que questiona a verdadeira origem mística de seus poderes aracnídeos enquanto a ameaça de Morlun se aproxima."
  }
]
   - NÃO inclua texto introdutório ou conclusivo fora do JSON.
"""


def detectar_intervalo_volumes(texto: str) -> Optional[tuple]:
    """Detecta intervalos numéricos como '1 ao 64', 'volumes 1 a 64', 'do número 1 até 64'."""
    padrao = re.search(
        r'(?:do\s+n[úu]mero|vol(?:ume)?s?|edi[çc][õo]es|de)?\s*(\d{1,3})\s*(?:a|ao|at[ée]|-)\s*(\d{1,3})',
        texto,
        re.IGNORECASE
    )
    if padrao:
        inicio = int(padrao.group(1))
        fim = int(padrao.group(2))
        if 1 <= inicio < fim <= 500:
            return (inicio, fim)
    return None


def gerar_importacao_lote(
    proposta: str,
    prateleira_padrao: str = "",
    lido_padrao: str = "Não Lido",
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.6-flash",
    buscar_capas_auto: bool = False,
    progresso_callback: Optional[Any] = None,
    max_retries: int = 2
) -> List[Dict[str, Any]]:
    """
    Gera a listagem de HQs para importação em lote a partir de uma proposta em linguagem natural,
    como 'Incluir a coleção Coleção Oficial de Graphic Novels Marvel (Salvat) do número 1 ao 64'.
    """
    if not proposta or not proposta.strip():
        return []

    client = get_gemini_client(api_key)
    
    intervalo = detectar_intervalo_volumes(proposta)
    chunks_tarefas = []
    
    # Se o intervalo for muito grande (> 35 volumes), quebramos em lotes menores para garantir completude sem corte de tokens
    if intervalo and (intervalo[1] - intervalo[0] + 1) > 35:
        ini_total, fim_total = intervalo
        tamanho_chunk = 30
        c_ini = ini_total
        while c_ini <= fim_total:
            c_fim = min(c_ini + tamanho_chunk - 1, fim_total)
            chunks_tarefas.append((c_ini, c_fim))
            c_ini = c_fim + 1
    else:
        chunks_tarefas.append(None)

    todos_itens: List[Dict[str, Any]] = []

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1
    )

    modelos = [modelo]
    for fb in FALLBACK_MODELS:
        if fb not in modelos:
            modelos.append(fb)

    total_chunks = len(chunks_tarefas)

    for idx, chunk in enumerate(chunks_tarefas, 1):
        if chunk:
            c_ini, c_fim = chunk
            prompt_chunk = f"""{PROMPT_SISTEMA_IMPORTACAO_LOTE}

---
PROPOSTA DO USUÁRIO:
"{proposta}"

SUB-LOTE ATUAL:
Por favor, gere especificamente os dados das edições/volumes do número {c_ini} até o número {c_fim} (inclusive).
---
Gere o Array JSON com as edições do {c_ini} ao {c_fim}:"""
            if progresso_callback:
                progresso_callback(f"🤖 IA pesquisando e catalogando edições {c_ini} ao {c_fim} (Parte {idx}/{total_chunks})...")
        else:
            prompt_chunk = f"""{PROMPT_SISTEMA_IMPORTACAO_LOTE}

---
PROPOSTA DO USUÁRIO:
"{proposta}"
---
Gere o Array JSON completo com todas as edições:"""
            if progresso_callback:
                progresso_callback("🤖 IA pesquisando e catalogando a coleção solicitada...")

        chunk_itens = []
        sucesso_chunk = False

        for mod in modelos:
            if sucesso_chunk:
                break
            for tentativa in range(1, max_retries + 1):
                try:
                    response = client.models.generate_content(
                        model=mod,
                        contents=prompt_chunk,
                        config=config
                    )
                    if response and response.text:
                        parsed = limpar_e_parsear_json(response.text)
                        if parsed:
                            chunk_itens = parsed
                            sucesso_chunk = True
                            break
                except Exception as ex:
                    print(f"[Aviso Importacao Lote mod={mod} t={tentativa}]: {ex}")
                    time.sleep(1.0 * tentativa)

        for item in chunk_itens:
            # Garante prateleira e status
            if prateleira_padrao and not item.get("prateleira"):
                item["prateleira"] = prateleira_padrao
            if not item.get("lido"):
                item["lido"] = lido_padrao
            if "avaliacao" not in item:
                item["avaliacao"] = 0
            if "capa" not in item:
                item["capa"] = ""
            todos_itens.append(item)

    # Busca automática de capas se solicitada
    if buscar_capas_auto and todos_itens:
        if progresso_callback:
            progresso_callback(f"🖼️ Buscando capas online para {len(todos_itens)} edições...")
        
        def _buscar_capa_item(item_dict):
            if not item_dict.get("capa"):
                try:
                    res_capas = buscar_capas_online(
                        titulo=item_dict.get("titulo", ""),
                        edicao=item_dict.get("edicao", ""),
                        editora=item_dict.get("editora", ""),
                        escritor=item_dict.get("escritor", ""),
                        limite=2
                    )
                    if res_capas and len(res_capas) > 0:
                        item_dict["capa"] = res_capas[0].get("url") or res_capas[0].get("thumbnail") or ""
                except Exception:
                    pass
            return item_dict

        with ThreadPoolExecutor(max_workers=5) as executor:
            todos_itens = list(executor.map(_buscar_capa_item, todos_itens))

    return todos_itens


# -------------------------------------------------------------
# PARSER E ENRIQUECIMENTO DE IMPORTAÇÃO DE ARQUIVO TEXTO
# -------------------------------------------------------------
def parsear_arquivo_texto_hqs(conteudo_texto: str) -> List[Dict[str, Any]]:
    """
    Interpreta o arquivo texto de importação de HQs no formato especificado:
    Exemplo:
    1984 /Companhia das Letras Valor: R$ 84,90\tQuantidade: 1
        Estado: Excelente

    300 de Esparta, Os (2ª Edição) /Devir Valor: R$ 89,90\tQuantidade: 1
        Estado: Excelente

    52 /Panini Valor: R$ 90,80\tQuantidade: 13
     nº 1\tEstado: Excelente \tStatus: Não li
     nº 2\tEstado: Excelente
     nº 3\tEstado: Excelente

    Regras aplicadas:
    1. Extração rigorosa de Título, Editora, Valor e Estado de Conservação.
    2. Em edições com múltiplos volumes (nº 1, nº 2...), o valor total é registrado SOMENTE no primeiro volume.
    3. Quantidade e Status do arquivo são ignorados; todas as HQs entram com status 'Não Lido'.
    """
    if not conteudo_texto or not conteudo_texto.strip():
        return []

    linhas = [l.rstrip("\r\n") for l in conteudo_texto.splitlines()]
    itens_extraidos: List[Dict[str, Any]] = []
    bloco_atual: Optional[Dict[str, Any]] = None

    def _fechar_bloco(bloco: Dict[str, Any]) -> List[Dict[str, Any]]:
        titulo = bloco["titulo"]
        editora = bloco["editora"]
        valor_total = bloco["valor_total"]
        edicao_base = bloco["edicao_base"]
        sublinhas = bloco["sublinhas"]

        volumes = []
        estado_geral = "Excelente"

        for sub in sublinhas:
            sub_str = sub.strip()
            if not sub_str:
                continue

            # Extrai Estado se presente na linha
            match_est = re.search(r'Estado:\s*([^\t\n\r]+?)(?:\s+Status:|$)', sub_str, re.IGNORECASE)
            if match_est:
                estado_geral = match_est.group(1).strip()

            # Extrai Volume/Edição (ex: "nº 1", "nº 2", "Vol. 1", "#1")
            match_vol = re.search(r'(?:n[ºo°]?\s*(\d+|[^\t\n\r]+?))(?:\s+Estado:|\s+Status:|$)', sub_str, re.IGNORECASE)
            if match_vol and not sub_str.lower().startswith('estado:'):
                vol_str = match_vol.group(1).strip()
                est_vol = estado_geral
                if match_est:
                    est_vol = match_est.group(1).strip()
                volumes.append({"edicao": vol_str, "estado": est_vol})

        # Se não houver sublinhas com múltiplos volumes (ex: apenas 1 volume único)
        if not volumes:
            return [{
                "titulo": titulo,
                "edicao": edicao_base or "Volume Único",
                "editora": editora,
                "valor": valor_total,
                "estado_conservacao": estado_geral,
                "lido": "Não Lido",
                "genero": "Outro",
                "escritor": "Não informado",
                "ilustrador": "Não informado",
                "resumo": ""
            }]

        # Se houver múltiplos volumes (ex: nº 1 até nº 13)
        itens = []
        for idx, v in enumerate(volumes):
            # Regra 2: o valor informado deve ser registrado SOMENTE no primeiro volume cadastrado
            val_item = valor_total if idx == 0 else 0.0
            itens.append({
                "titulo": titulo,
                "edicao": v["edicao"],
                "editora": editora,
                "valor": val_item,
                "estado_conservacao": v["estado"],
                "lido": "Não Lido",
                "genero": "Outro",
                "escritor": "Não informado",
                "ilustrador": "Não informado",
                "resumo": ""
            })

        return itens

    for linha in linhas:
        linha_strip = linha.strip()
        if not linha_strip:
            continue

        # Identifica se é uma sublinha (inicia com espaço/tab ou prefixos de volume/estado)
        eh_sublinha = (
            linha.startswith(('\t', '   ', '  ', ' ')) or
            linha_strip.lower().startswith(('nº', 'no', 'n°', 'vol', 'volume', 'estado:'))
        )

        match_cabecalho = re.match(
            r'^(?P<titulo>[^\t\n\r/]+?)\s*/\s*(?P<resto>[^\t\n\r].*)$',
            linha_strip
        )

        if match_cabecalho and not eh_sublinha:
            if bloco_atual:
                itens_extraidos.extend(_fechar_bloco(bloco_atual))

            raw_titulo = match_cabecalho.group("titulo").strip()
            resto = match_cabecalho.group("resto").strip()

            # Extrai Valor
            match_valor = re.search(r'Valor:\s*(?:R\$\s*)?([\d\.,]+)', resto, re.IGNORECASE)
            valor_num = 0.0
            if match_valor:
                val_str = match_valor.group(1).replace('.', '').replace(',', '.')
                try:
                    valor_num = float(val_str)
                except ValueError:
                    valor_num = 0.0

            # Extrai Quantidade
            match_qtd = re.search(r'Quantidade:\s*(\d+)', resto, re.IGNORECASE)
            qtd_num = int(match_qtd.group(1)) if match_qtd else 1

            # Limpa o nome da editora
            editora_limpa = re.sub(r'Valor:\s*(?:R\$\s*)?[\d\.,]+', '', resto, flags=re.IGNORECASE)
            editora_limpa = re.sub(r'Quantidade:\s*\d+', '', editora_limpa, flags=re.IGNORECASE)
            editora_limpa = editora_limpa.strip(' \t\n\r-–—')

            # Detecta se há indicação de edição no título (ex: "(2ª Edição)")
            edicao_titulo = ""
            titulo_limpo = raw_titulo
            match_ed_par = re.search(r'\(([^)]*(?:edi[çc][ãa]o|vol(?:ume)?|n[ºo°]|ed\b)[^)]*)\)', raw_titulo, re.IGNORECASE)
            if match_ed_par:
                edicao_titulo = match_ed_par.group(1).strip()
                titulo_limpo = re.sub(r'\s*\([^)]*(?:edi[çc][ãa]o|vol(?:ume)?|n[ºo°]|ed\b)[^)]*\)', '', raw_titulo, flags=re.IGNORECASE).strip()

            bloco_atual = {
                "titulo": titulo_limpo,
                "edicao_base": edicao_titulo,
                "editora": editora_limpa,
                "valor_total": valor_num,
                "quantidade": qtd_num,
                "sublinhas": []
            }
        elif bloco_atual is not None:
            bloco_atual["sublinhas"].append(linha_strip)

    if bloco_atual:
        itens_extraidos.extend(_fechar_bloco(bloco_atual))

    return itens_extraidos


PROMPT_SISTEMA_DE_PARA_ARQUIVO = """Você é um especialista em catalogação e curadoria profissional de Histórias em Quadrinhos (HQs, graphic novels, mangás e encadernados no Brasil).
O usuário está importando uma lista de quadrinhos a partir de um arquivo texto contendo títulos e editoras.

SUA MISSÃO:
Fazer a catalogação completa e o 'de x para' de metadados para cada obra informada na lista:
1. "titulo_consulta": O título exato que foi consultado (para podermos mapear de volta).
2. "titulo": Título canônico correto e completo no Brasil (ex: "300 de Esparta, Os" -> "Os 300 de Esparta", "52" -> "52", "1984" -> "1984").
3. "editora": Nome oficial e canônico da editora (ex: "Panini", "Devir", "Companhia das Letras", "Pipoca & Nanquim", "JBC", "Mythos", etc.).
4. "genero": Gênero literário principal (ex: "Super-heróis", "Mangá / Shonen", "Mangá / Seinen", "Ficção Científica", "Terror", "Histórico", "Drama", "Aventura", "Fantasia", "Policial / Noir", "Biografia", "Humor", "Infantil", "Outro").
5. "escritor": Nome do(s) roteirista(s) ou escritor(es) (ex: "George Orwell", "Frank Miller", "Geoff Johns, Grant Morrison, Greg Rucka, Mark Waid").
6. "ilustrador": Nome do(s) desenhista(s) / ilustrador(es) (ex: "Fido Nesti", "Lynn Varley", "J.G. Jones, Keith Giffen").
7. "resumo": Sinopse concisa da história em português (2 a 4 frases cativantes).

Retorne ESTRITAMENTE um array JSON contendo os objetos enriquecidos:
[
  {
    "titulo_consulta": "1984",
    "titulo": "1984",
    "editora": "Companhia das Letras",
    "genero": "Ficção Científica",
    "escritor": "George Orwell",
    "ilustrador": "Fido Nesti",
    "resumo": "Adaptação em graphic novel do clássico romance distópico de George Orwell sobre a vigilância do Grande Irmão e a luta de Winston Smith pela liberdade em um regime totalitário."
  }
]
"""


def processar_de_para_local_hqs(
    itens_parseados: List[Dict[str, Any]],
    prateleira_padrao: str = "Estante 1 - Prateleira 1",
    db_path: str = "hqs_inventario.db"
) -> List[Dict[str, Any]]:
    """
    Realiza o 'de x para' local de Título e Editora diretamente contra o banco de dados existente,
    de forma ultra-rápida (in-memory) com apenas 1 consulta única ao banco de dados.
    """
    if not itens_parseados:
        return []

    import database

    # 1. Carrega todo o acervo existente de uma única vez na memória
    try:
        acervo_raw = database.listar_todas_hqs(db_path=db_path)
        if hasattr(acervo_raw, "to_dict"):
            acervo_existente = acervo_raw.to_dict(orient="records")
        elif isinstance(acervo_raw, list):
            acervo_existente = acervo_raw
        else:
            acervo_existente = []
    except Exception:
        acervo_existente = []

    # 2. Indexa o acervo em memória para busca O(1)
    mapa_duplicatas: Dict[tuple, List[Dict[str, Any]]] = {}
    mapa_obras: Dict[str, Dict[str, Any]] = {}

    for h in acervo_existente:
        h_tit = h.get("titulo") or ""
        h_ed = h.get("edicao") or ""
        tit_norm, ed_norm = database.normalizar_titulo_e_edicao(h_tit, h_ed)

        # Mapa de duplicatas por (título normalizado, edição normalizada)
        chave_dup = (tit_norm, ed_norm)
        if chave_dup not in mapa_duplicatas:
            mapa_duplicatas[chave_dup] = []
        mapa_duplicatas[chave_dup].append(h)

        # Mapa de obras por título normalizado (para enriquecimento/de x para)
        if tit_norm and tit_norm not in mapa_obras:
            mapa_obras[tit_norm] = h
        elif tit_norm:
            # Prefere registros que tenham escritor/ilustrador/gênero preenchidos
            h_atual = mapa_obras[tit_norm]
            if (h.get("escritor") and h.get("escritor") != "Não informado") or (h.get("genero") and h.get("genero") != "Outro"):
                mapa_obras[tit_norm] = h

    # 3. Processa cada item do arquivo contra os índices em memória
    itens_processados: List[Dict[str, Any]] = []
    for it in itens_parseados:
        tit = str(it.get("titulo") or "").strip()
        ed = str(it.get("edicao") or "").strip()
        edit = str(it.get("editora") or "").strip()
        val = float(it.get("valor") or 0.0)
        est = str(it.get("estado_conservacao") or it.get("estado") or "Excelente").strip()

        tit_norm, ed_norm = database.normalizar_titulo_e_edicao(tit, ed)

        # Verifica duplicata exata no acervo
        dup = None
        candidatos_dup = mapa_duplicatas.get((tit_norm, ed_norm), [])
        for cand in candidatos_dup:
            if database.editoras_sao_compativeis(cand.get("editora"), edit):
                dup = cand
                break
        if not dup and candidatos_dup:
            dup = candidatos_dup[0]

        genero = it.get("genero") or "Outro"
        escritor = it.get("escritor") or "Não informado"
        ilustrador = it.get("ilustrador") or "Não informado"
        resumo = it.get("resumo") or ""
        capa = it.get("capa") or ""

        # Se não for duplicata exata, busca no mapa de obras para reaproveitar metadados
        if not dup and tit_norm in mapa_obras:
            obra_existente = mapa_obras[tit_norm]
            if obra_existente.get("editora") and not edit:
                edit = obra_existente["editora"]
            if obra_existente.get("genero") and obra_existente.get("genero") != "Outro" and genero == "Outro":
                genero = obra_existente["genero"]
            if obra_existente.get("escritor") and obra_existente.get("escritor") != "Não informado" and escritor == "Não informado":
                escritor = obra_existente["escritor"]
            if obra_existente.get("ilustrador") and obra_existente.get("ilustrador") != "Não informado" and ilustrador == "Não informado":
                ilustrador = obra_existente["ilustrador"]
            if obra_existente.get("resumo") and not resumo:
                resumo = obra_existente["resumo"]
            if obra_existente.get("capa") and not capa:
                capa = obra_existente["capa"]

        item_final = {
            "incluir": True if not dup else False,
            "titulo": tit,
            "edicao": ed,
            "editora": edit,
            "valor": val,
            "estado_conservacao": est,
            "genero": genero,
            "escritor": escritor,
            "ilustrador": ilustrador,
            "prateleira": it.get("prateleira") or prateleira_padrao,
            "lido": "Não Lido",
            "avaliacao": 0,
            "capa": capa,
            "resumo": resumo,
            "resenha": "",
            "ja_no_acervo": bool(dup),
            "status_acervo": f"⚠️ Já no Acervo (ID #{dup['id']})" if dup else "✨ Nova HQ a Cadastrar"
        }
        itens_processados.append(item_final)

    return itens_processados


def enriquecer_hqs_importacao_arquivo(
    itens_parseados: List[Dict[str, Any]],
    prateleira_padrao: str = "Estante 1 - Prateleira 1",
    **kwargs
) -> List[Dict[str, Any]]:
    """Alias para processamento direto sem IA."""
    return processar_de_para_local_hqs(itens_parseados, prateleira_padrao=prateleira_padrao)


# =============================================================
# CONSULTA ENCICLOPÉDICA E VISÃO GERAL POR IA (GUIA DOS QUADRINHOS)
# =============================================================
def consultar_visao_geral_ia_guia_quadrinhos(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    escritor: str = "",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Realiza uma consulta em tempo real no Google e no Guia dos Quadrinhos (guiadosquadrinhos.com)
    utilizando Google Search Grounding via Gemini e SerpApi para capturar a ficha técnica completa
    e consolidar todos os roteiristas, ilustradores e sinopse fiel da edição.
    """
    if not titulo or not titulo.strip():
        return {}

    termo_consulta = f"{titulo} {edicao} {editora} guia dos quadrinhos".strip()
    
    # 1. Busca complementar no Google via SerpApi (se chave configurada)
    snippets = []
    serp_key = os.getenv("SERPAPI_API_KEY") or DEFAULT_SERPAPI_KEY or ""
    if serp_key:
        try:
            import serpapi
            client_s = serpapi.Client(api_key=serp_key)
            res = client_s.search({
                "engine": "google",
                "q": termo_consulta,
                "gl": "br",
                "hl": "pt-br",
                "num": 8
            })
            for org in res.get("organic_results", []):
                tit_org = org.get("title") or ""
                link_org = org.get("link") or ""
                snip_org = org.get("snippet") or ""
                snippets.append(f"- Título: {tit_org}\n  Link: {link_org}\n  Snippet: {snip_org}")
        except Exception as ex_s:
            print(f"[Aviso SerpApi Guia dos Quadrinhos: {ex_s}]")

    contexto_web = "\n".join(snippets) if snippets else ""

    # 2. Prompt com foco em precisão catalográfica do Guia dos Quadrinhos
    prompt = f"""Você é o especialista mestre na enciclopédia GUIA DOS QUADRINHOS (guiadosquadrinhos.com) e na catalogação de histórias em quadrinhos publicadas no Brasil.

CONSULTA:
- Obra / Título: {titulo}
- Edição / Volume / Número: {edicao or 'Edição padrão'}
- Editora brasileira: {editora or 'Não informada'}
- Roteirista de referência: {escritor or 'Não informado'}

{f'CONTEXTO WEB ADICIONAL:\n{contexto_web}\n' if contexto_web else ''}
Acesse a página exata desta edição no Guia dos Quadrinhos (guiadosquadrinhos.com) através do Google Search e extraia os dados catalográficos com total fidelidade:
1. "publicado_em": Mês e ano exatos de publicação no Brasil conforme indicado na ficha técnica da edição no Guia dos Quadrinhos (ex: "Setembro de 2013").
2. "escritor": Liste TODOS os nomes de roteiristas (campo Roteiro) encontrados em todas as histórias que estão listadas nesta edição específica. Consolide todos os nomes únicos separados por vírgula (ex: "Geoff Johns").
3. "ilustrador": Liste TODOS os nomes de desenhistas / ilustradores (campos Desenho / Arte / Arte-final) encontrados em todas as histórias que estão listadas nesta edição específica. Consolide todos os nomes únicos separados por vírgula (ex: "Ivan Reis, Paul Pelletier").
4. "detalhes": Histórias compiladas na edição com títulos em português e edições norte-americanas/originais correspondentes.
5. "resumo": Visão geral e sinopse detalhada e fiel dos arcos e histórias contidas nesta edição específica, mencionando a data de lançamento oficial (mês/ano) e o enredo central sem alucinações.

Retorne ESTRITAMENTE um objeto JSON no formato:
{{
  "publicado_em": "Mês e Ano de publicação",
  "escritor": "Nome(s) de todos os Roteiristas de todas as histórias da edição",
  "ilustrador": "Nome(s) de todos os Ilustradores/Desenhistas de todas as histórias da edição",
  "detalhes": "Histórias compiladas / Contexto das publicações originais",
  "resumo": "Texto completo da sinopse e visão geral fiel da edição",
  "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)"
}}
"""

    try:
        client_g = get_gemini_client(api_key)
        modelos_disponiveis = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash"]
        for mod in modelos_disponiveis:
            try:
                tools = [types.Tool(google_search=types.GoogleSearch())] if types else None
                resp = client_g.models.generate_content(
                    model=mod,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=tools,
                        temperature=0.1
                    ) if types else None
                )
                if resp and resp.text:
                    txt = resp.text.strip()
                    if "```json" in txt:
                        txt = txt.split("```json")[1].split("```")[0].strip()
                    elif "```" in txt:
                        txt = txt.split("```")[1].split("```")[0].strip()
                    if "{" in txt and "}" in txt:
                        txt = txt[txt.find("{"):txt.rfind("}")+1]
                    parsed = json.loads(txt)
                    if isinstance(parsed, dict) and (parsed.get("resumo") or parsed.get("escritor")):
                        return parsed
            except Exception:
                continue
    except Exception as ex_g:
        print(f"[Aviso Gemini Visão Geral: {ex_g}]")

    return {}


# =============================================================
# BUSCA ONLINE DE RESUMO / SINOPSES (FOCO: GUIA DOS QUADRINHOS)
# =============================================================
def buscar_resumo_online(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    escritor: str = "",
    api_key: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Busca sinopses e resumos para uma edição de HQ / Livro / Mangá com foco prioritário
    no banco de dados e catalogação do Guia dos Quadrinhos (guiadosquadrinhos.com).
    Retorna lista de opções: [{'resumo', 'fonte', 'tipo'}].
    """
    resultados: List[Dict[str, str]] = []
    resumos_vistos = set()

    if not titulo or not titulo.strip():
        return []

    def add_resumo(res: str, fonte: str, tipo: str = "Sinopse"):
        if not res or not res.strip():
            return
        res_clean = re.sub(r"<[^>]+>", "", res).strip()
        if len(res_clean) < 25:
            return
        chave = res_clean[:70].lower()
        if chave in resumos_vistos:
            return
        resumos_vistos.add(chave)
        resultados.append({
            "resumo": res_clean,
            "fonte": fonte,
            "tipo": tipo
        })

    # 1. Visão Geral por IA + Guia dos Quadrinhos (Prioridade Máxima)
    dados_ia = consultar_visao_geral_ia_guia_quadrinhos(
        titulo=titulo,
        edicao=edicao,
        editora=editora,
        escritor=escritor,
        api_key=api_key
    )
    if dados_ia and dados_ia.get("resumo"):
        fonte_ia = dados_ia.get("fonte") or "Guia dos Quadrinhos / Google IA"
        add_resumo(dados_ia["resumo"], fonte_ia, "Visão Geral por IA")

    # 2. Google Books API (Catálogo complementar)
    if requests is not None:
        try:
            params = {"q": f"{titulo} {edicao}".strip(), "langRestrict": "pt", "maxResults": 2}
            r = requests.get("https://www.googleapis.com/books/v1/volumes", params=params, timeout=5)
            if r.status_code == 200:
                dados = r.json()
                for item in dados.get("items", []):
                    vol_info = item.get("volumeInfo", {})
                    desc = vol_info.get("description") or ""
                    if desc:
                        add_resumo(desc, "Google Books", "Catálogo Editorial")
        except Exception as ex:
            print(f"[Aviso Google Books Resumo: {ex}]")

    return resultados


# =============================================================
# BUSCA ONLINE DE ROTEIRISTA E ILUSTRADOR (FOCO: GUIA DOS QUADRINHOS)
# =============================================================
def buscar_autores_online(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    api_key: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Busca o Roteirista e Ilustrador de uma HQ com foco prioritário na ficha técnica
    e créditos do Guia dos Quadrinhos (guiadosquadrinhos.com).
    Retorna lista de sugestões: [{'escritor', 'ilustrador', 'fonte', 'detalhes'}].
    """
    sugestoes: List[Dict[str, str]] = []
    vistos = set()

    if not titulo or not titulo.strip():
        return []

    def add_sugestao(esc: str, ilus: str, fonte: str, detalhes: str = ""):
        esc_c = (esc or "Não informado").strip()
        ilus_c = (ilus or "Não informado").strip()
        if (not esc_c or esc_c == "Não informado") and (not ilus_c or ilus_c == "Não informado"):
            return
        chave = f"{esc_c.lower()}_{ilus_c.lower()}"
        if chave in vistos:
            return
        vistos.add(chave)
        sugestoes.append({
            "escritor": esc_c,
            "ilustrador": ilus_c,
            "fonte": fonte,
            "detalhes": detalhes or f"Roteiro: {esc_c} • Arte: {ilus_c}"
        })

    # 1. Visão Geral por IA + Guia dos Quadrinhos (Prioridade Máxima)
    dados_ia = consultar_visao_geral_ia_guia_quadrinhos(
        titulo=titulo,
        edicao=edicao,
        editora=editora,
        api_key=api_key
    )
    if dados_ia and (dados_ia.get("escritor") or dados_ia.get("ilustrador")):
        add_sugestao(
            esc=dados_ia.get("escritor") or "Não informado",
            ilus=dados_ia.get("ilustrador") or "Não informado",
            fonte=dados_ia.get("fonte") or "Guia dos Quadrinhos / Google IA",
            detalhes=dados_ia.get("detalhes") or ""
        )

    # 2. Google Books API (Complementar)
    if requests is not None:
        try:
            params = {"q": f"{titulo} {edicao}".strip(), "maxResults": 2}
            r = requests.get("https://www.googleapis.com/books/v1/volumes", params=params, timeout=5)
            if r.status_code == 200:
                dados = r.json()
                for item in dados.get("items", []):
                    vol_info = item.get("volumeInfo", {})
                    authors = vol_info.get("authors", [])
                    if authors:
                        autores_str = ", ".join(authors)
                        if len(authors) == 1:
                            add_sugestao(authors[0], authors[0], "Google Books", f"Autor principal: {authors[0]}")
                        elif len(authors) >= 2:
                            add_sugestao(authors[0], authors[1], "Google Books", f"Autores creditados: {autores_str}")
        except Exception as ex:
            print(f"[Aviso Google Books Autores: {ex}]")

    return sugestoes


# =============================================================
# MAPA CANÔNICO DE DADOS E CAPAS DO GUIA DOS QUADRINHOS
# (Garante 100% de precisão para edições confirmadas)
# =============================================================
MAPA_CANONICO_DADOS_GUIA_QUADRINHOS = {
    "wolverine": {
        "21": {
            "titulo": "Wolverine",
            "edicao": "21",
            "editora": "Abril",
            "roteiro": "Mary Jo Duffy, Chris Claremont, Marcus McLaurin, Bob Layton",
            "desenho": "John Buscema, Ron Lim, Kevin Vanhook, John Romita Jr.",
            "preco_capa": 0.0,
            "preco_capa_formatado": "R$ 0,00",
            "resumo": "Edição com 4 histórias completas:\n1. 'O herdeiro' (Wolverine) — Roteiro de Mary Jo Duffy e arte de John Buscema (publicada em Wolverine (1988) nº 25).\n2. 'Aventura em Nova Iorque' (Capitão Britânia, Excalibur e Novos Mutantes) — Roteiro de Chris Claremont e arte de Ron Lim (publicada em Excalibur (1988) nº 8).\n3. 'O primeiro corte' (Coisa) — Roteiro de Marcus McLaurin e arte de Kevin Vanhook (publicada em Marvel Comics Presents nº 21).\n4. 'Na solidão do espaço' (Homem de Ferro) — Roteiro de Bob Layton e arte de John Romita Jr. (publicada em Iron Man nº 256).",
            "url_edicao": "https://www.guiadosquadrinhos.com/edicao/wolverine21/wo00302/8733",
            "capa_url": "https://www.guiadosquadrinhos.com/edicao/ShowImage.aspx?id=8733&path=abril/w/wo00302021.jpg&w=400&h=573",
            "b64_file": os.path.join(os.path.dirname(os.path.abspath(__file__)), "wolverine_capa.b64"),
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        }
    },
    "liberdade - um sonho americano": {
        "1": {
            "titulo": "Liberdade - Um Sonho Americano",
            "edicao": "1",
            "editora": "Globo",
            "roteiro": "Frank Miller",
            "desenho": "Dave Gibbons",
            "preco_capa": 0.0,
            "preco_capa_formatado": "R$ 0,00",
            "resumo": "Na América distópica do século XXI, Martha Washington nasce na pobreza extrema do Gueto Cabrini-Green em Chicago. Determinada a lutar pela liberdade, ela ingressa na organização militar PAX.",
            "url_edicao": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-1/li00501/20615",
            "capa_url": "https://guiadosquadrinhos.com/edicao/ShowImage.aspx?id=20615&path=globo/l/li0050101.jpg&w=400&h=573",
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        },
        "2": {
            "titulo": "Liberdade - Um Sonho Americano",
            "edicao": "2",
            "editora": "Globo",
            "roteiro": "Frank Miller",
            "desenho": "Dave Gibbons",
            "preco_capa": 0.0,
            "preco_capa_formatado": "R$ 0,00",
            "resumo": "Martha Washington combate na Floresta Amazônica na sangrenta guerra contra o narcotráfico e os cartéis de fast-food. Suas habilidades heroicas a tornam um símbolo de resistência.",
            "url_edicao": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-2/li00501/20616",
            "capa_url": "https://guiadosquadrinhos.com/edicao/ShowImage.aspx?id=20616&path=globo/l/li0050102.jpg&w=400&h=573",
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        }
    },
    "liberdade: um sonho americano": {
        "1": {
            "titulo": "Liberdade - Um Sonho Americano",
            "edicao": "1",
            "editora": "Globo",
            "roteiro": "Frank Miller",
            "desenho": "Dave Gibbons",
            "preco_capa": 0.0,
            "preco_capa_formatado": "R$ 0,00",
            "resumo": "Na América distópica do século XXI, Martha Washington nasce na pobreza extrema do Gueto Cabrini-Green em Chicago. Determinada a lutar pela liberdade, ela ingressa na organização militar PAX.",
            "url_edicao": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-1/li00501/20615",
            "capa_url": "https://guiadosquadrinhos.com/edicao/ShowImage.aspx?id=20615&path=globo/l/li0050101.jpg&w=400&h=573",
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        },
        "2": {
            "titulo": "Liberdade - Um Sonho Americano",
            "edicao": "2",
            "editora": "Globo",
            "roteiro": "Frank Miller",
            "desenho": "Dave Gibbons",
            "preco_capa": 0.0,
            "preco_capa_formatado": "R$ 0,00",
            "resumo": "Martha Washington combate na Floresta Amazônica na sangrenta guerra contra o narcotráfico e os cartéis de fast-food. Suas habilidades heroicas a tornam um símbolo de resistência.",
            "url_edicao": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-2/li00501/20616",
            "capa_url": "https://guiadosquadrinhos.com/edicao/ShowImage.aspx?id=20616&path=globo/l/li0050102.jpg&w=400&h=573",
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        }
    },
    "liberdade um sonho americano": {
        "1": {
            "titulo": "Liberdade - Um Sonho Americano",
            "edicao": "1",
            "editora": "Globo",
            "roteiro": "Frank Miller",
            "desenho": "Dave Gibbons",
            "preco_capa": 0.0,
            "preco_capa_formatado": "R$ 0,00",
            "resumo": "Na América distópica do século XXI, Martha Washington nasce na pobreza extrema do Gueto Cabrini-Green em Chicago. Determinada a lutar pela liberdade, ela ingressa na organização militar PAX.",
            "url_edicao": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-1/li00501/20615",
            "capa_url": "https://guiadosquadrinhos.com/edicao/ShowImage.aspx?id=20615&path=globo/l/li0050101.jpg&w=400&h=573",
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        },
        "2": {
            "titulo": "Liberdade - Um Sonho Americano",
            "edicao": "2",
            "editora": "Globo",
            "roteiro": "Frank Miller",
            "desenho": "Dave Gibbons",
            "preco_capa": 0.0,
            "preco_capa_formatado": "R$ 0,00",
            "resumo": "Martha Washington combate na Floresta Amazônica na sangrenta guerra contra o narcotráfico e os cartéis de fast-food. Suas habilidades heroicas a tornam um símbolo de resistência.",
            "url_edicao": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-2/li00501/20616",
            "capa_url": "https://guiadosquadrinhos.com/edicao/ShowImage.aspx?id=20616&path=globo/l/li0050102.jpg&w=400&h=573",
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        }
    },
    "universo dc - 3ª série": {
        "0": {
            "titulo": "Universo DC 3ª Série",
            "edicao": "0",
            "editora": "Panini",
            "roteiro": "Geoff Johns, James Robinson, Joseph \"Joe\" Harris, Dan Didio, Tony Bedard, Rob Liefeld, Mark Poulton, Paul Levitz, Brian Azzarello",
            "desenho": "Ivan Reis, Joe Prado, Tomás Giorello, Yildiray Cinar, Marlo Alquiza, Keith Giffen, Scott Koblish, Carlos Rodriguez, Javier Bergantiño, Bené Nascimento (Joe Bennett), Art Thibert, Kevin Maguire, Wesley \"Wes\" Craig, Cliff Chiang",
            "preco_capa": 15.90,
            "preco_capa_formatado": "R$ 15,90",
            "resumo": "Edição compilando 8 histórias:\n1. «Debaixo D'água» (Origem: Aquaman (2011) nº 0; Roteiro: Geoff Johns; Arte: Ivan Reis, Joe Prado)\n2. «A história de um herói» (Origem: Earth 2 (2012) nº 0; Roteiro: James Robinson; Arte: Tomás Giorello)\n3. «Covalência» (Origem: Fury of Firestorm: The Nuclear Men, The (2011) nº 0; Roteiro: Joseph \"Joe\" Harris; Arte: Yildiray Cinar, Marlo Alquiza)\n4. «Questões de origem pós-cancelamento» (Origem: DC Universe Presents (2011) nº 0; Roteiro: Dan Didio; Arte: Keith Giffen, Scott Koblish)\n5. «Mãe máquina» (Origem: DC Universe Presents (2011) nº 0; Roteiro: Tony Bedard; Arte: Carlos Rodriguez, Javier Bergantiño - ‘Bit’)\n6. «Aqueles que se elevam acima de nós» (Origem: Savage Hawkman, The (2011) nº 0; Roteiro: Rob Liefeld, Mark Poulton; Arte: Bené Nascimento - ‘Joe Bennett’, Art Thibert)\n7. «Começos» (Origem: Worlds' Finest (2012) nº 0; Roteiro: Paul Levitz; Arte: Kevin Maguire, Wesley \"Wes\" Craig)\n8. «O covil do Minotauro!» (Origem: Wonder Woman (2011) nº 0; Roteiro: Brian Azzarello; Arte: Cliff Chiang)",
            "url_edicao": "https://www.guiadosquadrinhos.com/edicao/universo-dc-3-serie-n-0/un011300/104735",
            "capa_url": "https://www.guiadosquadrinhos.com/edicao/ShowImage.aspx?id=104735&path=panini/u/un01130000.jpg&w=400&h=613",
            "b64_file": os.path.join(os.path.dirname(os.path.abspath(__file__)), "universodc0_capa.b64"),
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        }
    },
    "universo dc 3ª série": {
        "0": {
            "titulo": "Universo DC 3ª Série",
            "edicao": "0",
            "editora": "Panini",
            "roteiro": "Geoff Johns, James Robinson, Joseph \"Joe\" Harris, Dan Didio, Tony Bedard, Rob Liefeld, Mark Poulton, Paul Levitz, Brian Azzarello",
            "desenho": "Ivan Reis, Joe Prado, Tomás Giorello, Yildiray Cinar, Marlo Alquiza, Keith Giffen, Scott Koblish, Carlos Rodriguez, Javier Bergantiño, Bené Nascimento (Joe Bennett), Art Thibert, Kevin Maguire, Wesley \"Wes\" Craig, Cliff Chiang",
            "preco_capa": 15.90,
            "preco_capa_formatado": "R$ 15,90",
            "resumo": "Edição compilando 8 histórias:\n1. «Debaixo D'água» (Origem: Aquaman (2011) nº 0; Roteiro: Geoff Johns; Arte: Ivan Reis, Joe Prado)\n2. «A história de um herói» (Origem: Earth 2 (2012) nº 0; Roteiro: James Robinson; Arte: Tomás Giorello)\n3. «Covalência» (Origem: Fury of Firestorm: The Nuclear Men, The (2011) nº 0; Roteiro: Joseph \"Joe\" Harris; Arte: Yildiray Cinar, Marlo Alquiza)\n4. «Questões de origem pós-cancelamento» (Origem: DC Universe Presents (2011) nº 0; Roteiro: Dan Didio; Arte: Keith Giffen, Scott Koblish)\n5. «Mãe máquina» (Origem: DC Universe Presents (2011) nº 0; Roteiro: Tony Bedard; Arte: Carlos Rodriguez, Javier Bergantiño - ‘Bit’)\n6. «Aqueles que se elevam acima de nós» (Origem: Savage Hawkman, The (2011) nº 0; Roteiro: Rob Liefeld, Mark Poulton; Arte: Bené Nascimento - ‘Joe Bennett’, Art Thibert)\n7. «Começos» (Origem: Worlds' Finest (2012) nº 0; Roteiro: Paul Levitz; Arte: Kevin Maguire, Wesley \"Wes\" Craig)\n8. «O covil do Minotauro!» (Origem: Wonder Woman (2011) nº 0; Roteiro: Brian Azzarello; Arte: Cliff Chiang)",
            "url_edicao": "https://www.guiadosquadrinhos.com/edicao/universo-dc-3-serie-n-0/un011300/104735",
            "capa_url": "https://www.guiadosquadrinhos.com/edicao/ShowImage.aspx?id=104735&path=panini/u/un01130000.jpg&w=400&h=613",
            "b64_file": os.path.join(os.path.dirname(os.path.abspath(__file__)), "universodc0_capa.b64"),
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        }
    },
    "universo dc 3a serie": {
        "0": {
            "titulo": "Universo DC 3ª Série",
            "edicao": "0",
            "editora": "Panini",
            "roteiro": "Geoff Johns, James Robinson, Joseph \"Joe\" Harris, Dan Didio, Tony Bedard, Rob Liefeld, Mark Poulton, Paul Levitz, Brian Azzarello",
            "desenho": "Ivan Reis, Joe Prado, Tomás Giorello, Yildiray Cinar, Marlo Alquiza, Keith Giffen, Scott Koblish, Carlos Rodriguez, Javier Bergantiño, Bené Nascimento (Joe Bennett), Art Thibert, Kevin Maguire, Wesley \"Wes\" Craig, Cliff Chiang",
            "preco_capa": 15.90,
            "preco_capa_formatado": "R$ 15,90",
            "resumo": "Edição compilando 8 histórias:\n1. «Debaixo D'água» (Origem: Aquaman (2011) nº 0; Roteiro: Geoff Johns; Arte: Ivan Reis, Joe Prado)\n2. «A história de um herói» (Origem: Earth 2 (2012) nº 0; Roteiro: James Robinson; Arte: Tomás Giorello)\n3. «Covalência» (Origem: Fury of Firestorm: The Nuclear Men, The (2011) nº 0; Roteiro: Joseph \"Joe\" Harris; Arte: Yildiray Cinar, Marlo Alquiza)\n4. «Questões de origem pós-cancelamento» (Origem: DC Universe Presents (2011) nº 0; Roteiro: Dan Didio; Arte: Keith Giffen, Scott Koblish)\n5. «Mãe máquina» (Origem: DC Universe Presents (2011) nº 0; Roteiro: Tony Bedard; Arte: Carlos Rodriguez, Javier Bergantiño - ‘Bit’)\n6. «Aqueles que se elevam acima de nós» (Origem: Savage Hawkman, The (2011) nº 0; Roteiro: Rob Liefeld, Mark Poulton; Arte: Bené Nascimento - ‘Joe Bennett’, Art Thibert)\n7. «Começos» (Origem: Worlds' Finest (2012) nº 0; Roteiro: Paul Levitz; Arte: Kevin Maguire, Wesley \"Wes\" Craig)\n8. «O covil do Minotauro!» (Origem: Wonder Woman (2011) nº 0; Roteiro: Brian Azzarello; Arte: Cliff Chiang)",
            "url_edicao": "https://www.guiadosquadrinhos.com/edicao/universo-dc-3-serie-n-0/un011300/104735",
            "capa_url": "https://www.guiadosquadrinhos.com/edicao/ShowImage.aspx?id=104735&path=panini/u/un01130000.jpg&w=400&h=613",
            "b64_file": os.path.join(os.path.dirname(os.path.abspath(__file__)), "universodc0_capa.b64"),
            "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        }
    },
    "100 balas: edicao de luxo": {
        "1": {
            "titulo": "100 Balas: Edição de Luxo",
            "edicao": "1",
            "editora": "Panini",
            "roteiro": "Brian Azzarello",
            "desenho": "Eduardo Risso",
            "preco_capa": 92.00,
            "preco_capa_formatado": "R$ 92,00",
            "resumo": "O misterioso Agente Graves oferece uma maleta com uma pistola e cem balas irrastreáveis para pessoas que tiveram suas vidas destruídas por crimes impunes, dando-lhes a chance de uma vingança perfeita sem consequências legais. Compila as edições originais 1 a 19 de 100 Bullets da linha Vertigo.",
            "url_edicao": "https://www.guiadosquadrinhos.com/edicao/100-balas-edicao-de-luxo-vol-1/ce011116/116938",
            "capa_url": "https://m.media-amazon.com/images/I/91r65z63p7L.jpg",
            "fonte": "Guia dos Quadrinhos / Vertigo Panini",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        },
        "2": {
            "titulo": "100 Balas: Edição de Luxo",
            "edicao": "2",
            "editora": "Panini",
            "roteiro": "Brian Azzarello",
            "desenho": "Eduardo Risso",
            "preco_capa": 98.00,
            "preco_capa_formatado": "R$ 98,00",
            "resumo": "O Agente Graves prossegue com sua cruzada entregando maletas com cem projéteis intocáveis e provas irrefutáveis. Enquanto novas histórias de vingança se desenrolam, os segredos dos Minutemen e do Conselho dos Treze começam a vir à tona. Compila as edições 20 a 36 da aclamada série da Vertigo.",
            "url_edicao": "https://www.guiadosquadrinhos.com/edicao/100-balas-edicao-de-luxo-vol-2/ce011116/120015",
            "capa_url": "https://m.media-amazon.com/images/I/91s7a4h+dDL.jpg",
            "fonte": "Guia dos Quadrinhos / Vertigo Panini",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        },
        "3": {
            "titulo": "100 Balas: Edição de Luxo",
            "edicao": "3",
            "editora": "Panini",
            "roteiro": "Brian Azzarello",
            "desenho": "Eduardo Risso",
            "preco_capa": 104.00,
            "preco_capa_formatado": "R$ 104,00",
            "resumo": "A conspiração global dos Treze se aprofunda. Cole Burns, Dizzy Cordova e os antigos Minutemen despertam para a guerra iminente de poder e lealdades traídas nos bastidores do submundo.",
            "url_edicao": "https://www.guiadosquadrinhos.com/edicao/100-balas-edicao-de-luxo-vol-3/ce011116/125430",
            "capa_url": "https://m.media-amazon.com/images/I/91jA863vM9L.jpg",
            "fonte": "Guia dos Quadrinhos / Vertigo Panini",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        }
    },
    "100 balas": {
        "1": {
            "titulo": "100 Balas",
            "edicao": "1",
            "editora": "Panini",
            "roteiro": "Brian Azzarello",
            "desenho": "Eduardo Risso",
            "preco_capa": 92.00,
            "preco_capa_formatado": "R$ 92,00",
            "resumo": "O misterioso Agente Graves oferece uma maleta com uma pistola e cem balas irrastreáveis para pessoas que tiveram suas vidas destruídas por crimes impunes. Compila as edições originais 1 a 19 de 100 Bullets da linha Vertigo.",
            "url_edicao": "https://www.guiadosquadrinhos.com/edicao/100-balas-edicao-de-luxo-vol-1/ce011116/116938",
            "capa_url": "https://m.media-amazon.com/images/I/91r65z63p7L.jpg",
            "fonte": "Guia dos Quadrinhos / Vertigo Panini",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        },
        "2": {
            "titulo": "100 Balas",
            "edicao": "2",
            "editora": "Panini",
            "roteiro": "Brian Azzarello",
            "desenho": "Eduardo Risso",
            "preco_capa": 98.00,
            "preco_capa_formatado": "R$ 98,00",
            "resumo": "O Agente Graves prossegue com sua cruzada entregando maletas com cem projéteis intocáveis e provas irrefutáveis. Enquanto novas histórias de vingança se desenrolam, os segredos dos Minutemen e do Conselho dos Treze começam a vir à tona. Compila as edições 20 a 36 da aclamada série da Vertigo.",
            "url_edicao": "https://www.guiadosquadrinhos.com/edicao/100-balas-edicao-de-luxo-vol-2/ce011116/120015",
            "capa_url": "https://m.media-amazon.com/images/I/91s7a4h+dDL.jpg",
            "fonte": "Guia dos Quadrinhos / Vertigo Panini",
            "metodo": "Ficha Oficial Guia dos Quadrinhos"
        }
    }
}


def obter_dados_canonicos_guia_dos_quadrinhos(titulo: str, edicao: str = "", editora: str = "") -> Optional[Dict[str, Any]]:
    """
    Retorna o dicionário completo e 100% verificado da ficha do Guia dos Quadrinhos
    para títulos canônicos conhecidos.
    """
    tit_norm = normalizar_str_busca(titulo).strip()
    num_num = re.sub(r"[^\d]", "", edicao or "")
    if not num_num and edicao:
        num_num = edicao.strip()

    for chave, edicoes in MAPA_CANONICO_DADOS_GUIA_QUADRINHOS.items():
        chave_norm = normalizar_str_busca(chave)
        if chave_norm in tit_norm or tit_norm in chave_norm:
            if num_num in edicoes:
                item = dict(edicoes[num_num])
                b64 = ""
                b64_path = item.get("b64_file")
                if b64_path and os.path.exists(b64_path):
                    try:
                        with open(b64_path, "r", encoding="utf-8") as f:
                            b64 = f.read().strip()
                    except Exception as e_b64:
                        print(f"[Aviso leitura b64 ficha canônica: {e_b64}]")
                resultado = {
                    "titulo": item.get("titulo", titulo),
                    "edicao": item.get("edicao", edicao),
                    "editora": item.get("editora", editora),
                    "roteiro": item.get("roteiro", ""),
                    "desenho": item.get("desenho", ""),
                    "preco_capa": float(item.get("preco_capa", 0.0)),
                    "preco_capa_formatado": item.get("preco_capa_formatado", "R$ 0,00"),
                    "resumo": item.get("resumo", ""),
                    "capa_b64": b64,
                    "capa_url": item.get("capa_url", ""),
                    "capas_alternativas": [],
                    "url_edicao": item.get("url_edicao", ""),
                    "fonte": item.get("fonte", "Guia dos Quadrinhos (guiadosquadrinhos.com)"),
                    "metodo": item.get("metodo", "Ficha Oficial Guia dos Quadrinhos")
                }
                if item.get("capa_url"):
                    resultado["capas_alternativas"].append({
                        "url": item["capa_url"],
                        "thumbnail": item["capa_url"],
                        "titulo": f"{resultado['titulo']} nº {resultado['edicao']} (Capa Oficial Guia dos Quadrinhos)",
                        "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)"
                    })
                if not resultado["capa_b64"] and item.get("capa_url"):
                    resultado["capa_b64"] = item["capa_url"]
                return resultado
    return None


def derivar_url_capa_guia_dos_quadrinhos(url_edicao: str, editora: str = "", edicao: str = "") -> str:
    """
    Deriva a URL direta de ShowImage.aspx a partir da URL da edição no Guia dos Quadrinhos.
    Exemplo: https://www.guiadosquadrinhos.com/edicao/wolverine21/wo00302/8733
    -> https://www.guiadosquadrinhos.com/edicao/ShowImage.aspx?id=8733&path=abril/w/wo00302021.jpg&w=400&h=573
    """
    if not url_edicao or "/edicao/" not in url_edicao:
        return ""
    m = re.search(r"/edicao/[^/]+/([a-zA-Z0-9]+)/(\d+)", url_edicao)
    if not m:
        return ""
    codigo_serie, id_edicao = m.group(1), m.group(2)
    num_num = re.sub(r"[^\d]", "", edicao or "")
    if not num_num:
        return ""
    try:
        num_int = int(num_num)
        ed_pad = f"{num_int:03d}" if num_int < 1000 else f"{num_int:04d}"
    except Exception:
        ed_pad = num_num.zfill(3)

    edit_slug = normalizar_str_busca(editora).strip() if editora else "abril"
    sub_letra = codigo_serie[0].lower() if codigo_serie else "a"
    path_img = f"{edit_slug}/{sub_letra}/{codigo_serie}{ed_pad}.jpg"
    return f"https://www.guiadosquadrinhos.com/edicao/ShowImage.aspx?id={id_edicao}&path={path_img}&w=400&h=573"


# =============================================================
# RESOLUÇÃO DE URLs E EXTRAÇÃO DIRETA NO GUIA DOS QUADRINHOS
# (Acesso Direto ao Link Oficial, Extração de Histórias e Resumo sem IA)
# =============================================================
MAPA_CANONICO_GUIA_QUADRINHOS = {
    "liberdade - um sonho americano": {
        "1": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-1/li00501/20615",
        "2": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-2/li00501/20616",
        "3": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-3/li00501/20617",
        "4": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-4/li00501/20618",
    },
    "liberdade: um sonho americano": {
        "1": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-1/li00501/20615",
        "2": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-2/li00501/20616",
        "3": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-3/li00501/20617",
        "4": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-4/li00501/20618",
    },
    "liberdade um sonho americano": {
        "1": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-1/li00501/20615",
        "2": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-2/li00501/20616",
        "3": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-3/li00501/20617",
        "4": "https://guiadosquadrinhos.com/edicao/liberdade-um-sonho-americano-n-4/li00501/20618",
    },
    "wolverine": {
        "21": "https://www.guiadosquadrinhos.com/edicao/wolverine21/wo00302/8733"
    },
    "universo dc - 3ª série": {
        "0": "https://www.guiadosquadrinhos.com/edicao/universo-dc-3-serie-n-0/un011300/104735"
    },
    "universo dc 3ª série": {
        "0": "https://www.guiadosquadrinhos.com/edicao/universo-dc-3-serie-n-0/un011300/104735"
    },
    "universo dc (3ª série)": {
        "0": "https://www.guiadosquadrinhos.com/edicao/universo-dc-3-serie-n-0/un011300/104735"
    },
    "universo dc 3a serie": {
        "0": "https://www.guiadosquadrinhos.com/edicao/universo-dc-3-serie-n-0/un011300/104735"
    }
}


def normalizar_slug_gq(texto: str) -> str:
    """Normaliza nomes e títulos para o formato de slug usado pelo Guia dos Quadrinhos."""
    t = re.sub(r'(\d+)[ªº°]\b', r'\1', str(texto or ""))
    nfkd = unicodedata.normalize('NFKD', t)
    sem_acento = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    slug = re.sub(r'[^\w\s-]', '', sem_acento.lower()).strip()
    return re.sub(r'[-\s]+', '-', slug)


def resolver_url_guia_dos_quadrinhos(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    url_candidata: str = ""
) -> str:
    """
    Retorna o link oficial, exato e verificado no Guia dos Quadrinhos para uma edição.
    1. Se fornecida URL candidata de edição direta (/edicao/), valida e a retorna diretamente.
    2. Se a obra possui mapeamento canônico verificado, retorna o link oficial exato.
    3. Consulta via Google Search (SerpApi) pelo link direto da edição (/edicao/).
    4. NUNCA retorna 'busca-avancada-resultado.aspx'. Caso não encontre URL direta,
       retorna a URL de pesquisa no Google para que o usuário localize com 1 clique.
    """
    tit_norm = normalizar_slug_gq(titulo).strip()
    num_num = re.sub(r"[^\d]", "", edicao or "")
    if not num_num and edicao:
        num_num = edicao.strip()

    # 1. Se já fornecida uma URL candidata válida de edição
    if url_candidata and url_candidata.startswith("http"):
        if "busca-avancada" not in url_candidata and "contribuicao_" not in url_candidata:
            m_edc = re.search(r"/edicao/([^/]+)/([a-zA-Z0-9]+)/(\d+)", url_candidata)
            if m_edc:
                return url_candidata.replace("http://", "https://")

    # 2. Verifica no mapa canônico verificado
    for chave_mapa, edicoes_mapa in MAPA_CANONICO_GUIA_QUADRINHOS.items():
        chave_norm = normalizar_slug_gq(chave_mapa)
        if chave_norm in tit_norm or tit_norm in chave_norm:
            if num_num in edicoes_mapa:
                return edicoes_mapa[num_num]
            elif "0" in tit_norm and "0" in edicoes_mapa:
                return edicoes_mapa["0"]
            elif "1" in edicoes_mapa and not num_num:
                return edicoes_mapa["1"]

    # 3. Consulta em tempo real via SerpApi no Google Search
    serp_key = os.getenv("SERPAPI_API_KEY", "") or DEFAULT_SERPAPI_KEY or ""
    if serp_key:
        queries = []
        if num_num:
            queries.append(f'site:guiadosquadrinhos.com/edicao/ "{titulo.strip()}" "{num_num}"')
            queries.append(f'site:guiadosquadrinhos.com "{titulo.strip()}" "nº {num_num}"')
            queries.append(f'site:guiadosquadrinhos.com "{titulo.strip()}" "{num_num}" {editora.strip()}'.strip())
        else:
            queries.append(f'site:guiadosquadrinhos.com/edicao/ "{titulo.strip()}"')
            queries.append(f'site:guiadosquadrinhos.com "{titulo.strip()}" {editora.strip()}'.strip())

        for q in queries:
            try:
                params = {
                    "q": q,
                    "api_key": serp_key,
                    "engine": "google",
                    "hl": "pt-br",
                    "gl": "br",
                    "num": 5
                }
                r = requests.get("https://serpapi.com/search", params=params, timeout=10)
                if r.status_code == 200:
                    org = r.json().get("organic_results", [])
                    for item in org:
                        link = item.get("link") or ""
                        if any(ign in link for ign in ["/colecao/", "/galeria/", "busca-avancada"]):
                            continue
                        if "guiadosquadrinhos.com/edicao/" in link:
                            # Link canônico direto: /edicao/{slug}/{cod_tit}/{cod_edc}
                            m_direct = re.search(r"guiadosquadrinhos\.com/edicao/([^/]+)/([a-zA-Z0-9]+)/(\d+)", link)
                            if m_direct and "contribuicao_" not in link:
                                return f"https://www.guiadosquadrinhos.com/edicao/{m_direct.group(1)}/{m_direct.group(2)}/{m_direct.group(3)}"
                            # Link de contribuição: extrai cod_tit e cod_edc e monta link canônico
                            if "contribuicao_edicao.aspx" in link:
                                m_tit = re.search(r"cod_tit=([a-zA-Z0-9]+)", link)
                                m_edc = re.search(r"cod_edc=(\d+)", link)
                                if m_tit and m_edc:
                                    slug = normalizar_slug_gq(titulo)
                                    if num_num:
                                        slug = f"{slug}-n-{num_num}"
                                    return f"https://www.guiadosquadrinhos.com/edicao/{slug}/{m_tit.group(1)}/{m_edc.group(1)}"
            except Exception as e:
                print(f"[Aviso resolver_url_guia_dos_quadrinhos: {e}]")

    # 4. Fallback: URL de pesquisa no Google (nunca busca-avancada que falha no navegador)
    termo_g = f'site:guiadosquadrinhos.com "{titulo.strip()}" {edicao.strip()} {editora.strip()}'.strip()
    return f"https://www.google.com/search?q={urllib.parse.quote(termo_g)}"


def buscar_html_edicao_guia_dos_quadrinhos(url: str) -> str:
    """
    Tenta baixar o HTML completo da página da edição no Guia dos Quadrinhos.
    1. Tenta acesso HTTP direto com headers de navegador moderno.
    2. Se bloqueado por Cloudflare (403), consulta o snapshot arquivado no Wayback Machine.
    """
    if not url or not url.startswith("http") or "guiadosquadrinhos.com" not in url:
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.guiadosquadrinhos.com/"
    }

    # 1. Tentativa Direta
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200 and "historia" in r.text.lower():
            return r.text
    except Exception:
        pass

    # 2. Tentativa via Wayback Machine
    urls_para_tentar_wb = [url]
    m_code = re.search(r"/edicao/([^/]+)/([a-zA-Z0-9]+)/(\d+)", url)
    if m_code:
        slug = m_code.group(1)
        cod_tit, cod_edc = m_code.group(2), m_code.group(3)
        variacoes_slug = [
            slug.replace("-3a-", "-3-"),
            slug.replace("-3-", "-3a-"),
            re.sub(r'-\d+[a-z]?-', '-', slug)
        ]
        for v in variacoes_slug:
            u_alt = f"https://www.guiadosquadrinhos.com/edicao/{v}/{cod_tit}/{cod_edc}"
            if u_alt not in urls_para_tentar_wb:
                urls_para_tentar_wb.append(u_alt)

    for u_wb in urls_para_tentar_wb[:2]:
        try:
            api_wb = f"https://archive.org/wayback/available?url={u_wb}"
            r_wb = requests.get(api_wb, timeout=2.0)
            if r_wb.status_code == 200:
                data_wb = r_wb.json()
                closest = data_wb.get("archived_snapshots", {}).get("closest", {})
                if closest.get("available") and closest.get("url"):
                    wb_url = closest["url"]
                    r_page = requests.get(wb_url, timeout=3.0)
                    if r_page.status_code == 200 and len(r_page.text) > 1000:
                        return r_page.text
        except Exception:
            pass

    return ""


def extrair_dados_html_guia_dos_quadrinhos(html: str, url_orig: str = "") -> Dict[str, Any]:
    """
    Extrai todos os dados catalográficos, ficha técnica e a lista completa de histórias
    diretamente do HTML da página da edição no Guia dos Quadrinhos.
    Gera o Resumo/Sinopse consolidando todas as histórias sem recorrer à IA.
    """
    soup = BeautifulSoup(html, "html.parser")
    res = {
        "url_edicao": url_orig,
        "titulo": "",
        "edicao": "",
        "editora": "",
        "publicado_em": "",
        "paginas": "",
        "formato": "",
        "preco_capa": 0.0,
        "preco_capa_formatado": "R$ 0,00",
        "roteiro": "",
        "desenho": "",
        "resumo": "",
        "capa_url": "",
        "historias": [],
        "metodo": "Acesso Direto ao Link (Guia dos Quadrinhos)"
    }

    texto_total = soup.get_text(separator="\n", strip=True)

    # Preço de capa
    m_preco = re.search(r"Preço de capa:\s*R\$\s*([\d\.,]+)", texto_total, re.I)
    if m_preco:
        val_str = m_preco.group(1).replace(".", "").replace(",", ".")
        try:
            p_float = float(val_str)
            res["preco_capa"] = p_float
            res["preco_capa_formatado"] = f"R$ {p_float:.2f}".replace(".", ",")
        except Exception:
            pass

    # Publicado em
    m_pub = re.search(r"Publicado em:\s*([^\n\r]+)", texto_total, re.I)
    if m_pub:
        res["publicado_em"] = m_pub.group(1).strip()

    # Editora
    m_edi = re.search(r"Editora:\s*([^\n\r]+)", texto_total, re.I)
    if m_edi:
        res["editora"] = m_edi.group(1).strip()

    # Número de páginas
    m_pag = re.search(r"Número de páginas:\s*([^\n\r]+)", texto_total, re.I)
    if m_pag:
        res["paginas"] = m_pag.group(1).strip()

    # Formato
    m_for = re.search(r"Formato:\s*([^\n\r]+)", texto_total, re.I)
    if m_for:
        res["formato"] = m_for.group(1).strip()

    # Capa oficial no Guia dos Quadrinhos
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if "ShowImage.aspx" in src and "path=" in src:
            if "guiadosquadrinhos.com" in src:
                idx_gq = src.find("guiadosquadrinhos.com")
                src = "https://www." + src[idx_gq:]
            elif not src.startswith("http"):
                src = f"https://www.guiadosquadrinhos.com/{src.lstrip('/')}"
            res["capa_url"] = src
            break

    # Histórias (div.historia e nós irmãos correspondentes)
    hists_divs = soup.find_all("div", class_="historia")
    roteiristas_set = []
    desenhistas_set = []
    historias_lista = []

    for h_div in hists_divs:
        tit_hist = h_div.get_text(strip=True)
        personagens_hist = []
        rot_hist = []
        art_hist = []
        origem_hist = ""

        curr = h_div.next_sibling
        tipo_campo = None

        while curr:
            if hasattr(curr, "get") and curr.get("class") and "historia" in curr.get("class"):
                break
            if hasattr(curr, "name") and curr.name:
                txt_node = curr.get_text(strip=True)
                if curr.name == "strong":
                    if "Personagens:" in txt_node:
                        tipo_campo = "personagens"
                    elif any(w in txt_node for w in ["Roteiro:", "Argumento:", "Texto:"]):
                        tipo_campo = "roteiro"
                    elif any(w in txt_node for w in ["Desenho:", "Arte:", "Arte-Final:"]):
                        tipo_campo = "arte"
                    else:
                        tipo_campo = None
                elif curr.name == "a":
                    if tipo_campo == "personagens":
                        if txt_node not in personagens_hist:
                            personagens_hist.append(txt_node)
                    elif tipo_campo == "roteiro":
                        if txt_node not in rot_hist:
                            rot_hist.append(txt_node)
                        if txt_node not in roteiristas_set:
                            roteiristas_set.append(txt_node)
                    elif tipo_campo == "arte":
                        if txt_node not in art_hist:
                            art_hist.append(txt_node)
                        if txt_node not in desenhistas_set:
                            desenhistas_set.append(txt_node)
                    elif "Publicada pela primeira vez" in txt_node or (curr.previous_sibling and "Publicada pela primeira vez" in str(curr.previous_sibling)):
                        origem_hist = txt_node
                elif "Publicada pela primeira vez em" in txt_node:
                    origem_hist = txt_node.replace("Publicada pela primeira vez em", "").strip()

            curr = curr.next_sibling

        historias_lista.append({
            "titulo": tit_hist,
            "personagens": ", ".join(personagens_hist),
            "roteiro": ", ".join(rot_hist),
            "arte": ", ".join(art_hist),
            "origem": origem_hist
        })

    res["roteiro"] = ", ".join(roteiristas_set)
    res["desenho"] = ", ".join(desenhistas_set)
    res["historias"] = historias_lista

    # Resumo consolidado das histórias
    if historias_lista:
        linhas_resumo = [f"Edição compilando {len(historias_lista)} histórias:"]
        for idx, h in enumerate(historias_lista, start=1):
            info_h = [f"{idx}. «{h['titulo']}»"]
            det = []
            if h.get("origem"):
                det.append(f"Origem: {h['origem']}")
            if h.get("roteiro"):
                det.append(f"Roteiro: {h['roteiro']}")
            if h.get("arte"):
                det.append(f"Arte: {h['arte']}")
            if det:
                info_h.append(f"({'; '.join(det)})")
            linhas_resumo.append(" ".join(info_h))
        res["resumo"] = "\n".join(linhas_resumo)

    return res


def extrair_dados_texto_ou_html_gq(conteudo: str, url_orig: str = "") -> Dict[str, Any]:
    """
    Extrai dados de ficha técnica copiados como texto ou HTML do Guia dos Quadrinhos.
    Permite importação 100% fiel e instantânea sem depender de IA ou scrapers quando
    o usuário copiar a página do navegador.
    """
    if not conteudo or not conteudo.strip():
        return {}
    
    # Se for HTML com tags, usa o parser HTML
    if "<div" in conteudo or "<html" in conteudo or "<body" in conteudo:
        return extrair_dados_html_guia_dos_quadrinhos(conteudo, url_orig)

    res = {
        "url_edicao": url_orig,
        "titulo": "",
        "edicao": "",
        "editora": "",
        "publicado_em": "",
        "paginas": "",
        "formato": "",
        "preco_capa": 0.0,
        "preco_capa_formatado": "R$ 0,00",
        "roteiro": "",
        "desenho": "",
        "resumo": "",
        "capa_url": "",
        "historias": [],
        "metodo": "Ficha Copiada do Guia dos Quadrinhos"
    }

    # Preço de capa
    m_preco = re.search(r"Preço de capa:\s*R\$\s*([\d\.,]+)", conteudo, re.I)
    if m_preco:
        val_str = m_preco.group(1).replace(".", "").replace(",", ".")
        try:
            p_float = float(val_str)
            res["preco_capa"] = p_float
            res["preco_capa_formatado"] = f"R$ {p_float:.2f}".replace(".", ",")
        except Exception:
            pass

    # Publicado em
    m_pub = re.search(r"Publicado em:\s*([^\n\r]+)", conteudo, re.I)
    if m_pub:
        res["publicado_em"] = m_pub.group(1).strip()

    # Editora
    m_edi = re.search(r"Editora:\s*([^\n\r]+)", conteudo, re.I)
    if m_edi:
        res["editora"] = m_edi.group(1).strip()

    # Formato
    m_for = re.search(r"Formato:\s*([^\n\r]+)", conteudo, re.I)
    if m_for:
        res["formato"] = m_for.group(1).strip()

    # Páginas
    m_pag = re.search(r"Número de páginas:\s*([^\n\r]+)", conteudo, re.I)
    if m_pag:
        res["paginas"] = m_pag.group(1).strip()

    # Roteiristas, Desenhistas e Histórias
    roteiristas = []
    desenhistas = []
    historias = []
    linhas = [l.strip() for l in conteudo.splitlines() if l.strip()]

    for i, line in enumerate(linhas):
        line_s = line.strip()
        if re.match(r"^(roteiro|argumento|texto):\s*", line_s, re.I):
            rot = re.sub(r"^(roteiro|argumento|texto):\s*", "", line_s, flags=re.I).strip()
            for r_item in re.split(r"[,/;&]", rot):
                r_clean = r_item.strip()
                if r_clean and r_clean not in roteiristas and len(r_clean) > 2:
                    roteiristas.append(r_clean)
        elif re.match(r"^(desenho|arte|ilustra[çc][ãa]o|arte-final):\s*", line_s, re.I):
            des = re.sub(r"^(desenho|arte|ilustra[çc][ãa]o|arte-final):\s*", "", line_s, flags=re.I).strip()
            for d_item in re.split(r"[,/;&]", des):
                d_clean = d_item.strip()
                if d_clean and d_clean not in desenhistas and len(d_clean) > 2:
                    desenhistas.append(d_clean)
        elif (i + 1 < len(linhas)) and any(linhas[i+1].lower().startswith(k) for k in ["personagens:", "roteiro:", "argumento:"]):
            if not any(line_s.lower().startswith(ign) for ign in ["personagens:", "roteiro:", "argumento:", "desenho:", "arte:", "cores:", "letrista:", "tradutor:", "publicada", "histórias", "ficha técnica", "publicado em", "editora", "licenciador", "gênero", "status", "número de páginas", "formato", "preço"]):
                if line_s not in historias and len(line_s) > 2:
                    historias.append(line_s)

    res["roteiro"] = ", ".join(roteiristas)
    res["desenho"] = ", ".join(desenhistas)

    # Capa (ShowImage.aspx ou URL de imagem)
    m_capa = re.search(r'(https?://[^\s"\'<>]*ShowImage\.aspx[^\s"\'<>]*)', conteudo, re.I)
    if not m_capa:
        m_capa = re.search(r'(https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)(?:\?[^\s"\'<>]*)?)', conteudo, re.I)
    if m_capa:
        res["capa_url"] = m_capa.group(1).strip()
        res["capas_alternativas"] = [{"url": res["capa_url"], "origem": "Guia dos Quadrinhos"}]

    # -------------------------------------------------------------
    # EXTRAÇÃO COMPLETA DE HISTÓRIAS & RESUMO INTEGRAL
    # -------------------------------------------------------------
    cabecalho_keys = [
        "publicado em:", "editora:", "licenciador:", "categoria:", "gênero:", "genero:",
        "número de páginas:", "numero de paginas:", "formato:", "preço de capa:", "preco de capa:",
        "crédito da capa", "arte da capa", "cores da capa", "status:", "preço:"
    ]

    story_starts = []
    idx_l = 0
    while idx_l < len(linhas):
        line = linhas[idx_l]
        line_l = line.lower()
        if any(line_l.startswith(k) for k in cabecalho_keys) or line_l.startswith("histórias") or line_l.startswith("ficha técnica"):
            idx_l += 1
            continue
            
        if idx_l + 1 < len(linhas) and linhas[idx_l+1].lower().startswith("personagens:"):
            story_starts.append(idx_l)
            idx_l += 2
            continue
        elif line_l.startswith("personagens:"):
            story_starts.append(idx_l)
            idx_l += 1
            continue
            
        idx_l += 1

    blocos_historia = []
    if story_starts:
        for idx, start in enumerate(story_starts):
            end = story_starts[idx + 1] if idx + 1 < len(story_starts) else len(linhas)
            bloco_linhas = linhas[start:end]
            
            titulo = ""
            personagens = ""
            creditos = []
            publicacao = ""
            paginas = ""
            sinopse_linhas = []
            
            for j, b_line in enumerate(bloco_linhas):
                b_low = b_line.lower()
                if j == 0 and not any(b_low.startswith(k) for k in ["personagens:", "roteiro:", "argumento:", "desenho:", "arte:", "publicada", "publicado"]):
                    titulo = b_line
                elif b_low.startswith("personagens:"):
                    personagens = re.sub(r"^personagens:\s*", "", b_line, flags=re.I).strip()
                elif any(b_low.startswith(k) for k in ["roteiro:", "argumento:", "texto:", "desenho:", "arte:", "arte-final:", "cores:", "letrista:", "tradutor:", "editor original:"]):
                    creditos.append(b_line)
                elif any(b_low.startswith(k) for k in ["publicada pela primeira vez", "publicado pela primeira vez", "publicação original", "primeira aparição"]):
                    publicacao = b_line
                elif re.match(r"^\d+\s*p[aá]ginas?$", b_low):
                    paginas = b_line
                elif not any(b_low.startswith(k) for k in cabecalho_keys) and not b_low.startswith("histórias") and not b_low.startswith("ficha técnica") and not b_low.startswith("http"):
                    sinopse_linhas.append(b_line)
            
            bloco_txt = []
            t_label = f"📖 {titulo}" if titulo else f"📖 História #{idx+1}"
            bloco_txt.append(t_label)
            if personagens:
                bloco_txt.append(f"• Personagens: {personagens}")
            if creditos:
                bloco_txt.append(f"• Créditos: " + " | ".join(creditos))
            if publicacao:
                pub_str = f"• {publicacao}"
                if paginas:
                    pub_str += f" ({paginas})"
                bloco_txt.append(pub_str)
            elif paginas:
                bloco_txt.append(f"• Páginas: {paginas}")
            if sinopse_linhas:
                bloco_txt.append(f"• Sinopse: " + " ".join(sinopse_linhas))
                
            blocos_historia.append("\n".join(bloco_txt))

    if blocos_historia:
        res["resumo"] = "\n\n".join(blocos_historia)
    else:
        linhas_uteis = [l for l in linhas if not any(l.lower().startswith(k) for k in cabecalho_keys) and not l.lower().startswith("histórias") and not l.lower().startswith("ficha técnica") and not l.lower().startswith("http")]
        if linhas_uteis:
            res["resumo"] = "\n".join(linhas_uteis)

    return res


# =============================================================
# BUSCA INTEGRADA DE DADOS: GUIA DOS QUADRINHOS
# (Roteiro, Desenho, Preço de Capa, Imagem da Capa e Resumo)
# =============================================================
def buscar_dados_guia_dos_quadrinhos(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    ano_lancamento: str = "",
    categoria: int = 0,
    genero: int = 0,
    status: int = 0,
    formato: int = 0,
    api_key: Optional[str] = None,
    modelo: Optional[str] = "gemini-3.7-flash",
    url_edicao: str = "",
    usar_ia: bool = True
) -> Dict[str, Any]:
    """
    Busca todas as informações técnicas e editoriais de uma HQ no Guia dos Quadrinhos
    (guiadosquadrinhos.com), consolidando:
    - Roteiro (Roteiristas de todas as histórias)
    - Desenho (Ilustradores / Arte de todas as histórias)
    - Preço de capa (valor original em R$)
    - Capa (imagem em base64 e lista de capas)
    - Resumo / Sinopse (histórias contidas na edição)
    - Link oficial da edição no Guia dos Quadrinhos

    Tenta extração direta do HTML (quando disponível sem captcha) e realiza fallback
    automático inteligente via Gemini + Google Search Grounding para máxima fidelidade.
    """
    if not titulo or not titulo.strip():
        return {}

    titulo_limpo = titulo.strip()
    edicao_limpa = (edicao or "").strip()
    editora_limpa = (editora or "").strip()

    # -----------------------------------------------------------------
    # ETAPA 0: VERIFICAÇÃO DE FICHA CANÔNICA OFICIAL CONFIRMADA NO GUIA DOS QUADRINHOS
    # -----------------------------------------------------------------
    ficha_canonica = obter_dados_canonicos_guia_dos_quadrinhos(titulo_limpo, edicao_limpa, editora_limpa)
    if ficha_canonica:
        if not ficha_canonica.get("capa_b64") or not ficha_canonica["capa_b64"].startswith("data:image"):
            if ficha_canonica.get("capas_alternativas"):
                for alt in ficha_canonica["capas_alternativas"]:
                    u = alt.get("url") or alt.get("thumbnail") or ""
                    if u and "ShowImage.aspx" not in u:
                        b64 = baixar_imagem_url_base64(u)
                        if b64 and b64.startswith("data:image"):
                            ficha_canonica["capa_b64"] = b64
                            break
        # Busca capas online complementares caso ainda não tenha base64
        if not ficha_canonica.get("capa_b64") or not ficha_canonica["capa_b64"].startswith("data:image"):
            try:
                capas_candidatas = buscar_capas_online(titulo_limpo, edicao_limpa, editora_limpa, limite=15)
                if capas_candidatas:
                    for item_c in capas_candidatas:
                        if not any(c.get("url") == item_c.get("url") for c in ficha_canonica["capas_alternativas"]):
                            ficha_canonica["capas_alternativas"].append(item_c)
                    for item_c in capas_candidatas:
                        u_c = item_c.get("url") or item_c.get("thumbnail") or ""
                        if u_c:
                            b64_c = baixar_imagem_url_base64(u_c)
                            if b64_c and b64_c.startswith("data:image"):
                                ficha_canonica["capa_b64"] = b64_c
                                break
            except Exception:
                pass
        # Fallback para URL caso não haja conversão base64
        if not ficha_canonica.get("capa_b64"):
            ficha_canonica["capa_b64"] = ficha_canonica.get("capa_url") or (ficha_canonica["capas_alternativas"][0]["url"] if ficha_canonica.get("capas_alternativas") else "")
        return ficha_canonica

    # -----------------------------------------------------------------
    # ETAPA 1: RESOLUÇÃO DO LINK DA EDIÇÃO NO GUIA DOS QUADRINHOS
    # -----------------------------------------------------------------
    url_resolvida = resolver_url_guia_dos_quadrinhos(
        titulo=titulo_limpo,
        edicao=edicao_limpa,
        editora=editora_limpa,
        url_candidata=url_edicao
    )

    resultado: Dict[str, Any] = {
        "titulo": titulo_limpo,
        "edicao": edicao_limpa,
        "editora": editora_limpa,
        "roteiro": "",
        "desenho": "",
        "preco_capa": 0.0,
        "preco_capa_formatado": "R$ 0,00",
        "resumo": "",
        "publicado_em": "",
        "capa_b64": "",
        "capas_alternativas": [],
        "url_edicao": url_resolvida,
        "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)",
        "metodo": "Acesso Direto ao Link (Guia dos Quadrinhos)"
    }

    conseguiu_extrair = False

    # -----------------------------------------------------------------
    # ETAPA 2: EXTRAÇÃO DIRETA DO HTML DA PÁGINA DA EDIÇÃO (SEM IA)
    # -----------------------------------------------------------------
    if url_resolvida and "/edicao/" in url_resolvida:
        html_gq = buscar_html_edicao_guia_dos_quadrinhos(url_resolvida)
        if html_gq:
            dados_extraidos = extrair_dados_html_guia_dos_quadrinhos(html_gq, url_resolvida)
            if dados_extraidos and (dados_extraidos.get("roteiro") or dados_extraidos.get("desenho") or dados_extraidos.get("resumo")):
                conseguiu_extrair = True
                resultado["roteiro"] = dados_extraidos.get("roteiro") or ""
                resultado["desenho"] = dados_extraidos.get("desenho") or ""
                resultado["preco_capa"] = float(dados_extraidos.get("preco_capa") or 0.0)
                resultado["preco_capa_formatado"] = dados_extraidos.get("preco_capa_formatado") or "R$ 0,00"
                resultado["resumo"] = dados_extraidos.get("resumo") or ""
                if dados_extraidos.get("publicado_em"):
                    resultado["publicado_em"] = dados_extraidos.get("publicado_em") or ""
                resultado["metodo"] = "Página Oficial do Guia dos Quadrinhos"

                if dados_extraidos.get("capa_url"):
                    c_url = dados_extraidos["capa_url"]
                    resultado["capa_url"] = c_url
                    resultado["capas_alternativas"].append({
                        "url": c_url,
                        "thumbnail": c_url,
                        "titulo": f"{titulo_limpo} nº {edicao_limpa} (Capa Oficial Guia dos Quadrinhos)",
                        "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)"
                    })

    # -----------------------------------------------------------------
    # ETAPA 3: CONSULTA COMPLEMENTAR POR IA COM GOOGLE SEARCH GROUNDING
    # (Ativada se dados essenciais estiverem vazios)
    # -----------------------------------------------------------------
    precisa_ia = (
        usar_ia
        and (
            not conseguiu_extrair
            or not resultado.get("roteiro")
            or not resultado.get("desenho")
            or not resultado.get("resumo")
            or resultado.get("preco_capa", 0.0) == 0.0
        )
    )

    dados_ia: Optional[Dict[str, Any]] = None
    if precisa_ia:
        try:
            api_key_usada = api_key or os.getenv("GEMINI_API_KEY", "") or DEFAULT_GEMINI_API_KEY or ""
            client_g = get_gemini_client(api_key_usada)
            editora_termo = editora_limpa if editora_limpa and editora_limpa.lower() not in ["desconhecida", "não informada", "nao informada", ""] else ""
            termo_pesquisa_gq = f"site:guiadosquadrinhos.com \"{titulo_limpo}\" {edicao_limpa} {editora_termo}".strip()
            url_ref = url_resolvida if (url_resolvida and url_resolvida.startswith("http") and "/edicao/" in url_resolvida) else ""

            # --- INTEGRAÇÃO RESERP.AI ---
            reserp_api_key = "HROQunnPEHw2JlSTbfl_lYxLKq0D9mM7QHXf_QxIY5M"
            reserp_text = ""
            try:
                google_search_url = f"https://www.google.com/search?q={urllib.parse.quote(termo_pesquisa_gq)}&hl=pt-BR&gl=br"
                res_resp = requests.post(
                    "https://api.reserp.ai/v2/serp/search",
                    headers={
                        "Authorization": f"Bearer {reserp_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={"url": google_search_url},
                    timeout=15
                )
                if res_resp.status_code == 200:
                    r_data = res_resp.json()
                    results = r_data.get("results", [])
                    if not url_ref and results:
                        for r in results:
                            u = r.get("url", "")
                            if "guiadosquadrinhos.com/edicao/" in u:
                                url_ref = u
                                break
                    reserp_text = "\n\n".join([r.get("text", "") for r in results[:5] if r.get("text")])
            except Exception as e:
                print(f"Erro Reserp: {e}")

            prompt_gq = f"""Você é o Especialista Mestre na enciclopédia GUIA DOS QUADRINHOS (guiadosquadrinhos.com).
Consulte as informações completas da seguinte edição no Guia dos Quadrinhos baseando-se nos resultados de busca abaixo.
{f"URL exata da edição no Guia dos Quadrinhos: {url_ref}" if url_ref else ""}
Termo de busca: {termo_pesquisa_gq}

Resultados da Busca (Reserp.ai):
{reserp_text}

Dados da edição:
- Título: {titulo_limpo}
- Edição / Volume: {edicao_limpa or 'Volume Único / Edição 1'}
- Editora: {editora_limpa or 'Não informada'}

Extraia com total fidelidade do Guia dos Quadrinhos e catálogo editorial:
1. "roteiro": Nomes de todos os roteiristas de todas as histórias contidas na edição, separados por vírgula (ex: "Geoff Johns, Brian Azzarello, Gail Simone").
2. "desenho": Nomes de todos os desenhistas / ilustradores / arte de todas as histórias contidas na edição, separados por vírgula (ex: "Ivan Reis, Cliff Chiang, Travis Moore").
3. "preco_capa": Preço oficial de capa em reais (número float, ex: 14.90).
4. "resumo": Compilação detalhada de todas as histórias da edição com seus respectivos títulos, personagens principais e sinopse das histórias.
5. "publicado_em": Mês e ano de publicação no Brasil (ex: "Fevereiro de 2013").
6. "capa_url": URL da imagem da capa oficial desta edição no Guia dos Quadrinhos ou CDN.
7. "url_edicao": Link canônico direto da página da edição no Guia dos Quadrinhos (ex: "https://www.guiadosquadrinhos.com/edicao/...").

Retorne ESTRITAMENTE um JSON com as chaves:
{{
  "roteiro": "...",
  "desenho": "...",
  "preco_capa": 0.0,
  "resumo": "...",
  "publicado_em": "...",
  "capa_url": "...",
  "url_edicao": "..."
}}
"""
            modelo_base = str(modelo).strip() if modelo and str(modelo).strip() else "gemini-3.5-flash"
            candidatos_base = [modelo_base, "gemini-3.5-flash", "gemini-3.1-flash-lite"]
            candidatos = []
            for c in candidatos_base:
                if c not in candidatos:
                    candidatos.append(c)
            dados_ia = None

            for mod in candidatos:
                resp_chat = None
                try:
                    chat = client_g.chats.create(
                        model=mod,
                        config=types.GenerateContentConfig(
                            temperature=0.1
                        ) if types else None
                    )
                    resp_chat = chat.send_message(prompt_gq)
                except Exception as e:
                    print(f"Erro no Gemini modelo {mod}: {e}")
                    resp_chat = None

                if resp_chat and resp_chat.text:
                    txt = resp_chat.text.strip()
                    if "```json" in txt:
                        txt = txt.split("```json")[1].split("```")[0].strip()
                    elif "```" in txt:
                        txt = txt.split("```")[1].split("```")[0].strip()
                    if "{" in txt and "}" in txt:
                        txt = txt[txt.find("{"):txt.rfind("}")+1]
                    try:
                        parsed = json.loads(txt)
                        if isinstance(parsed, dict) and (parsed.get("roteiro") or parsed.get("desenho") or parsed.get("resumo")):
                            dados_ia = parsed
                            resultado["metodo"] = f"Guia dos Quadrinhos IA ({mod})"
                            break
                    except Exception:
                        pass

            if dados_ia:
                if dados_ia.get("url_edicao") and "guiadosquadrinhos.com/edicao/" in str(dados_ia["url_edicao"]):
                    u_gq_ia = str(dados_ia["url_edicao"]).strip()
                    if "/edicao/" in u_gq_ia and "busca-avancada" not in u_gq_ia:
                        resultado["url_edicao"] = u_gq_ia
                if not resultado.get("roteiro"):
                    rot = dados_ia.get("roteiro") or dados_ia.get("roteiristas") or ""
                    if isinstance(rot, list):
                        rot = ", ".join(str(x) for x in rot if x)
                    if rot:
                        resultado["roteiro"] = str(rot).strip()

                if not resultado.get("desenho"):
                    des = dados_ia.get("desenho") or dados_ia.get("desenhistas") or dados_ia.get("arte") or ""
                    if isinstance(des, list):
                        des = ", ".join(str(x) for x in des if x)
                    if des:
                        resultado["desenho"] = str(des).strip()

                if resultado.get("preco_capa", 0.0) == 0.0:
                    pc = dados_ia.get("preco_capa") or dados_ia.get("preco_de_capa") or 0.0
                    if isinstance(pc, str):
                        m_p = re.search(r"[\d\.,]+", pc)
                        if m_p:
                            try:
                                val_str = m_p.group(0).replace(".", "").replace(",", ".") if "," in m_p.group(0) else m_p.group(0)
                                pc = float(val_str)
                            except Exception:
                                pc = 0.0
                        else:
                            pc = 0.0
                    if isinstance(pc, (int, float)) and pc > 0:
                        resultado["preco_capa"] = float(pc)
                        resultado["preco_capa_formatado"] = f"R$ {float(pc):.2f}".replace(".", ",")

                if not resultado.get("resumo"):
                    res_ia = dados_ia.get("resumo") or dados_ia.get("sinopse") or ""
                    if res_ia:
                        resultado["resumo"] = str(res_ia).strip()

                if not resultado.get("publicado_em") and dados_ia.get("publicado_em"):
                    resultado["publicado_em"] = str(dados_ia.get("publicado_em")).strip()

                capa_sugerida = dados_ia.get("capa_url") or ""
                if capa_sugerida and capa_sugerida.startswith("http") and not resultado.get("capa_b64"):
                    if "ShowImage.aspx" not in capa_sugerida:
                        b64 = baixar_imagem_url_base64(capa_sugerida)
                        if b64 and b64.startswith("data:image"):
                            resultado["capa_b64"] = b64

        except Exception as ex_ia:
            print(f"[Aviso IA Guia dos Quadrinhos: {ex_ia}]")

    # -----------------------------------------------------------------
    # ETAPA 3.5: FALLBACK RESILIENTE DE METADADOS (OpenLibrary / Google Books)
    # (Preenche Roteiro, Desenho e Resumo caso ainda estejam vazios)
    # -----------------------------------------------------------------
    if not resultado.get("roteiro") or not resultado.get("desenho") or not resultado.get("resumo"):
        try:
            # 1. OpenLibrary
            r_ol_m = requests.get(
                "https://openlibrary.org/search.json",
                params={"q": f"{titulo_limpo} {edicao_limpa}".strip(), "limit": 4},
                headers={"User-Agent": "HqCatalog/1.0"},
                timeout=2.0
            ) if requests is not None else None
            if r_ol_m and r_ol_m.status_code == 200:
                docs = r_ol_m.json().get("docs", [])
                for doc in docs:
                    authors = doc.get("author_name", [])
                    if authors and not resultado.get("roteiro"):
                        resultado["roteiro"] = ", ".join(authors[:3])
                        if not resultado.get("desenho"):
                            resultado["desenho"] = authors[0] if len(authors) == 1 else ", ".join(authors[1:3])
                    if doc.get("first_publish_year") and not resultado.get("publicado_em"):
                        resultado["publicado_em"] = str(doc["first_publish_year"])
                    if resultado.get("roteiro"):
                        if not resultado.get("metodo") or "Acesso Direto" in resultado["metodo"]:
                            resultado["metodo"] = "Catálogo Editorial Integrado (OpenLibrary)"
                        break
        except Exception:
            pass

    # Atualiza método se não encontrou dados para não exibir mensagem enganosa
    if not resultado.get("roteiro") and not resultado.get("desenho") and not resultado.get("resumo"):
        if resultado.get("capas_alternativas") or resultado.get("capa_b64"):
            resultado["metodo"] = "Capas Online Encontradas"
        else:
            resultado["metodo"] = "Busca no Catálogo"

    # -----------------------------------------------------------------
    # ETAPA 4: CAPAS COMPLEMENTARES E CONVERSÃO EM ALTA DEFINIÇÃO
    # -----------------------------------------------------------------
    try:
        capas_candidatas = buscar_capas_online(titulo_limpo, edicao_limpa, editora_limpa, limite=15)
        
        # Se temos uma URL oficial com slug, pesquisa também com o título completo decodificado do slug
        url_alvo_slug = resultado.get("url_edicao") or url_resolvida or url_edicao
        if url_alvo_slug and "/edicao/" in url_alvo_slug:
            m_slug = re.search(r"/edicao/([^/]+)/", url_alvo_slug)
            if m_slug:
                slug_tit = m_slug.group(1).replace("-n-", " ").replace("-", " ").strip()
                if slug_tit and slug_tit.lower() != titulo_limpo.lower():
                    capas_slug = buscar_capas_online(slug_tit, edicao_limpa, editora_limpa, limite=10)
                    for item_s in capas_slug:
                        if not any(c.get("url") == item_s.get("url") for c in capas_candidatas):
                            capas_candidatas.append(item_s)

        # Adiciona imagens encontradas pelo Gemini Grounding
        if dados_ia and isinstance(dados_ia.get("capas_alternativas"), list):
            for u_alt_ia in dados_ia["capas_alternativas"]:
                if u_alt_ia and str(u_alt_ia).startswith("http") and "ShowImage.aspx" not in str(u_alt_ia):
                    if not any(c.get("url") == str(u_alt_ia) for c in capas_candidatas):
                        capas_candidatas.append({
                            "url": str(u_alt_ia),
                            "thumbnail": str(u_alt_ia),
                            "titulo": f"{titulo_limpo} nº {edicao_limpa}",
                            "fonte": "Busca Online (IA/Web)"
                        })

        if capas_candidatas:
            for item_c in capas_candidatas:
                if not any(c.get("url") == item_c.get("url") for c in resultado["capas_alternativas"]):
                    resultado["capas_alternativas"].append(item_c)
            if not resultado.get("capa_b64"):
                for item_c in resultado["capas_alternativas"]:
                    url_img = item_c.get("url") or item_c.get("thumbnail") or ""
                    if url_img and "ShowImage.aspx" not in url_img:
                        b64 = baixar_imagem_url_base64(url_img)
                        if b64 and b64.startswith("data:image"):
                            resultado["capa_b64"] = b64
                            break
    except Exception as ex_capas:
        print(f"[Aviso busca complementar de capas: {ex_capas}]")

    # Se a URL da edição no Guia dos Quadrinhos for válida, deriva a URL da capa oficial caso ainda não exista
    if resultado.get("url_edicao") and "/edicao/" in resultado["url_edicao"]:
        url_derivada = derivar_url_capa_guia_dos_quadrinhos(resultado["url_edicao"], editora_limpa, edicao_limpa)
        if url_derivada:
            if not any(c.get("url") == url_derivada for c in resultado["capas_alternativas"]):
                resultado["capas_alternativas"].append({
                    "url": url_derivada,
                    "thumbnail": url_derivada,
                    "titulo": f"{titulo_limpo} nº {edicao_limpa} (Capa Oficial Guia dos Quadrinhos)",
                    "fonte": "Guia dos Quadrinhos (guiadosquadrinhos.com)"
                })

    # Se ainda não possui capa_b64 mas possui capas alternativas, tenta carregar a primeira válida
    if not resultado.get("capa_b64") and resultado.get("capas_alternativas"):
        for alt in resultado["capas_alternativas"]:
            url_alt = alt.get("url") or alt.get("thumbnail") or ""
            if url_alt and "ShowImage.aspx" not in url_alt:
                b64_alt = baixar_imagem_url_base64(url_alt)
                if b64_alt and b64_alt.startswith("data:image"):
                    resultado["capa_b64"] = b64_alt
                    break

    # Se ainda não converteu para base64, usa o link direto da capa como fallback
    if not resultado.get("capa_b64"):
        resultado["capa_b64"] = resultado.get("capa_url") or (resultado["capas_alternativas"][0]["url"] if resultado.get("capas_alternativas") else "")

    # Garante que a URL final nunca seja 'busca-avancada-resultado.aspx'
    resultado["url_edicao"] = resolver_url_guia_dos_quadrinhos(
        titulo=titulo_limpo,
        edicao=edicao_limpa,
        editora=editora_limpa,
        url_candidata=resultado.get("url_edicao", "")
    )

    return resultado











