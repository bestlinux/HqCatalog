"""
Módulo JEV (Joint Evaluator & TypeSafe Decision Models - System 1 AI Engine)
Implementa modelos e rotinas determinísticas e probabilísticas tipadas (TypeSafe)
para decisões ultrarrápidas, roteamento de intenção, validação de schemas
e deduplicação probabilística (Entity Resolution) no catálogo de HQs.
"""

import re
import unicodedata
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field, field_validator, ConfigDict


# =====================================================================
# 1. SCHEMAS E ENUMS TIPADOS DO DOMÍNIO (TypeSafe Contracts)
# =====================================================================

class GeneroEnum(str, Enum):
    SUPER_HEROIS = "Super-heróis"
    MANGA_SHONEN = "Mangá / Shonen"
    MANGA_SEINEN = "Mangá / Seinen"
    TERROR = "Terror"
    FICCAO_CIENTIFICA = "Ficção Científica"
    FANTASIA = "Fantasia"
    AVENTURA = "Aventura"
    DRAMA = "Drama"
    HISTORICO = "Histórico"
    BIOGRAFIA = "Biografia"
    SUSPENSE_POLICIAL = "Suspense / Policial"
    HUMOR = "Humor"
    INFANTIL = "Infantil"
    OUTRO = "Outro"


class StatusLeituraEnum(str, Enum):
    NAO_LIDO = "Não Lido"
    LIDO = "Lido"
    LENDO = "Lendo"
    QUERO_LER = "Quero Ler"


class IntencaoEnum(str, Enum):
    ADICIONAR = "ADICIONAR"
    REMOVER = "REMOVER"
    ATUALIZAR_STATUS = "ATUALIZAR_STATUS"
    ATUALIZAR_DADOS = "ATUALIZAR_DADOS"
    BUSCAR_PRECO = "BUSCAR_PRECO"
    ORDEM_LEITURA = "ORDEM_LEITURA"
    CONSULTAR_CATALOGO = "CONSULTAR_CATALOGO"
    CONVERSA_GERAL = "CONVERSA_GERAL"


class ItemHqJEV(BaseModel):
    """Schema rigorosamente tipado e sanitizado para qualquer HQ no catálogo."""
    model_config = ConfigDict(use_enum_values=True)

    titulo: str = Field(..., min_length=1, description="Título canônico da HQ")
    edicao: str = Field(default="", description="Volume ou número da edição")
    editora: str = Field(default="Desconhecida", description="Editora responsável")
    genero: str = Field(default=GeneroEnum.OUTRO.value, description="Gênero canônico")
    escritor: str = Field(default="Não informado", description="Roteirista")
    ilustrador: str = Field(default="Não informado", description="Desenhista")
    prateleira: str = Field(default="Estante 1 - Prateleira 1", description="Localização física")
    lido: str = Field(default=StatusLeituraEnum.NAO_LIDO.value, description="Status de leitura")
    avaliacao: int = Field(default=0, ge=0, le=5, description="Avaliação de 0 a 5 estrelas")
    valor: float = Field(default=0.0, ge=0.0, description="Valor da HQ em Reais (R$)")
    estado_conservacao: str = Field(default="Excelente", description="Estado de conservação da HQ")
    capa: str = Field(default="", description="URL ou base64 da capa")
    resumo: str = Field(default="", description="Sinopse ou resumo")
    resenha: str = Field(default="", description="Resenha pessoal do usuário")

    @field_validator("titulo", mode="before")
    @classmethod
    def sanitizar_titulo(cls, v: Any) -> str:
        s = str(v or "").strip().strip("\"'“”")
        s = re.sub(r"[\s\-–—:]+$", "", s).strip()
        return s or "Sem título"

    @field_validator("edicao", mode="before")
    @classmethod
    def sanitizar_edicao(cls, v: Any) -> str:
        s = str(v or "").strip().strip("\"'“”")
        return s

    @field_validator("valor", mode="before")
    @classmethod
    def sanitizar_valor(cls, v: Any) -> float:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return max(0.0, float(v))
        s = str(v).replace("R$", "").replace("r$", "").replace(" ", "").strip()
        if not s:
            return 0.0
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            return max(0.0, float(s))
        except (ValueError, TypeError):
            return 0.0

    @field_validator("estado_conservacao", mode="before")
    @classmethod
    def sanitizar_estado(cls, v: Any) -> str:
        s = str(v or "").strip().strip("\"'“”")
        return s or "Excelente"

    @field_validator("genero", mode="before")
    @classmethod
    def validar_genero(cls, v: Any) -> str:
        return normalizar_genero_canonico(str(v or ""))

    @field_validator("lido", mode="before")
    @classmethod
    def validar_status(cls, v: Any) -> str:
        s = str(v or "").strip()
        mapeamento = {
            "lido": StatusLeituraEnum.LIDO.value,
            "sim": StatusLeituraEnum.LIDO.value,
            "lendo": StatusLeituraEnum.LENDO.value,
            "em leitura": StatusLeituraEnum.LENDO.value,
            "quero ler": StatusLeituraEnum.QUERO_LER.value,
            "desejo ler": StatusLeituraEnum.QUERO_LER.value,
        }
        return mapeamento.get(s.lower(), StatusLeituraEnum.NAO_LIDO.value if s.lower() in ("não lido", "nao lido", "não", "nao") else (s or StatusLeituraEnum.NAO_LIDO.value))

    @field_validator("avaliacao", mode="before")
    @classmethod
    def validar_avaliacao(cls, v: Any) -> int:
        try:
            val = int(v or 0)
            return max(0, min(5, val))
        except (ValueError, TypeError):
            return 0


