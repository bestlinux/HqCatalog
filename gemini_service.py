"""
Módulo de Integração com a API do Gemini (Google GenAI SDK)
Utiliza o modelo gemini-2.5-flash para visão computacional e identificação de HQs em fotos de prateleiras.
"""

import json
import re
import os
import time
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
     * "lido": "Lido" se o usuário mencionar que já leu, senão "Não Lido"
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
     * "novo_valor": Novo valor (ex: "Lido", 5, "Estante 2", etc.)
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
    Identifica a intenção (adicionar, remover, atualizar, etc.), extrai e enriquece os dados usando o Gemini.
    """
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
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
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
                if _eh_erro_sobrecarga(erro_str) and tentativa < max_retries_por_modelo:
                    time.sleep(1.0 * tentativa)
                else:
                    break

    # Fallback caso a IA não responda
    return {
        "acao": "desconhecido",
        "explicacao": f"Não foi possível processar o comando com a IA: {ultimo_erro}",
        "dados": {}
    }




