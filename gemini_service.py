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
7. "resumo": Um resumo conciso e envolvente da premissa ou enredo principal desta história/edição (em português, de 2 a 4 frases, descrevendo o contexto e a trama central da HQ).

Retorne ESTRITAMENTE um array JSON contendo os objetos identificados.
Exemplo de formato esperado:
[
  {
    "titulo": "Demolidor: A Queda de Murdock",
    "edicao": "Edição de Luxo",
    "editora": "Panini",
    "genero": "Super-heróis",
    "escritor": "Frank Miller",
    "ilustrador": "David Mazzucchelli",
    "resumo": "Karen Page vende a identidade secreta do Demolidor por uma dose de heroína. A informação chega ao Rei do Crime, que sistematicamente destrói a vida pessoal, financeira e psicológica de Matt Murdock até levá-lo ao limite."
  },
  {
    "titulo": "Watchmen",
    "edicao": "Edição Definitiva",
    "editora": "Panini",
    "genero": "Super-heróis",
    "escritor": "Alan Moore",
    "ilustrador": "Dave Gibbons",
    "resumo": "Em uma realidade alternativa nos anos 1980 em meio à Guerra Fria, o assassinato do vigilante Comediante desencadeia uma investigação liderada por Rorschach, revelando uma conspiração global que questiona a própria moralidade humana."
  },
  {
    "titulo": "Akira",
    "edicao": "Vol. 3",
    "editora": "JBC",
    "genero": "Ficção Científica",
    "escritor": "Katsuhiro Otomo",
    "ilustrador": "Katsuhiro Otomo",
    "resumo": "Na pós-apocalíptica Neo-Tóquio, gangues de motoqueiros colidem com experimentos militares psíquicos enquanto o poder destrutivo de Akira ameaça emergir novamente e devastar o que resta da civilização."
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
                        "ilustrador": str(item.get("ilustrador", "")).strip() or "Não informado",
                        "resumo": str(item.get("resumo", "")).strip()
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
                        "ilustrador": str(item.get("ilustrador", "")).strip() or "Não informado",
                        "resumo": str(item.get("resumo", "")).strip()
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
                        "ilustrador": str(item.get("ilustrador", "")).strip() or "Não informado",
                        "resumo": str(item.get("resumo", "")).strip()
                    } for item in dados["quadrinhos"] if isinstance(item, dict)
                ]
            return [{
                "titulo": str(dados.get("titulo", "")).strip(),
                "edicao": str(dados.get("edicao", "")).strip(),
                "editora": str(dados.get("editora", "")).strip(),
                "genero": str(dados.get("genero", "")).strip() or "Outro",
                "escritor": str(dados.get("escritor", "")).strip() or "Não informado",
                "ilustrador": str(dados.get("ilustrador", "")).strip() or "Não informado",
                "resumo": str(dados.get("resumo", "")).strip()
            }]
        return []
    except json.JSONDecodeError as e:
        raise ValueError(f"Falha ao interpretar o JSON retornado pela IA: {e}. Resposta bruta: {texto_resposta[:300]}")


import io
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError

FALLBACK_MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3-flash-preview"]


def redimensionar_para_ia(imagem: Any, max_dim: int = 1600) -> Any:
    """
    Otimiza a imagem para envio à IA:
    Reduz fotos gigantes de celular (12MP-50MP / 15MB) para ~1600px JPEG (~300KB),
    acelerando o upload e o processamento de 10s para menos de 1 segundo sem perder legibilidade.
    """
    if Image is None or not isinstance(imagem, Image.Image):
        return imagem

    img = imagem.convert("RGB")
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85, optimize=True)
    buffer.seek(0)
    return Image.open(buffer)


