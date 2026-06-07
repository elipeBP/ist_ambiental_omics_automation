"""
Computação centralizada de métricas e insights analíticos.

Consumida por:
  - src/ui/pages/4_Insights_Analiticos.py  (renderização Streamlit)
  - src/reports/pdf_builder.py             (geração PDF)

Aceita o DataFrame bruto de qualquer batch (vw_ranking_candidatos ou
vw_ranking_historico) e retorna um dict com todos os indicadores computados.
"""
import re

import pandas as pd

# ---------------------------------------------------------------------------
# Classificação química amigável
# ---------------------------------------------------------------------------

# Mapeamento keyword → categoria PT-BR (ordem importa: mais específico primeiro)
_CATEGORIA_RULES: list[tuple[list[str], str]] = [
    # Peptídeos e derivados
    (["cyclopeptide", "cyclic peptide", "orbitide"],           "Peptídeo Cíclico"),
    (["polypeptide", "oligopeptide", "tetrapeptide",
      "tripeptide", "dipeptide", "peptide"],                   "Peptídeo"),
    # Aminoácidos
    (["alpha-amino acid", "amino acid", "aminoacid",
      "glutamine derivative", "leucine derivative",
      "non-proteinogenic"],                                     "Aminoácido"),
    # Lipídios
    (["fatty acid", "lipid", "phospholipid", "sphingolipid",
      "glycerolipid", "ceramide", "triacylglycerol",
      "diacylglycerol", "lysophospholipid"],                   "Lipídio"),
    # Carboidratos
    (["monosaccharide", "disaccharide", "oligosaccharide",
      "polysaccharide", "carbohydrate", "sugar", "glycan"],    "Carboidrato"),
    # Flavonoides / Polifenóis
    (["flavonoid", "flavone", "flavonol", "flavanone",
      "isoflavone", "anthocyanin", "chalcone",
      "4-coumarate", "phenylpropanoid"],                       "Flavonoide"),
    # Esteroides
    (["steroid", "sterol", "corticosteroid",
      "3-oxo-delta", "glucocorticoid"],                        "Esteroide"),
    # Alcaloides
    (["alkaloid", "indolecarboxamide", "indole alkaloid",
      "hydroxypiperidine", "isoquinoline", "purine alkaloid"], "Alcaloide"),
    # Ácidos orgânicos
    (["organic acid", "carboxylic acid", "dicarboxylic",
      "monocarboxylic", "citrate", "benzoate", "malate",
      "lactate", "acetate"],                                   "Ácido Orgânico"),
    # Vitaminas / cofatores
    (["vitamin", "coenzyme", "cofactor", "cobalamin"],         "Vitamina / Cofator"),
    # Nucleosídeos / nucleotídeos
    (["nucleoside", "nucleotide", "purine", "pyrimidine",
      "adenosine", "guanosine", "cytidine"],                   "Nucleosídeo / Nucleotídeo"),
    # Terpenoides
    (["terpene", "terpenoid", "monoterpene",
      "diterpene", "sesquiterpene", "triterpene"],              "Terpenoide"),
    # Fosfatos orgânicos
    (["organophosphate", "aryl phosphate",
      "phosphate ester"],                                      "Fosfato Orgânico"),
    # Halogenados
    (["organofluorine", "organochlorine", "organobromine",
      "haloalkyl", "organic chloride", "organic fluoride"],    "Halogenado"),
    # Heterocíclicos (depois de alcaloides/nucleosídeos)
    (["thiazole", "benzothiazole", "benzothiophene",
      "imidazole", "quinoline", "oxazole", "furan",
      "pyridine", "thiophene"],                                "Heterocíclico"),
]

# Abreviações de aminoácidos comuns — usadas na Camada 2 (heurística por nome)
_AA_ABBREVS = {
    "ala", "arg", "asn", "asp", "cys", "gln", "glu", "gly",
    "his", "ile", "leu", "lys", "met", "phe", "pro", "ser",
    "thr", "trp", "tyr", "val",
}

