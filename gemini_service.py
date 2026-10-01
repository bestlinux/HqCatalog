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
from typing import List, Dict, Any, Optional
try:
    import requests
except ImportError:
    requests = None
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


def get_gemini_client(api_key: Optional[str] = None) -> Any:
    """
    Inicializa e retorna o cliente oficial do Google GenAI.
    Se a api_key não for passada, busca na variável de ambiente GEMINI_API_KEY.
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "Chave de API do Gemini não informada. "
            "Configure a variável de ambiente GEMINI_API_KEY ou informe-a na barra lateral do app."
        )
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
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-pro-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview"
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
    modelo: str = "gemini-3.6-flash",
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
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.1-pro-preview",
        "gemini-pro-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview"
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
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.1-pro-preview",
        "gemini-pro-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview"
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
def buscar_capas_online(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    escritor: str = "",
    limite: int = 8
) -> List[Dict[str, str]]:
    """
    Busca capas de quadrinhos, mangás e graphic novels online em múltiplos serviços:
    1. Apple Books / iTunes Search API (imagens oficiais em alta resolução)
    2. OpenLibrary Covers API
    3. SerpApi Google Images (se configurada)
    Retorna uma lista de dicionários contendo {'url', 'titulo', 'fonte', 'thumbnail'}.
    """
    capas: List[Dict[str, str]] = []
    urls_vistas = set()

    if not titulo or not titulo.strip():
        return []

    def add_capa(url: str, tit: str, fonte: str, thumb: Optional[str] = None):
        if not url or url in urls_vistas:
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            return
        urls_vistas.add(url)
        capas.append({
            "url": url,
            "titulo": tit or titulo,
            "fonte": fonte,
            "thumbnail": thumb or url
        })

    # Construção de termos de busca inteligentes
    termos = []
    if edicao:
        termos.append(f"{titulo} {edicao}".strip())
    if editora:
        termos.append(f"{titulo} {editora}".strip())
    if escritor and escritor != "Não informado":
        termos.append(f"{titulo} {escritor}".strip())
    termos.append(titulo.strip())

    termos_unicos = []
    for t in termos:
        if t and t not in termos_unicos:
            termos_unicos.append(t)

    # 1. Provedor Apple Books / iTunes
    if requests is not None:
        for termo in termos_unicos:
            if len(capas) >= limite:
                break
            try:
                r = requests.get(
                    "https://itunes.apple.com/search",
                    params={"term": termo, "media": "ebook", "country": "BR", "limit": 4},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                    timeout=5
                )
                if r.status_code == 200:
                    dados = r.json()
                    for item in dados.get("results", []):
                        art = item.get("artworkUrl100") or ""
                        if art:
                            highres = art.replace("100x100bb.jpg", "800x800bb.jpg").replace("100x100bb.png", "800x800bb.png")
                            item_tit = item.get("trackName") or titulo
                            add_capa(highres, item_tit, "Apple Books / iTunes", art)
            except Exception as ex:
                print(f"[Aviso iTunes search: {ex}]")

    # 2. Provedor OpenLibrary
    if requests is not None and len(capas) < limite:
        for termo in termos_unicos[:2]:
            if len(capas) >= limite:
                break
            try:
                r = requests.get(
                    "https://openlibrary.org/search.json",
                    params={"q": termo, "limit": 4},
                    headers={"User-Agent": "HqCatalog/1.0"},
                    timeout=5
                )
                if r.status_code == 200:
                    dados = r.json()
                    for doc in dados.get("docs", []):
                        cover_i = doc.get("cover_i")
                        if cover_i:
                            c_url = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg"
                            c_thumb = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
                            doc_tit = doc.get("title") or titulo
                            add_capa(c_url, doc_tit, "OpenLibrary", c_thumb)
            except Exception as ex:
                print(f"[Aviso OpenLibrary search: {ex}]")

    # 3. Provedor SerpApi Google Images (se configurada)
    serp_key = os.getenv("SERPAPI_API_KEY", "")
    if serp_key and len(capas) < limite:
        try:
            import serpapi
            client = serpapi.Client(api_key=serp_key)
            query_img = f"{titulo} {edicao} {editora} capa".strip()
            res = client.search({"engine": "google_images", "q": query_img, "gl": "br", "hl": "pt-br", "num": 5})
            for img_it in res.get("images_results", []):
                orig = img_it.get("original") or img_it.get("thumbnail")
                if orig:
                    add_capa(orig, img_it.get("title", titulo), "Google Images", img_it.get("thumbnail"))
        except Exception as ex:
            print(f"[Aviso SerpApi Images: {ex}]")

    return capas[:limite]


def baixar_imagem_url_base64(url: str, max_dim: int = 800, quality: int = 85, timeout: int = 8) -> str:
    """
    Baixa uma imagem a partir de uma URL e converte em string base64 JPEG compacta.
    Se não for possível baixar ou processar, retorna a própria URL original.
    """
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return url

    if requests is None or Image is None:
        return url

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=timeout)
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
        print(f"[Aviso ao baixar imagem {url}: {ex}]")

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

    modelos = [modelo, "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview"]
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

    modelos = [modelo, "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview"]
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

    modelos = [modelo, "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"]
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

    modelos = [modelo, "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"]
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







