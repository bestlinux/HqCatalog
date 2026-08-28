"""
Módulo de Integração com a API do Gemini (Google GenAI SDK)
Utiliza o modelo gemini-2.5-flash para visão computacional e identificação de HQs em fotos de prateleiras.
"""

import json
import re
import os
from typing import List, Dict, Any, Optional
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


PROMPT_SISTEMA_HQS = """Você é um especialista em catalogação de histórias em quadrinhos (HQs, graphic novels, mangás, encadernados e gibis).
Analise a imagem da prateleira/estante fornecida com máxima atenção às lombadas e capas visíveis.

Identifique CADA HQ individualmente na foto da esquerda para a direita (ou de cima para baixo).

Extraia as seguintes informações para cada item:
1. "titulo": Nome completo e correto do quadrinho / série / arco (ex: "Batman: O Cavaleiro das Trevas", "Sandman - Edição Definitiva Vol. 1", "Turma da Mônica - Laços", "Berserk").
2. "edicao": Número da edição ou do volume (ex: "1", "Vol. 2", "Edição Especial", "#104", ou "" caso não haja número explícito).
3. "editora": Nome da editora responsável pela publicação (ex: "Panini", "Pipoca & Nanquim", "Mythos", "JBC", "Devir", "Marvel", "DC Comics", "Image", "Dark Horse", "Abril", "Veneta", ou "Desconhecida" se não for visível).
4. "genero": Gênero literário/temático principal da obra (ex: "Super-heróis", "Terror", "Aventura", "Ficção Científica", "Fantasia", "Drama", "Mangá / Shonen", "Mangá / Seinen", "Suspense / Policial", "Humor", "Infantil", "Histórico", "Biografia", ou "Outro").
5. "escritor": Nome do(s) roteirista(s) ou escritor(es) principal(is) da obra (ex: "Alan Moore", "Neil Gaiman", "Frank Miller", "Stan Lee", "Akira Toriyama", "Mauricio de Sousa", ou "Não informado" se não identificar).
6. "ilustrador": Nome do(s) desenhista(s), ilustrador(es) ou artista(s) principal(is) da obra (ex: "Dave Gibbons", "Jim Lee", "Todd McFarlane", "Alex Ross", "Katsuhiro Otomo", "Kentaro Miura", ou "Não informado" se não identificar).

Retorne ESTRITAMENTE um array JSON contendo os objetos identificados.
Exemplo de formato esperado:
[
  {
    "titulo": "Demolidor: A Queda de Murdock",
    "edicao": "Edição de Luxo",
    "editora": "Panini",
    "genero": "Super-heróis",
    "escritor": "Frank Miller",
    "ilustrador": "David Mazzucchelli"
  },
  {
    "titulo": "Watchmen",
    "edicao": "Edição Definitiva",
    "editora": "Panini",
    "genero": "Super-heróis",
    "escritor": "Alan Moore",
    "ilustrador": "Dave Gibbons"
  },
  {
    "titulo": "Akira",
    "edicao": "Vol. 3",
    "editora": "JBC",
    "genero": "Ficção Científica",
    "escritor": "Katsuhiro Otomo",
    "ilustrador": "Katsuhiro Otomo"
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
            # Garante que cada item tenha as chaves esperadas
            itens_higienizados = []
            for item in dados:
                if isinstance(item, dict):
                    itens_higienizados.append({
                        "titulo": str(item.get("titulo", "")).strip(),
                        "edicao": str(item.get("edicao", "")).strip(),
                        "editora": str(item.get("editora", "")).strip(),
                        "genero": str(item.get("genero", "")).strip() or "Outro",
                        "escritor": str(item.get("escritor", "")).strip() or "Não informado",
                        "ilustrador": str(item.get("ilustrador", "")).strip() or "Não informado"
                    })
            return itens_higienizados
        elif isinstance(dados, dict):
            # Caso a IA retorne um único objeto ou embrulhado em uma chave (ex: {"hqs": [...]})
            if "hqs" in dados and isinstance(dados["hqs"], list):
                return [
                    {
                        "titulo": str(item.get("titulo", "")).strip(),
                        "edicao": str(item.get("edicao", "")).strip(),
                        "editora": str(item.get("editora", "")).strip(),
                        "genero": str(item.get("genero", "")).strip() or "Outro",
                        "escritor": str(item.get("escritor", "")).strip() or "Não informado",
                        "ilustrador": str(item.get("ilustrador", "")).strip() or "Não informado"
                    } for item in dados["hqs"] if isinstance(item, dict)
                ]
            elif "quadrinhos" in dados and isinstance(dados["quadrinhos"], list):
                return [
                    {
                        "titulo": str(item.get("titulo", "")).strip(),
                        "edicao": str(item.get("edicao", "")).strip(),
                        "editora": str(item.get("editora", "")).strip(),
                        "genero": str(item.get("genero", "")).strip() or "Outro",
                        "escritor": str(item.get("escritor", "")).strip() or "Não informado",
                        "ilustrador": str(item.get("ilustrador", "")).strip() or "Não informado"
                    } for item in dados["quadrinhos"] if isinstance(item, dict)
                ]
            return [{
                "titulo": str(dados.get("titulo", "")).strip(),
                "edicao": str(dados.get("edicao", "")).strip(),
                "editora": str(dados.get("editora", "")).strip(),
                "genero": str(dados.get("genero", "")).strip() or "Outro",
                "escritor": str(dados.get("escritor", "")).strip() or "Não informado",
                "ilustrador": str(dados.get("ilustrador", "")).strip() or "Não informado"
            }]
        return []
    except json.JSONDecodeError as e:
        raise ValueError(f"Falha ao interpretar o JSON retornado pela IA: {e}. Resposta bruta: {texto_resposta[:300]}")


import time

FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3-flash", "gemini-2.5-flash"]


def processar_foto_prateleira(
    imagem: Any,
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.6-flash",
    max_retries: int = 3,
    status_callback: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Envia a imagem da prateleira para o modelo Gemini e retorna a lista de HQs identificadas.
    Inclui retry automático com backoff exponencial e fallback de modelo caso ocorra 503 (servidor sobrecarregado).
    
    Args:
        imagem: Objeto PIL.Image da foto capturada.
        api_key: Chave de API opcional.
        modelo: Nome do modelo Gemini a ser utilizado (padrão: gemini-3.6-flash).
        max_retries: Quantidade máxima de tentativas por modelo em caso de 503.
        status_callback: Função callback para enviar mensagens de status à UI (ex: st.write ou st.info).
        
    Returns:
        Lista de dicionários [{'titulo': ..., 'edicao': ..., 'editora': ...}]
    """
    client = get_gemini_client(api_key)

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,  # Baixa temperatura para respostas determinísticas e precisas
    )

    # Lista ordenada de modelos para tentar (começa pelo escolhido, seguido pelos fallbacks)
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
                    contents=[imagem, PROMPT_SISTEMA_HQS],
                    config=config
                )

                if not response or not response.text:
                    return []

                return limpar_e_parsear_json(response.text)

            except Exception as ex:
                erro_str = str(ex)
                ultimo_erro = ex
                
                # Identifica se é erro de sobrecarga temporária da API (503 UNAVAILABLE ou 429 RATE_LIMIT)
                eh_sobrecarga = (
                    "503" in erro_str or
                    "UNAVAILABLE" in erro_str or
                    "high demand" in erro_str or
                    "429" in erro_str or
                    "RESOURCE_EXHAUSTED" in erro_str
                )

                if eh_sobrecarga:
                    tempo_espera = 2 ** tentativa  # 2s, 4s, 8s
                    if status_callback:
                        status_callback(
                            f"⚠️ Servidor do Gemini com alta demanda ({mod}). Aguardando {tempo_espera}s antes de tentar novamente..."
                        )
                    time.sleep(tempo_espera)
                else:
                    # Se for outro tipo de erro (ex: 404 de modelo não encontrado), pula logo para o próximo modelo
                    break

    # Se todas as tentativas e modelos falharem, lança o último erro
    raise RuntimeError(
        f"Não foi possível processar a imagem após várias tentativas devido à sobrecarga temporária da API do Google: {ultimo_erro}"
    )
