"""
Camada de interpretação do sistema — Omics ETL Pipeline.

Transforma o dict numérico de computar_insights() em estruturas de decisão
independentes de renderer (Streamlit, PDF, XLSX, exportações futuras).

Regra de dependências (unidirecional):
  narrative.py → stdlib · pandas · src.reports.insights
  NÃO importa: reportlab · streamlit · matplotlib · _shared · charts
"""
from __future__ import annotations

import pandas as pd
from typing import TypedDict

from src.reports.insights import (
    CRITERIO_LABEL,
    SCORE_TIER_ALTA,
    SCORE_TIER_MODERADA,
)

# ---------------------------------------------------------------------------
# Tipo de retorno público
# ---------------------------------------------------------------------------

class NarrativaDict(TypedDict):
    # — Status global
    status:          str            # "conclusivo" | "parcial" | "inconclusivo"
    status_label:    str            # rótulo PT-BR sem emoji, renderer-agnostic
    status_cor:      str            # "verde" | "amarelo" | "vermelho"
    # — Contagens de ação
    n_criticos:      int            # compostos em empate Rank 1
    n_atencao:       int            # compostos score < SCORE_TIER_MODERADA, sem empate
    n_revisar:       int            # n_criticos + n_atencao
    # — Risco analítico
    risco_label:     str            # "Baixo" | "Moderado" | "Elevado"
    risco_desc:      str            # frase de descrição
    # — Texto técnico — RA + Streamlit (aceita **bold** markdown)
    paragrafo:       str
    conclusao:       str
    # — Texto executivo — RE (plain text, sem jargão técnico)
    paragrafo_exec:  str
    recomendacao:    str            # frase imperativa de ação
    # — Tabela diagnóstica — RA + RE
    dimensoes:       list           # [(nome_dim, valor_str, interpretacao_str), ...]
    # — Tabela de prioridades — Streamlit + RA + RE
    priority_df:     pd.DataFrame   # cols: Prioridade/Composto/Confiança/Categoria/Situação/Candidato mais provável


# ---------------------------------------------------------------------------
# Constantes de mapeamento (renderer-agnostic)
# ---------------------------------------------------------------------------

_STATUS_LABEL: dict[str, str] = {
    "conclusivo":   "Análise Conclusiva",
    "parcial":      "Análise Parcialmente Conclusiva",
    "inconclusivo": "Análise Inconclusiva",
}

_STATUS_COR: dict[str, str] = {
    "conclusivo":   "verde",
    "parcial":      "amarelo",
    "inconclusivo": "vermelho",
}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def gerar_narrativa(ins: dict, cobertura_ext: dict | None = None) -> NarrativaDict:
    """
    Ponto de entrada único da camada de interpretação.

    ins           — saída de computar_insights(df)
    cobertura_ext — saída de carregar_cobertura_externa(); pode ser None ou {}

    Determinístico: mesma entrada → mesma saída sempre.
    Sem I/O, sem randomness, sem efeitos colaterais.
    """
    cob = cobertura_ext or {}

    mean_p  = float(ins.get("mean_pontuacao", 0))
    pct_emp = float(ins.get("pct_empates", 0))
    pct_ch  = float(cob.get("pct_chebi", 0))

    status            = _calcular_status(mean_p, pct_emp, pct_ch)
    risco_l, risco_d  = _calcular_risco(mean_p, pct_emp)
    n_crit, n_at, n_rev = _contar_acoes(ins)

    return NarrativaDict(
        status         = status,
        status_label   = _STATUS_LABEL[status],
        status_cor     = _STATUS_COR[status],
        n_criticos     = n_crit,
        n_atencao      = n_at,
        n_revisar      = n_rev,
        risco_label    = risco_l,
        risco_desc     = risco_d,
        paragrafo      = _gerar_paragrafo(ins, cob),
        conclusao      = _gerar_conclusao(
                             status, n_crit, n_at,
                             ins.get("n_compostos", 0),
                             ins.get("n_alta_conf", 0),
                         ),
        paragrafo_exec = _gerar_paragrafo_exec(ins, cob, n_crit, n_at),
        recomendacao   = _gerar_recomendacao(status, n_crit, n_at, ins.get("n_compostos", 0)),
        dimensoes      = _gerar_dimensoes(ins, cob),
        priority_df    = _build_priority_table(ins),
    )