class ProbabilisticDuplicateDecision(BaseModel):
    """Resultado da avaliação probabilística de duplicidade."""
    is_duplicate: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    existing_id: Optional[int] = None
    existing_title: Optional[str] = None
    similarity_score: float = 0.0
    requires_human_confirmation: bool = False


class IntentDecision(BaseModel):
    """Resultado da classificação e roteamento de intenção System 1."""
    intent: IntencaoEnum
    confidence: float = Field(ge=0.0, le=1.0)
    entities: Dict[str, Any] = Field(default_factory=dict)
    requires_system2: bool = False
    suggested_action: str = ""


# =====================================================================
# 2. NORMALIZADORES & CANONICALIZADORES SYSTEM 1
# =====================================================================

def remover_acentos_e_pontuacao(texto: str) -> str:
    """Remove diacríticos e normaliza caracteres para comparação pura."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', texto)
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    sem_pont = re.sub(r'[^\w\s]', ' ', sem_acento.lower())
    return " ".join(sem_pont.split())


def normalizar_genero_canonico(genero_raw: str) -> str:
    """Mapeia qualquer saída livre para um GeneroEnum canônico."""
    if not genero_raw:
        return GeneroEnum.OUTRO.value

    g_clean = remover_acentos_e_pontuacao(genero_raw)

    if any(k in g_clean for k in ["super heroi", "super herois", "marvel", "dc", "heroi", "vigilante"]):
        return GeneroEnum.SUPER_HEROIS.value
    if any(k in g_clean for k in ["shonen", "manga shonen", "shounen"]):
        return GeneroEnum.MANGA_SHONEN.value
    if any(k in g_clean for k in ["seinen", "manga seinen", "eroguro"]):
        return GeneroEnum.MANGA_SEINEN.value
    if any(k in g_clean for k in ["terror", "horror", "medo", "gore", "sobrenatural"]):
        return GeneroEnum.TERROR.value
    if any(k in g_clean for k in ["ficcao cientifica", "sci fi", "cyberpunk", "espacial"]):
        return GeneroEnum.FICCAO_CIENTIFICA.value
    if any(k in g_clean for k in ["fantasia", "magia", "medieval", "espada"]):
        return GeneroEnum.FANTASIA.value
    if any(k in g_clean for k in ["aventura", "exploracao", "acao"]):
        return GeneroEnum.AVENTURA.value
    if any(k in g_clean for k in ["biografia", "autobiografia", "memoria"]):
        return GeneroEnum.BIOGRAFIA.value
    if any(k in g_clean for k in ["historico", "historia", "guerra", "documental"]):
        return GeneroEnum.HISTORICO.value
    if any(k in g_clean for k in ["policial", "noir", "crime", "suspense", "investigacao", "detetive"]):
        return GeneroEnum.SUSPENSE_POLICIAL.value
    if any(k in g_clean for k in ["humor", "comedia", "tiras", "satira"]):
        return GeneroEnum.HUMOR.value
    if any(k in g_clean for k in ["infantil", "turma da monica", "disney", "crianca"]):
        return GeneroEnum.INFANTIL.value
    if any(k in g_clean for k in ["drama", "cotidiano", "romance"]):
        return GeneroEnum.DRAMA.value

    return GeneroEnum.OUTRO.value


# =====================================================================
# 3. ENTITY RESOLUTION & DEDUPLICAÇÃO PROBABILÍSTICA (JEV Decider)
# =====================================================================

def calcular_similaridade_strings(s1: str, s2: str) -> float:
    """Calcula similaridade semântica/léxica Jaccard de tokens normalizados."""
    t1 = remover_acentos_e_pontuacao(s1)
    t2 = remover_acentos_e_pontuacao(s2)

    if not t1 or not t2:
        return 0.0
    if t1 == t2:
        return 1.0

    palavras1 = set(t1.split())
    palavras2 = set(t2.split())

    # Remove stopwords comuns
    stopwords = {"de", "do", "da", "dos", "das", "o", "a", "os", "as", "e", "em", "um", "uma", "the", "of", "and"}
    p1 = {w for w in palavras1 if w not in stopwords}
    p2 = {w for w in palavras2 if w not in stopwords}

    if not p1 or not p2:
        p1, p2 = palavras1, palavras2

    intersecao = len(p1.intersection(p2))
    uniao = len(p1.union(p2))
    
    jaccard = (intersecao / uniao) if uniao > 0 else 0.0

    # Bônus para contenção de substring
    if t1 in t2 or t2 in t1:
        jaccard = max(jaccard, 0.85)

    return min(1.0, max(0.0, jaccard))


def decidir_duplicata_probabilistica(
    hq_candidata: Dict[str, Any],
    acervo_existente: List[Dict[str, Any]],
    threshold_auto: float = 0.85,
    threshold_duvida: float = 0.65
) -> ProbabilisticDuplicateDecision:
    """
    Avalia probabilisticamente se uma HQ candidata já existe no acervo.
    Combina pesos de Título (55%), Edição (30%) e Editora (15%).
    """
    tit_cand = str(hq_candidata.get("titulo") or "").strip()
    ed_cand = str(hq_candidata.get("edicao") or "").strip()
    edit_cand = str(hq_candidata.get("editora") or "").strip()

    if acervo_existente is None:
        acervo_existente = []
    elif hasattr(acervo_existente, "to_dict"):
        try:
            acervo_existente = acervo_existente.to_dict("records")
        except Exception:
            acervo_existente = []

    if not tit_cand or not acervo_existente:
        return ProbabilisticDuplicateDecision(
            is_duplicate=False,
            confidence=1.0,
            reason="Título vazio ou acervo vazio",
            similarity_score=0.0
        )

    melhor_score = 0.0
    melhor_hq: Optional[Dict[str, Any]] = None
    motivo_detectado = ""

    ed_cand_norm = remover_acentos_e_pontuacao(ed_cand)
    # Extrai dígitos se houver
    num_cand = re.findall(r'\d+', ed_cand)

    for hq_ex in acervo_existente:
        tit_ex = str(hq_ex.get("titulo") or "").strip()
        ed_ex = str(hq_ex.get("edicao") or "").strip()
        edit_ex = str(hq_ex.get("editora") or "").strip()

        sim_tit = calcular_similaridade_strings(tit_cand, tit_ex)
        
        # Match de edição
        ed_ex_norm = remover_acentos_e_pontuacao(ed_ex)
        num_ex = re.findall(r'\d+', ed_ex)

        if ed_cand_norm == ed_ex_norm:
            score_ed = 1.0
        elif num_cand and num_ex and num_cand[0] == num_ex[0]:
            score_ed = 0.95
        elif not ed_cand and not ed_ex:
            score_ed = 0.90
        elif not ed_cand or not ed_ex:
            score_ed = 0.50
        else:
            score_ed = 0.0

        # Match de editora
        sim_edit = calcular_similaridade_strings(edit_cand, edit_ex)
        if edit_cand.lower() in ("desconhecida", "") or edit_ex.lower() in ("desconhecida", ""):
            score_edit = 0.70  # Neutro se uma for desconhecida
        elif sim_edit >= 0.5:
            score_edit = 1.0
        else:
            score_edit = 0.2

        # Cálculo da probabilidade composta
        score_composto = (0.55 * sim_tit) + (0.30 * score_ed) + (0.15 * score_edit)

        if score_composto > melhor_score:
            melhor_score = score_composto
            melhor_hq = hq_ex
            motivo_detectado = (
                f"Correspondência com ID #{hq_ex.get('id')}: '{tit_ex}' "
                f"(Edição: '{ed_ex}', Editora: '{edit_ex}') - Score: {score_composto:.2f}"
            )

    if melhor_hq and melhor_score >= threshold_auto:
        return ProbabilisticDuplicateDecision(
            is_duplicate=True,
            confidence=round(melhor_score, 3),
            reason=motivo_detectado,
            existing_id=melhor_hq.get("id"),
            existing_title=melhor_hq.get("titulo"),
            similarity_score=round(melhor_score, 3),
            requires_human_confirmation=False
        )
    elif melhor_hq and melhor_score >= threshold_duvida:
        return ProbabilisticDuplicateDecision(
            is_duplicate=False,
            confidence=round(melhor_score, 3),
            reason=f"Possível duplicata similar (ID #{melhor_hq.get('id')}: '{melhor_hq.get('titulo')}').",
            existing_id=melhor_hq.get("id"),
            existing_title=melhor_hq.get("titulo"),
            similarity_score=round(melhor_score, 3),
            requires_human_confirmation=True
        )

    return ProbabilisticDuplicateDecision(
        is_duplicate=False,
        confidence=round(1.0 - melhor_score, 3),
        reason="Nenhuma duplicata relevante detectada",
        similarity_score=round(melhor_score, 3),
        requires_human_confirmation=False
    )


# =====================================================================
# 4. CLASSIFICADOR & ROTEADOR DE INTENÇÃO SYSTEM 1
# =====================================================================

def classificar_intencao_system1(texto: str) -> IntentDecision:
    """
    Classifica a intenção do comando em linguagem natural de forma ultrarrápida (<5ms).
    Decide se a ação pode ser executada deterministicamente ou se requer o LLM System 2.
    """
    t_clean = remover_acentos_e_pontuacao(texto)
    
    # 1. Pesquisa de Preço / Onde Comprar
    padroes_preco = ["onde comprar", "qual o preco", "preco de", "quanto custa", "menor preco", "promocao de", "comprar"]
    if any(p in t_clean for p in padroes_preco):
        # Extrai termo de busca removendo o prefixo
        termo = texto
        for p in padroes_preco:
            termo = re.sub(re.escape(p), "", termo, flags=re.IGNORECASE)
        termo = termo.strip().strip("?:!.,")
        return IntentDecision(
            intent=IntencaoEnum.BUSCAR_PRECO,
            confidence=0.96,
            entities={"termo_busca": termo or texto},
            requires_system2=False,
            suggested_action="pesquisar_precos"
        )

    # 2. Ordem de Leitura / Cronologia
    padroes_ordem = ["ordem de leitura", "cronologia", "ordem cronologica", "como ler", "guia de leitura"]
    if any(p in t_clean for p in padroes_ordem):
        return IntentDecision(
            intent=IntencaoEnum.ORDEM_LEITURA,
            confidence=0.94,
            entities={"tema": texto},
            requires_system2=True,
            suggested_action="gerar_ordem_leitura"
        )

    # 3. Atualizar Status de Leitura (ex: "marque Batman como lido")
    match_status = re.search(
        r'(?:marqu?e|coloqu?e|mude|altere)\s+(?:o|a|os|as)?\s*(.*?)\s+(?:como|para)?\s*(lido|nao lido|não lido|lendo|quero ler)',
        texto,
        re.IGNORECASE
    )
    if match_status:
        titulo_extraido = match_status.group(1).strip()
        novo_status = match_status.group(2).strip().title()
        return IntentDecision(
            intent=IntencaoEnum.ATUALIZAR_STATUS,
            confidence=0.92,
            entities={"titulo": titulo_extraido, "novo_status": novo_status},
            requires_system2=False,
            suggested_action="atualizar_status_leitura"
        )

    # 4. Remoção / Exclusão (ex: "delete a HQ ID 15", "remover a HQ ID #42")
    match_remover_id = re.search(
        r'(?:remover?|remov[ae]|deletar?|delet[ae]|excluir?|exclu[ia]|apagar?|apagu?e)\s+(?:.*?\s+)?(?:id\s*#?|#)?\s*(\d+)',
        texto,
        re.IGNORECASE
    )
    if match_remover_id:
        return IntentDecision(
            intent=IntencaoEnum.REMOVER,
            confidence=0.98,
            entities={"id": int(match_remover_id.group(1))},
            requires_system2=False,
            suggested_action="remover_por_id"
        )

    # 5. Adicionar / Cadastro em Linguagem Natural Simples
    match_add = re.search(
        r'(?:adicionar?|adicion[ae]|cadastrar?|cadastr[ae]|incluir?|inclu[ia])\s+(?:o|a)?\s*(.*)',
        texto,
        re.IGNORECASE
    )
    if match_add:
        detalhes = match_add.group(1).strip()
        return IntentDecision(
            intent=IntencaoEnum.ADICIONAR,
            confidence=0.88,
            entities={"comando_bruto": detalhes},
            requires_system2=True,  # Requer IA para enriquecer autor, desenhista, editora
            suggested_action="crud_assistido"
        )

    # 6. Caso padrão: Consulta ao Catálogo ou Chat Geral
    return IntentDecision(
        intent=IntencaoEnum.CONVERSA_GERAL,
        confidence=0.75,
        entities={"pergunta": texto},
        requires_system2=True,
        suggested_action="consultar_chatbot"
    )


# =====================================================================
# 5. HIGIENIZADOR & FACTORY TYPESAFE
# =====================================================================

def validar_e_tipar_hq(
    dados_item: Dict[str, Any],
    prateleira_padrao: str = "Estante 1 - Prateleira 1",
    lido_padrao: str = "Não Lido"
) -> Dict[str, Any]:
    """
    Valida um dicionário através do schema Pydantic ItemHqJEV,
    garantindo tipos estritos, normalização de gêneros e valores padrão.
    """
    item_dict = dict(dados_item)

    if prateleira_padrao and not item_dict.get("prateleira"):
        item_dict["prateleira"] = prateleira_padrao
    if not item_dict.get("lido"):
        item_dict["lido"] = lido_padrao

    # Cria e valida com Pydantic
    obj_tipado = ItemHqJEV(**item_dict)
    return obj_tipado.model_dump()