def processar_foto_prateleira(
    imagem: Any,
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.6-flash",
    max_retries: int = 3,
    status_callback: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Envia a imagem da prateleira ou capa para o modelo Gemini e retorna a lista de HQs identificadas.
    Inclui redimensionamento prévio, retry com backoff e fallback de modelo.
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
    modelo: str = "gemini-3.1-flash-lite",
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
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
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

                if _eh_erro_sobrecarga(erro_str) and tentativa < max_retries_por_modelo:
                    tempo_espera = 1.0 * tentativa
                    time.sleep(tempo_espera)
                else:
                    # Passa para o próximo modelo da lista
                    break

    return "Desculpe, ocorreu uma instabilidade temporária ao consultar a IA. Por favor, tente novamente em instantes."


# -------------------------------------------------------------
# PESQUISA E COTAÇÃO DE PREÇOS EM LOJAS COM GOOGLE SEARCH GROUNDING
# -------------------------------------------------------------
PROMPT_PESQUISA_PRECOS = """Você é um assistente especialista em cotação de HQs, Mangás, Graphic Novels e Edições Especiais no mercado brasileiro.
O usuário quer cotar/pesquisar os preços médios e disponibilidade da edição: "{termo}".

LOJAS ALVO DA COTAÇÃO:
1. Amazon (Amazon Brasil)
2. MagazineLuiza (Magalu)
3. MercadoLivre
4. Mundos Infinitos
5. Comix Book Shop

REGRAS:
- Retorne EXCLUSIVAMENTE um objeto JSON válido (sem textos ou markdown fora do JSON).
- Identifique a edição exata (Título, Volume/Edição, Editora).
- Para cada uma das 5 lojas:
  * "loja": nome exato ("Amazon", "MagazineLuiza", "MercadoLivre", "Mundos Infinitos", "Comix Book Shop")
  * "preco_str": preço médio/estimado de mercado em reais no formato "200,00" ou "140,00" se a loja costuma comercializar a edição, ou exatamente "Titulo não encontrado" caso seja um item raro/esgotado/indisponível na loja.
  * "preco_num": número float correspondente (ex: 140.0) ou 0.0 se não encontrado.
  * "status": "Encontrado" ou "Titulo não encontrado"
- "melhor_loja": a loja com o menor preco_num maior que zero (ou "" se nenhuma tiver).
- "melhor_preco": menor valor float encontrado (ou 0.0 se nenhuma tiver).

FORMATO JSON OBRIGATÓRIO:
{
    "titulo": "Nome Completo da HQ",
    "edicao": "Volume ou Edição",
    "editora": "Editora",
    "lojas": [
        {"loja": "Amazon", "preco_str": "200,00", "preco_num": 200.0, "status": "Encontrado"},
        {"loja": "MagazineLuiza", "preco_str": "140,00", "preco_num": 140.0, "status": "Encontrado"},
        {"loja": "MercadoLivre", "preco_str": "Titulo não encontrado", "preco_num": 0.0, "status": "Titulo não encontrado"},
        {"loja": "Mundos Infinitos", "preco_str": "180,00", "preco_num": 180.0, "status": "Encontrado"},
        {"loja": "Comix Book Shop", "preco_str": "Titulo não encontrado", "preco_num": 0.0, "status": "Titulo não encontrado"}
    ],
    "melhor_loja": "MagazineLuiza",
    "melhor_preco": 140.0
}
"""

import urllib.parse

def gerar_link_loja(loja: str, termo: str, link_sugerido: str = "") -> str:
    """Gera um link funcional e direto de busca para a loja especificada."""
    if link_sugerido and (link_sugerido.startswith("http://") or link_sugerido.startswith("https://")):
        return link_sugerido

    termo_enc = urllib.parse.quote(termo.strip())
    loja_low = loja.lower()

    if "amazon" in loja_low:
        return f"https://www.amazon.com.br/s?k={termo_enc}"
    elif "magazine" in loja_low or "magalu" in loja_low:
        return f"https://www.magazineluiza.com.br/busca/{termo_enc}/"
    elif "mercado" in loja_low:
        return f"https://lista.mercadolivre.com.br/{termo_enc}"
    elif "infinito" in loja_low:
        return f"https://mundosinfinitos.com.br/catalogsearch/result/?q={termo_enc}"
    elif "comix" in loja_low:
        return f"https://www.comix.com.br/catalogsearch/result/?q={termo_enc}"
    return ""


def _invocar_gemini_precos(client, modelo_alvo, prompt, config):
    try:
        resp = client.models.generate_content(
            model=modelo_alvo,
            contents=prompt,
            config=config
        )
        if resp and resp.text:
            parsed = limpar_e_parsear_json(resp.text)
            if isinstance(parsed, dict) and "lojas" in parsed:
                return parsed
            elif isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
                return parsed[0]
    except Exception:
        pass
    return None


def pesquisar_precos_hq(
    termo_busca: str,
    api_key: Optional[str] = None,
    modelo: str = "gemini-3.6-flash"
) -> Dict[str, Any]:
    """
    Pesquisa preços de uma HQ específica nas lojas de forma rápida, com timeout e sem travamento.
    """
    client = get_gemini_client(api_key)
    prompt = PROMPT_PESQUISA_PRECOS.replace("{termo}", termo_busca.strip())

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1
    )

    resultado = None

    # Modelos canônicos rápidos e válidos
    modelos_para_tentar = [modelo]
    for fb in ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]:
        if fb not in modelos_para_tentar:
            modelos_para_tentar.append(fb)

    for mod in modelos_para_tentar:
        for tentativa in range(1, 3):
            resultado = _invocar_gemini_precos(client, mod, prompt, config)
            if resultado:
                break
            time.sleep(1.0 * tentativa)
        if resultado:
            break

    if not resultado or not isinstance(resultado, dict):
        resultado = {
            "titulo": termo_busca.strip(),
            "edicao": "",
            "editora": "",
            "lojas": [
                {"loja": "Amazon", "preco_str": "Titulo não encontrado", "preco_num": 0.0, "status": "Titulo não encontrado"},
                {"loja": "MagazineLuiza", "preco_str": "Titulo não encontrado", "preco_num": 0.0, "status": "Titulo não encontrado"},
                {"loja": "MercadoLivre", "preco_str": "Titulo não encontrado", "preco_num": 0.0, "status": "Titulo não encontrado"},
                {"loja": "Mundos Infinitos", "preco_str": "Titulo não encontrado", "preco_num": 0.0, "status": "Titulo não encontrado"},
                {"loja": "Comix Book Shop", "preco_str": "Titulo não encontrado", "preco_num": 0.0, "status": "Titulo não encontrado"}
            ],
            "melhor_loja": "",
            "melhor_preco": 0.0,
            "link_melhor_oferta": ""
        }

    # Formata links e status
    termo_hq = f"{resultado.get('titulo', '')} {resultado.get('edicao', '')}".strip() or termo_busca.strip()
    lojas_padrao = ["Amazon", "MagazineLuiza", "MercadoLivre", "Mundos Infinitos", "Comix Book Shop"]
    lojas_resultado = resultado.get("lojas", [])
    lojas_finais = []

    for nome_padrao in lojas_padrao:
        item = next((x for x in lojas_resultado if x.get("loja", "").lower() == nome_padrao.lower() or nome_padrao.lower() in x.get("loja", "").lower()), None)
        if not item:
            item = {
                "loja": nome_padrao,
                "preco_str": "Titulo não encontrado",
                "preco_num": 0.0,
                "status": "Titulo não encontrado"
            }

        preco_raw = str(item.get("preco_str", "")).strip()
        if "não encontrado" in preco_raw.lower() or float(item.get("preco_num") or 0.0) <= 0:
            item["status"] = "Titulo não encontrado"
            item["preco_str"] = "Titulo não encontrado"
            item["preco_num"] = 0.0
            item["link"] = gerar_link_loja(nome_padrao, termo_hq)
        else:
            item["status"] = "Encontrado"
            item["link"] = gerar_link_loja(nome_padrao, termo_hq)

        lojas_finais.append(item)

    resultado["lojas"] = lojas_finais

    lojas_validas = [lj for lj in lojas_finais if lj.get("status") == "Encontrado" and float(lj.get("preco_num") or 0.0) > 0]
    if lojas_validas:
        melhor = min(lojas_validas, key=lambda x: float(x.get("preco_num")))
        resultado["melhor_loja"] = melhor.get("loja", "")
        resultado["melhor_preco"] = float(melhor.get("preco_num"))
        resultado["link_melhor_oferta"] = melhor.get("link", "")
    else:
        resultado["melhor_loja"] = ""
        resultado["melhor_preco"] = 0.0
        resultado["link_melhor_oferta"] = ""

    return resultado


def eh_intencao_pesquisa_preco(texto: str) -> bool:
    """Verifica se a mensagem do usuário é um pedido de busca de preço/cotação de HQ."""
    txt = texto.strip().lower()
    gatilhos = [
        "pesquis", "pesquise", "pesquisar", "busca", "busque", "preço", "preco",
        "quanto custa", "valor de", "cotação", "cotacao", "comprar", "oferta",
        "mundos infinitos", "comix", "amazon", "magalu", "mercadolivre"
    ]
    return any(g in txt for g in gatilhos)