# ---------------------------------------------------------------------------
# Funções privadas — status e risco
# ---------------------------------------------------------------------------

def _calcular_status(mean_p: float, pct_emp: float, pct_ch: float) -> str:
    if mean_p < SCORE_TIER_MODERADA or pct_emp > 40:
        return "inconclusivo"
    if mean_p >= 70 and pct_emp <= 15 and pct_ch >= 50:
        return "conclusivo"
    return "parcial"


def _calcular_risco(mean_p: float, pct_emp: float) -> tuple[str, str]:
    if mean_p < SCORE_TIER_MODERADA or pct_emp > 40:
        return (
            "Elevado",
            "Score médio abaixo de 45 ou mais de 40% dos compostos em empate.",
        )
    if mean_p >= 70 and pct_emp <= 15:
        return ("Baixo", "Boa confiança geral com poucos empates.")
    return ("Moderado", "Confiança ou proporção de empates em nível intermediário.")


def _contar_acoes(ins: dict) -> tuple[int, int, int]:
    """Retorna (n_criticos, n_atencao, n_revisar)."""
    emp_sinais    = ins.get("emp_sinais", frozenset())
    compound_data = ins.get("compound_data", pd.DataFrame())

    if compound_data.empty:
        return 0, 0, 0

    scores = (
        compound_data.set_index("Sinal")["pontuacao_rank1"]
        .apply(lambda x: pd.to_numeric(x, errors="coerce"))
    )
    low_sinais = set(scores[scores < SCORE_TIER_MODERADA].index.tolist()) - set(emp_sinais)

    n_criticos = len(emp_sinais)
    n_atencao  = len(low_sinais)
    return n_criticos, n_atencao, n_criticos + n_atencao


# ---------------------------------------------------------------------------
# Funções privadas — texto técnico (RA + Streamlit)
# ---------------------------------------------------------------------------

def _gerar_paragrafo(ins: dict, cob: dict) -> str:
    """Texto técnico com **bold** markdown — RA e Streamlit."""
    n       = ins.get("n_compostos", 0)
    score   = ins.get("mean_pontuacao", 0.0)
    n_emp   = ins.get("n_empates", 0)
    pct_emp = ins.get("pct_empates", 0.0)
    c_dom   = ins.get("criterio_dom")
    c_dom_n = ins.get("criterio_dom_n", 0)
    cl      = ins.get("classes_classif", pd.DataFrame())
    pct_ch  = cob.get("pct_chebi", 0)

    conf = (
        f"boa confiança ({score:.1f}/100)"           if score >= 70
        else f"confiança moderada ({score:.1f}/100)" if score >= SCORE_TIER_MODERADA
        else f"baixa confiança ({score:.1f}/100)"
    )

    partes = [f"Este experimento identificou **{n} compostos** com {conf}."]

    if c_dom and c_dom_n > 0:
        lbl = CRITERIO_LABEL.get(c_dom, c_dom).lower()
        partes.append(
            f"O critério de {lbl} foi determinante em {c_dom_n} identificações, "
            "indicando qualidade espectral aceitável."
        )

    if ins.get("_tem_empate", False):
        if n_emp == 0:
            partes.append("Todos os compostos foram identificados automaticamente, sem empates.")
        elif n_emp == 1:
            partes.append(
                "**1 composto** não pôde ser identificado automaticamente "
                "e requer avaliação do especialista."
            )
        else:
            partes.append(
                f"**{n_emp} compostos ({pct_emp:.0f}%)** não puderam ser identificados "
                "automaticamente e requerem avaliação do especialista."
            )

    if not cl.empty:
        cls = cl.iloc[0]["Classe química"]
        frq = int(cl.iloc[0]["Frequência"])
        if cls != "Não classificado":
            partes.append(
                f"O perfil químico é dominado por **{cls.lower()}** ({frq} de {n} compostos)."
            )

    if pct_ch > 0:
        if pct_ch >= 70:
            partes.append(f"Cobertura de bases externas boa (ChEBI {pct_ch:.0f}%).")
        elif pct_ch >= 40:
            partes.append(
                f"Cobertura de bases externas parcial (ChEBI {pct_ch:.0f}%), "
                "esperada para amostras com compostos emergentes."
            )
        else:
            partes.append(
                f"Cobertura de bases externas limitada (ChEBI {pct_ch:.0f}%) — "
                "muitos compostos não estão catalogados em bases públicas."
            )

    return " ".join(partes)