_NAO_CLASSIFICADO = "Não classificado"


def classificar_categoria(classe_quimica: str, nome: str = "") -> str:
    """
    Converte o campo classe_quimica (termos ChEBI técnicos) em uma
    categoria amigável em português.

    Camada 1 — keyword matching em classe_quimica.
    Camada 2 — heurística conservadora no nome da molécula.
    Camada 3 — "Não classificado".

    Nunca retorna None ou string vazia.
    """
    cq = (classe_quimica or "").strip().lower()
    nm = (nome or "").strip().lower()

    # Valores que indicam ausência de classificação
    if cq in ("", "none", "nao classificada", "não classificada", "nao_classificada"):
        cq = ""

    # Camada 1 — keyword matching
    if cq:
        for keywords, categoria in _CATEGORIA_RULES:
            if any(kw in cq for kw in keywords):
                return categoria

    # Camada 2 — heurística no nome (apenas quando Camada 1 falhou)
    if nm:
        # Nome no padrão de sequência peptídica: "ala-pro-arg-leu" etc.
        partes = re.split(r"[-\s]", nm)
        if len(partes) >= 2 and all(p in _AA_ABBREVS for p in partes if p):
            return "Peptídeo (estimado)"
        if "cyclo(" in nm:
            return "Peptídeo Cíclico (estimado)"
        if "acid" in nm and "amino" in nm:
            return "Aminoácido (estimado)"

    return _NAO_CLASSIFICADO

# ---------------------------------------------------------------------------
# Constantes: hierarquia IST de critérios de desempate
# ---------------------------------------------------------------------------

CRITERIO_ORDER = [
    "fragmentacao", "score_lab", "isotopo", "massa",
    "formula", "unico", "empate_humano",
]

CRITERIO_LABEL = {
    "fragmentacao":  "Fragmentação MS/MS",
    "score_lab":     "Score Lab",
    "isotopo":       "Padrão Isotópico",
    "massa":         "Erro de Massa",
    "formula":       "Fórmula",
    "unico":         "Candidato único",
    "empate_humano": "Empate — decisão humana",
}

CRITERIO_COLOR = {
    "fragmentacao":  "#2e75b6",
    "score_lab":     "#4472c4",
    "isotopo":       "#5a9e6f",
    "massa":         "#70ad47",
    "formula":       "#a8c9a5",
    "unico":         "#9e9e9e",
    "empate_humano": "#e57373",
}