def _gerar_conclusao(
    status: str,
    n_criticos: int,
    n_atencao: int,
    n_compostos: int,
    n_alta_conf: int,
) -> str:
    if status == "conclusivo":
        return (
            f"Resultado conclusivo. {n_alta_conf} de {n_compostos} compostos "
            "com alta confiança de identificação."
        )
    if status == "inconclusivo":
        return (
            "Resultado inconclusivo. Revisão detalhada pelo especialista "
            "recomendada antes de reportar qualquer identificação."
        )
    partes = ["Resultado aceitável."]
    if n_criticos > 0:
        s = "s" if n_criticos > 1 else ""
        partes.append(f"Revisão manual necessária em {n_criticos} composto{s} em empate.")
    if n_atencao > 0:
        s = "s" if n_atencao > 1 else ""
        partes.append(f"{n_atencao} composto{s} com baixa confiança requerem atenção.")
    return " ".join(partes)


# ---------------------------------------------------------------------------
# Funções privadas — texto executivo (RE)
# ---------------------------------------------------------------------------

def _gerar_paragrafo_exec(ins: dict, cob: dict, n_criticos: int, n_atencao: int) -> str:
    """Plain text sem jargão técnico — RE."""
    n      = ins.get("n_compostos", 0)
    score  = ins.get("mean_pontuacao", 0.0)
    n_rev  = n_criticos + n_atencao

    if score >= 70:
        f1 = (
            f"Foram identificados {n} compostos na amostra com "
            "alta correspondência às bases de dados científicas."
        )
    elif score >= SCORE_TIER_MODERADA:
        f1 = (
            f"Foram identificados {n} compostos na amostra. "
            "A maioria das identificações apresenta correspondência adequada "
            "às bases de dados científicas."
        )
    else:
        f1 = (
            f"Foram identificados {n} compostos na amostra. "
            "A qualidade geral das identificações está abaixo do esperado "
            "e requer revisão detalhada."
        )

    if n_rev == 0:
        f2 = f"Todas as {n} identificações foram concluídas automaticamente pelo sistema."
    elif n_rev == 1:
        f2 = "1 composto requer avaliação adicional pelo especialista analítico."
    else:
        f2 = (
            f"{n_rev} compostos requerem avaliação adicional pelo especialista analítico "
            f"({n_criticos} com identidade incerta, {n_atencao} com baixa correspondência)."
        )

    n_ok = n - n_rev
    if n_rev == 0:
        f3 = "O experimento está disponível para consolidação de resultados."
    elif n_ok > 0:
        f3 = f"Os {n_ok} compostos restantes estão disponíveis para consolidação de resultados."
    else:
        f3 = "Recomenda-se aguardar validação antes de consolidar os resultados."

    return " ".join([f1, f2, f3])


def _gerar_recomendacao(
    status: str,
    n_criticos: int,
    n_atencao: int,
    n_compostos: int,
) -> str:
    """Frase imperativa de ação — exclusiva do RE."""
    if status == "conclusivo":
        return "Experimento aprovado. Resultados disponíveis para relatório de resultados."
    if status == "inconclusivo":
        return (
            "Aguardar validação do especialista analítico "
            "antes de divulgar os resultados."
        )

    acoes: list[str] = []
    if n_criticos > 0:
        s = "s" if n_criticos > 1 else ""
        acoes.append(f"revisar {n_criticos} composto{s} com identidade incerta")
    if n_atencao > 0:
        s = "s" if n_atencao > 1 else ""
        acoes.append(f"avaliar {n_atencao} composto{s} com baixa correspondência")

    if not acoes:
        return "Experimento aprovado. Resultados disponíveis para relatório de resultados."

    n_ok     = n_compostos - n_criticos - n_atencao
    acao_str = " e ".join(acoes)
    sfx      = f" Os {n_ok} compostos restantes estão aprovados." if n_ok > 0 else ""
    return f"Ação recomendada: {acao_str}.{sfx}"


# ---------------------------------------------------------------------------
# Funções privadas — tabela diagnóstica (RA + RE)
# ---------------------------------------------------------------------------

def _gerar_dimensoes(ins: dict, cob: dict) -> list[tuple[str, str, str]]:
    """Lista de (dimensão, valor_str, interpretação) para tabela diagnóstica."""
    dims: list[tuple[str, str, str]] = []

    n_comp  = ins.get("n_compostos", 0)
    score   = ins.get("mean_pontuacao", 0.0)
    n_emp   = ins.get("n_empates", 0)
    pct_emp = ins.get("pct_empates", 0.0)
    n_nao   = ins.get("n_nao_resolvidos", n_emp)
    n_resol = ins.get("n_resolvidos", n_comp - n_nao)
    cl      = ins.get("classes_classif", pd.DataFrame())

    # 1. Confiança geral
    if score >= 70:
        sc_interp = "Alta"
    elif score >= SCORE_TIER_MODERADA:
        sc_interp = "Moderada — avaliação individual recomendada"
    else:
        sc_interp = "Baixa — revisão detalhada necessária"
    dims.append(("Confiança geral", f"{score:.1f} / 100", sc_interp))

    # 2. Empates Rank 1
    if n_emp == 0:
        emp_interp = "Nenhum — todas as identificações resolvidas automaticamente"
    elif pct_emp <= 15:
        emp_interp = f"{n_emp} requerem decisão do especialista"
    else:
        emp_interp = f"Taxa elevada — {n_emp} compostos com ambiguidade irresolvível"
    dims.append(("Empates Rank 1", f"{n_emp} de {n_comp} ({pct_emp:.0f}%)", emp_interp))

    # 3. Resolução automática
    pct_resol = n_resol / n_comp * 100 if n_comp else 0
    if pct_resol >= 90:
        resol_interp = "Alta — sistema resolveu bem"
    elif pct_resol >= 70:
        resol_interp = "Moderada"
    else:
        resol_interp = "Baixa — muitos compostos precisam de intervenção manual"
    dims.append(
        ("Resolução automática", f"{n_resol} de {n_comp} ({pct_resol:.0f}%)", resol_interp)
    )

    # 4. Perfil químico dominante
    if not cl.empty:
        cls_dom  = cl.iloc[0]["Classe química"]
        freq_dom = int(cl.iloc[0]["Frequência"])
        pct_dom  = freq_dom / n_comp * 100 if n_comp else 0
        dims.append((
            "Perfil químico dominante",
            f"{cls_dom} ({freq_dom} — {pct_dom:.0f}%)",
            "Categoria mais frequente nos Rank 1",
        ))

    # 5. Cobertura ChEBI
    pct_chebi = cob.get("pct_chebi", 0)
    if pct_chebi > 0:
        if pct_chebi >= 70:
            cov_interp = "Bem documentado"
        elif pct_chebi >= 40:
            cov_interp = "Parcial — esperado para compostos emergentes"
        else:
            cov_interp = "Limitada — muitos compostos não catalogados"
        dims.append(("Cobertura ChEBI", f"{pct_chebi:.0f}%", cov_interp))

    # 6. Cobertura PubChem
    pct_pubchem = cob.get("pct_pubchem", 0)
    if pct_pubchem > 0:
        dims.append((
            "Cobertura PubChem",
            f"{pct_pubchem:.0f}%",
            "Compostos Rank 1 com CID público",
        ))

    return dims