SCORE_TIER_ALTA     = 80
SCORE_TIER_MODERADA = 45


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def computar_insights(df: pd.DataFrame) -> dict:
    """
    Processa o DataFrame de um batch e devolve todos os indicadores necessários
    para a página de Insights e para a geração do relatório PDF.

    Retorna dict vazio se df estiver vazio.
    """
    if df.empty:
        return {}

    # -- Detecção de colunas disponíveis (backward compat) ------------------
    score_col     = "Score Ranking" if "Score Ranking" in df.columns else "Score Total"
    _tem_empate   = "Empate" in df.columns
    _tem_criterio = "Criterio Desempate" in df.columns
    _tem_classes  = "Classe Quimica" in df.columns

    # -- DataFrames derivados ------------------------------------------------
    rank1_df    = df[df["Rank"] == 1].copy()
    # Um registro por sinal — no caso de empate, o critério e a classe são
    # iguais para todos os candidatos do grupo, então drop_duplicates é seguro.
    rank1_unico = rank1_df.drop_duplicates(subset=["Sinal"]).copy()

    compound_counts = df.groupby("Sinal").size().reset_index(name="n_candidatos")

    rank1_scores = (
        rank1_df.groupby("Sinal")[score_col]
        .first()
        .reset_index()
        .rename(columns={score_col: "pontuacao_rank1"})
    )
    rank1_scores["pontuacao_rank1"] = pd.to_numeric(
        rank1_scores["pontuacao_rank1"], errors="coerce"
    )

    rank1_cand = (
        rank1_unico[["Sinal", "Candidato"]]
        .rename(columns={"Candidato": "melhor_candidato"})
    )

    compound_data = (
        compound_counts
        .merge(rank1_scores, on="Sinal", how="left")
        .merge(rank1_cand,   on="Sinal", how="left")
    )
    compound_data["melhor_candidato_curto"] = compound_data["melhor_candidato"].apply(
        lambda s: (s[:50] + "…") if isinstance(s, str) and len(s) > 50 else s
    )

    # -- Métricas base -------------------------------------------------------
    n_compostos      = len(compound_data)
    n_candidatos_tot = len(df)
    mean_pontuacao   = (
        float(rank1_unico[score_col].mean()) if not rank1_unico.empty else 0.0
    )
    mean_cand_comp = n_candidatos_tot / n_compostos if n_compostos else 0.0
    n_alta_conf    = int(
        (pd.to_numeric(rank1_unico[score_col], errors="coerce") >= SCORE_TIER_ALTA).sum()
    )

    # -- Empates -------------------------------------------------------------
    if _tem_empate and not rank1_unico.empty:
        _emp_num    = pd.to_numeric(rank1_unico["Empate"], errors="coerce").fillna(0)
        n_empates   = int((_emp_num > 0).sum())
        pct_empates = n_empates / n_compostos * 100 if n_compostos else 0.0
        emp_sinais  = frozenset(rank1_unico[_emp_num > 0]["Sinal"].tolist())
    else:
        n_empates   = 0
        pct_empates = 0.0
        emp_sinais  = frozenset()

    # -- Critérios de desempate ----------------------------------------------
    if _tem_criterio and not rank1_unico.empty:
        _crit_raw = (
            rank1_unico["Criterio Desempate"]
            .fillna("desconhecido")
            .value_counts()
            .reset_index()
        )
        _crit_raw.columns = ["criterio", "n"]
        _crit_raw["label"] = (
            _crit_raw["criterio"].map(CRITERIO_LABEL).fillna(_crit_raw["criterio"])
        )
        _crit_raw["cor"] = (
            _crit_raw["criterio"].map(CRITERIO_COLOR).fillna("#cccccc")
        )
        _crit_raw["ordem"] = (
            _crit_raw["criterio"]
            .map({c: i for i, c in enumerate(CRITERIO_ORDER)})
            .fillna(99)
        )
        criterio_counts = _crit_raw.sort_values("ordem").reset_index(drop=True)

        _crit_bio = (
            criterio_counts[~criterio_counts["criterio"].isin(["unico", "empate_humano"])]
            .sort_values("n", ascending=False)
        )
        criterio_dom   = _crit_bio.iloc[0]["criterio"] if not _crit_bio.empty else None
        criterio_dom_n = int(_crit_bio.iloc[0]["n"]) if not _crit_bio.empty else 0
        n_nao_resolvidos = int(
            criterio_counts.loc[criterio_counts["criterio"] == "empate_humano", "n"].sum()
        )
        n_resolvidos = n_compostos - n_nao_resolvidos
    else:
        criterio_counts  = pd.DataFrame()
        criterio_dom     = None
        criterio_dom_n   = 0
        n_resolvidos     = 0
        n_nao_resolvidos = n_empates

    # -- Categorias químicas amigáveis (Rank 1) ---------------------------------
    # Usa "Categoria" se disponível (adicionada por utils.py), senão deriva ao voo.
    _NAO_CLASS = "Não classificado"
    if "Categoria" in rank1_unico.columns:
        _cat_raw = rank1_unico["Categoria"].fillna(_NAO_CLASS)
    elif "Classe Quimica" in rank1_unico.columns:
        _nom_col = rank1_unico["Candidato"] if "Candidato" in rank1_unico.columns else pd.Series([""] * len(rank1_unico))
        _cat_raw = pd.Series([
            classificar_categoria(cq, nm)
            for cq, nm in zip(
                rank1_unico["Classe Quimica"].fillna(""),
                _nom_col.fillna(""),
            )
        ], index=rank1_unico.index)
    else:
        _cat_raw = pd.Series([_NAO_CLASS] * len(rank1_unico))

    _tem_classes = True  # sempre há categoria (com fallback)
    classes_cnt = _cat_raw.value_counts().reset_index()
    classes_cnt.columns = ["Classe química", "Frequência"]
    classes_classif = classes_cnt[classes_cnt["Classe química"] != _NAO_CLASS]
    n_nc      = int(classes_cnt.loc[classes_cnt["Classe química"] == _NAO_CLASS, "Frequência"].sum())
    n_classif = int(classes_classif["Frequência"].sum())

    pct_classif = n_classif / n_compostos * 100 if n_compostos else 0.0

    # -- Insights textuais ---------------------------------------------------
    insights = _gerar_insights(
        mean_pontuacao, mean_cand_comp, n_empates, pct_empates,
        _tem_empate, criterio_dom, criterio_dom_n, n_compostos,
        pct_classif, _tem_classes, classes_classif,
    )

    return {
        # Flags de colunas disponíveis
        "score_col":     score_col,
        "_tem_empate":   _tem_empate,
        "_tem_criterio": _tem_criterio,
        "_tem_classes":  _tem_classes,
        # DataFrames
        "df":            df,
        "rank1_df":      rank1_df,
        "rank1_unico":   rank1_unico,
        "compound_data": compound_data,
        # Métricas escalares
        "n_compostos":      n_compostos,
        "n_candidatos_tot": n_candidatos_tot,
        "mean_pontuacao":   mean_pontuacao,
        "mean_cand_comp":   mean_cand_comp,
        "n_alta_conf":      n_alta_conf,
        "n_empates":        n_empates,
        "pct_empates":      pct_empates,
        "emp_sinais":       emp_sinais,
        # Critérios
        "criterio_counts":  criterio_counts,
        "criterio_dom":     criterio_dom,
        "criterio_dom_n":   criterio_dom_n,
        "n_resolvidos":     n_resolvidos,
        "n_nao_resolvidos": n_nao_resolvidos,
        # Classes químicas
        "classes_cnt":      classes_cnt,
        "classes_classif":  classes_classif,
        "n_nc":             n_nc,
        "n_classif":        n_classif,
        "pct_classif":      pct_classif,
        # Insights textuais (lista de (tipo, texto) com markdown **bold**)
        "insights": insights,
        # Constantes para uso no renderizador
        "CRITERIO_LABEL": CRITERIO_LABEL,
        "CRITERIO_COLOR": CRITERIO_COLOR,
        "CRITERIO_ORDER": CRITERIO_ORDER,
        "SCORE_TIER_ALTA":     SCORE_TIER_ALTA,
        "SCORE_TIER_MODERADA": SCORE_TIER_MODERADA,
    }