# ---------------------------------------------------------------------------
# Funções privadas — tabela de prioridades
# ---------------------------------------------------------------------------

def _build_priority_table(ins: dict) -> pd.DataFrame:
    """
    DataFrame de compostos ordenado por prioridade de revisão.
    Usa ins["emp_sinais"] exposto por computar_insights() — sem recálculo.
    """
    compound_data = ins.get("compound_data", pd.DataFrame())
    rank1_unico   = ins.get("rank1_unico",   pd.DataFrame())
    rank1_df      = ins.get("rank1_df",      pd.DataFrame())
    emp_sinais    = ins.get("emp_sinais",     frozenset())

    if compound_data.empty:
        return pd.DataFrame(columns=[
            "Prioridade", "Composto", "Confiança",
            "Situação", "Candidato mais provável",
        ])

    _extra_cols = ["Sinal"]
    for col in ["Empate", "Categoria"]:
        if col in rank1_unico.columns:
            _extra_cols.append(col)
    extra  = rank1_unico[_extra_cols].drop_duplicates("Sinal").reset_index(drop=True)
    n_tied = rank1_df.groupby("Sinal").size().to_dict() if not rank1_df.empty else {}

    tbl = (
        compound_data[["Sinal", "pontuacao_rank1", "melhor_candidato_curto"]]
        .merge(extra, on="Sinal", how="left")
        .copy()
    )

    prioridade_col: list = []
    ordem_col: list      = []
    situacao_col: list   = []

    for _, row in tbl.iterrows():
        sinal = row["Sinal"]
        score = pd.to_numeric(row.get("pontuacao_rank1"), errors="coerce")
        score = float(score) if pd.notna(score) else 100.0

        if sinal in emp_sinais:
            n_t = n_tied.get(sinal, 2)
            prioridade_col.append("🔴 Alta")
            ordem_col.append(3)
            situacao_col.append(f"Empate — {n_t} candidatos")
        elif score < SCORE_TIER_MODERADA:
            prioridade_col.append("🟡 Média")
            ordem_col.append(2)
            situacao_col.append("Baixa confiança")
        elif score >= SCORE_TIER_ALTA:
            prioridade_col.append("✅ OK")
            ordem_col.append(0)
            situacao_col.append("Alta confiança")
        else:
            prioridade_col.append("—")
            ordem_col.append(1)
            situacao_col.append("Confiança moderada")

    tbl["Prioridade"] = prioridade_col
    tbl["_ordem"]     = ordem_col
    tbl["Situação"]   = situacao_col
    tbl["Confiança"]  = pd.to_numeric(tbl["pontuacao_rank1"], errors="coerce").round(1)

    tbl = tbl.sort_values(["_ordem", "pontuacao_rank1"], ascending=[False, True])

    out_cols   = ["Prioridade", "Sinal", "Confiança"]
    col_rename = {"Sinal": "Composto"}

    if "Categoria" in tbl.columns:
        out_cols.append("Categoria")

    out_cols += ["Situação", "melhor_candidato_curto"]
    col_rename["melhor_candidato_curto"] = "Candidato mais provável"

    return (
        tbl[out_cols]
        .rename(columns=col_rename)
        .reset_index(drop=True)
    )