def strip_markdown(text: str) -> str:
    """Remove marcadores markdown **bold** para uso em contextos sem renderização."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


# ---------------------------------------------------------------------------
# Geração dos insights textuais (interno)
# ---------------------------------------------------------------------------

def _gerar_insights(
    mean_pontuacao: float,
    mean_cand_comp: float,
    n_empates: int,
    pct_empates: float,
    _tem_empate: bool,
    criterio_dom,
    criterio_dom_n: int,
    n_compostos: int,
    pct_classif: float,
    _tem_classes: bool,
    classes_classif: pd.DataFrame,
) -> list[tuple[str, str]]:
    """Retorna lista de (tipo, texto_markdown) para exibição e relatório."""
    ins: list[tuple[str, str]] = []

    # 1 — Confiança geral
    if mean_pontuacao >= 75:
        ins.append(("success",
            f"**Alta confiança geral:** score médio dos Rank 1 é **{mean_pontuacao:.1f}/100** — "
            "boa correspondência espectral na maioria das identificações."
        ))
    elif mean_pontuacao >= 45:
        ins.append(("info",
            f"**Confiança moderada:** score médio de **{mean_pontuacao:.1f}/100** — "
            "recomenda-se avaliação individual dos compostos com scores mais baixos."
        ))
    else:
        ins.append(("warning",
            f"**Baixa confiança geral:** score médio de **{mean_pontuacao:.1f}/100** — "
            "o experimento apresenta alta ambiguidade e requer revisão detalhada pelo especialista."
        ))

    # 2 — Ambiguidade
    if mean_cand_comp >= 15:
        ins.append(("warning",
            f"**Alta ambiguidade molecular:** média de **{mean_cand_comp:.1f} candidatos por composto** — "
            "muitos sinais possuem diversas identidades compatíveis."
        ))
    elif mean_cand_comp <= 5:
        ins.append(("success",
            f"**Baixa ambiguidade:** média de **{mean_cand_comp:.1f} candidatos por composto** — "
            "a maioria dos sinais possui poucas identidades alternativas."
        ))
    else:
        ins.append(("info",
            f"**Ambiguidade moderada:** média de **{mean_cand_comp:.1f} candidatos por composto**."
        ))

    # 3 — Empates
    if _tem_empate:
        if pct_empates >= 50:
            ins.append(("warning",
                f"**Alta ambiguidade residual:** **{n_empates} de {n_compostos} compostos "
                f"({pct_empates:.0f}%)** com Rank 1 em empate — requerem decisão do especialista."
            ))
        elif pct_empates >= 15:
            ins.append(("info",
                f"**{n_empates} compostos ({pct_empates:.0f}%) em empate no Rank 1** — "
                "a maioria das identificações foi resolvida automaticamente."
            ))
        elif n_empates > 0:
            ins.append(("info",
                f"**{n_empates} composto(s) em empate ({pct_empates:.0f}%)** — "
                "baixa taxa de ambiguidade residual."
            ))
        else:
            ins.append(("success",
                "**Todos os Rank 1 foram resolvidos automaticamente** — "
                "nenhum empate detectado neste experimento."
            ))

    # 4 — Critério dominante
    if criterio_dom and criterio_dom_n > 0:
        _lbl = CRITERIO_LABEL.get(criterio_dom, criterio_dom).lower()
        ins.append(("info",
            f"**A maioria das identificações foi resolvida por {_lbl}:** "
            f"{criterio_dom_n} de {n_compostos} compostos tiveram o Rank 1 "
            "determinado por este critério."
        ))

    # 5 — Cobertura de classificação química
    if n_compostos > 0 and _tem_classes:
        if pct_classif >= 60:
            ins.append(("success",
                f"**{pct_classif:.0f}% dos Rank 1** foram classificados quimicamente "
                "em bases públicas (PubChem / ChEBI)."
            ))
        elif pct_classif >= 25:
            ins.append(("info",
                f"**{pct_classif:.0f}% dos Rank 1** possuem classificação química documentada."
            ))
        else:
            ins.append(("info",
                "**A maioria dos Rank 1 não possui classificação química** — "
                "frequente em compostos emergentes ou de síntese não catalogados."
            ))

    # 6 — Classe predominante
    if not classes_classif.empty and n_compostos > 0:
        _classe = classes_classif.iloc[0]["Classe química"]
        _freq   = int(classes_classif.iloc[0]["Frequência"])
        _pct    = _freq / n_compostos * 100
        ins.append(("info",
            f"**Há predominância de {_classe.lower()}** — "
            f"{_freq} de {n_compostos} compostos ({_pct:.0f}%) são desta classe química."
        ))

    return ins
