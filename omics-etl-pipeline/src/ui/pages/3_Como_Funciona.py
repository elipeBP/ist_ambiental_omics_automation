"""
Página: Como Funciona
Guia de interpretação dos resultados para novos usuários.
"""
import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

st.set_page_config(
    page_title="Como Funciona | Omics ETL",
    page_icon="📖",
    layout="wide",
)

st.title("📖 Como Funciona")
st.caption("Guia de interpretação dos resultados | IST Ambiental / SENAI")
st.divider()

# ---------------------------------------------------------------------------
# Seção 1 — O fluxo completo
# ---------------------------------------------------------------------------
st.subheader("O fluxo completo")
st.write(
    "Este sistema recebe as planilhas exportadas pelo instrumento LC-MS/MS e organiza os "
    "candidatos moleculares por plausibilidade de identificação. "
    "O objetivo é auxiliar o especialista a decidir qual é a identidade mais provável "
    "de cada composto detectado na amostra."
)

c1, c2, c3 = st.columns(3)

with c1:
    with st.container(border=True):
        st.markdown("### 🔬 Instrumento LC-MS/MS")
        st.markdown(
            "Analisa a amostra e registra **sinais** para cada composto detectado. "
            "Para cada sinal, o software do equipamento compara com uma biblioteca espectral "
            "e sugere uma lista de **candidatos moleculares** compatíveis."
        )
        st.caption("*Gera: planilha de identificação + planilha de abundâncias*")

with c2:
    with st.container(border=True):
        st.markdown("### 🖥️ Este sistema")
        st.markdown(
            "Recebe as planilhas, organiza os candidatos por **pontuação de identificação** "
            "e busca informações adicionais sobre cada molécula em bases de dados "
            "científicas públicas (PubChem, ChEBI)."
        )
        st.caption("*Gera: ranking de candidatos por composto detectado*")

with c3:
    with st.container(border=True):
        st.markdown("### 🧪 Especialista analítico")
        st.markdown(
            "Avalia os resultados considerando o **contexto químico da amostra**: "
            "quais classes de compostos são esperadas? O Rank 1 faz sentido para esta matriz? "
            "A identificação definitiva sempre depende do julgamento especializado."
        )
        st.caption("*Decide: qual identificação reportar*")

st.divider()

# ---------------------------------------------------------------------------
# Seção 2 — Composto detectado (sinal analítico)
# ---------------------------------------------------------------------------
st.subheader("O que é um composto detectado?")

col_a, col_b = st.columns([3, 2])

with col_a:
    st.markdown(
        """
        Quando o instrumento LC-MS/MS analisa uma amostra, ele registra **sinais elétricos**
        correspondentes a compostos presentes. Cada sinal é descrito por dois parâmetros:

        - **Tempo de retenção (RT):** instante em minutos em que o composto saiu da coluna cromatográfica
        - **Razão massa/carga (m/z):** propriedade elétrica da molécula ionizada, relacionada à sua massa

        Esses dois números juntos formam o **código do composto** que você vê no sistema.
        """
    )

with col_b:
    with st.container(border=True):
        st.markdown("**Exemplo de código:**")
        st.code("10.90_592.2617n")
        st.caption(
            "**10.90** = detectado aos 10,9 min  \n"
            "**592.2617** = m/z medido  \n"
            "**n** = modo de ionização negativo"
        )

st.info(
    "💡 Um único composto detectado pode corresponder a **dezenas de candidatos moleculares** "
    "diferentes — especialmente quando existem **isômeros** (moléculas com a mesma fórmula "
    "mas estruturas distintas). O sistema organiza esses candidatos para facilitar a decisão."
)

st.divider()

# ---------------------------------------------------------------------------
# Seção 3 — Candidato molecular
# ---------------------------------------------------------------------------
st.subheader("O que é um candidato molecular?")

st.markdown(
    """
    Para cada sinal detectado, o software do instrumento compara as características espectrais
    com uma **biblioteca de compostos conhecidos** e gera uma lista de moléculas compatíveis —
    os **candidatos moleculares**.

    Cada candidato é uma molécula cuja estrutura química é **consistente com o sinal medido**,
    considerando sua massa, seus padrões de fragmentação e seus isótopos.

    O sistema lista todos os candidatos e os ordena do mais ao menos provável — mas a
    compatibilidade espectral não garante a identidade: dois isômeros podem ter pontuações
    muito próximas, e apenas o contexto da amostra permite decidir.
    """
)

col_x, col_y = st.columns(2)
with col_x:
    with st.container(border=True):
        st.markdown("**Candidato com alta pontuação:**")
        st.markdown("✅ Padrão de fragmentação compatível  \n✅ Padrão isotópico consistente  \n✅ Erro de massa próximo de zero")
        st.caption("→ Provavelmente é este composto — mas precisa de validação")

with col_y:
    with st.container(border=True):
        st.markdown("**Candidato com baixa pontuação:**")
        st.markdown("⚠️ Fragmentação parcialmente compatível  \n⚠️ Padrão isotópico divergente  \n⚠️ Erro de massa elevado")
        st.caption("→ Menos provável — pode ser descartado após análise")

st.divider()

# ---------------------------------------------------------------------------
# Seção 4 — Como funciona o ranking
# ---------------------------------------------------------------------------
st.subheader("Como o ranking é calculado?")

st.markdown(
    """
    O **Rank** ordena os candidatos de um mesmo composto do mais ao menos provável.
    **Rank 1** = candidato com maior pontuação de identificação para aquele sinal.

    A **pontuação de identificação** (0–100) é calculada a partir de critérios gerados
    pelo instrumento LC-MS/MS:
    """
)

r1, r2, r3 = st.columns(3)

with r1:
    with st.container(border=True):
        st.markdown("**Correspondência MS/MS**")
        st.markdown("Grau de coincidência entre os fragmentos detectados e o padrão esperado para a molécula.")
        st.caption("Critério mais discriminativo — especialmente para isômeros")

with r2:
    with st.container(border=True):
        st.markdown("**Padrão isotópico**")
        st.markdown("Semelhança entre a distribuição de isótopos medida e a prevista pela fórmula molecular.")
        st.caption("Valida a composição elementar do candidato")

with r3:
    with st.container(border=True):
        st.markdown("**Erro de massa (ppm)**")
        st.markdown("Diferença entre a massa medida e a massa teórica do candidato, em partes por milhão.")
        st.caption("≤ 5 ppm = excelente. ≥ 20 ppm = incompatível")

st.warning(
    "⚠️ **O ranking é um ponto de partida, não uma resposta definitiva.** "
    "A pontuação mais alta indica compatibilidade espectral — "
    "a identificação final requer avaliação do contexto químico da amostra pelo especialista."
)

st.divider()

# ---------------------------------------------------------------------------
# Seção 5 — Os indicadores em detalhe
# ---------------------------------------------------------------------------
st.subheader("O que significa cada indicador?")

with st.expander("Pontuação de identificação (0–100)", expanded=True):
    st.markdown(
        """
        Score calculado a partir dos dados do instrumento. Candidatos com pontuação mais alta
        correspondem melhor ao sinal medido. É a base do ranking.

        - **> 80:** correspondência muito boa — candidato altamente provável
        - **50–80:** correspondência moderada — requer avaliação adicional
        - **< 50:** correspondência fraca — candidato improvável, mas não descartado automaticamente
        """
    )

with st.expander("Score do instrumento (Score Lab)"):
    st.markdown(
        """
        Pontuação geral calculada internamente pelo software do equipamento LC-MS/MS.
        Integra múltiplos critérios de identificação de acordo com os parâmetros do fabricante.
        É o critério principal do ranking.
        """
    )

with st.expander("Correspondência MS/MS (Fragmentação)"):
    st.markdown(
        """
        Avalia o quão bem os fragmentos detectados — gerados pela quebra da molécula no
        espectrômetro — coincidem com o padrão esperado para o candidato.
        É especialmente importante para distinguir **isômeros estruturais** que têm a
        mesma fórmula mas padrões de fragmentação diferentes.
        """
    )

with st.expander("Padrão isotópico (Isotope Similarity)"):
    st.markdown(
        """
        Toda molécula tem uma distribuição característica de isótopos (versões do elemento
        com massas ligeiramente diferentes). Este indicador compara a distribuição medida
        pelo instrumento com a prevista pela fórmula molecular do candidato.
        Valores altos (> 80) indicam boa consistência elementar.
        """
    )

with st.expander("Erro de massa (ppm)"):
    st.markdown(
        """
        Diferença entre a massa medida pelo instrumento e a massa teórica calculada
        para a fórmula molecular do candidato. Expresso em **partes por milhão (ppm)**.

        Instrumentos modernos de alta resolução (Q-TOF, Orbitrap) operam tipicamente
        abaixo de 5 ppm. Valores acima de 20 ppm geralmente indicam incompatibilidade.

        - **≤ 5 ppm:** excelente — pontuação máxima
        - **5–20 ppm:** aceitável — pontuação reduzida proporcionalmente
        - **> 20 ppm:** incompatível — pontuação zero neste critério
        """
    )

with st.expander("Forma iônica detectada (Adducts)"):
    st.markdown(
        """
        Durante a ionização, moléculas podem ganhar ou perder átomos, formando diferentes
        **adducts** (formas iônicas). O m/z medido pelo instrumento corresponde ao adduct,
        não à molécula neutra diretamente.

        Exemplos comuns:
        - **M-H:** molécula perdeu um próton (modo negativo)
        - **M+H:** molécula ganhou um próton (modo positivo)
        - **M+Na:** molécula ganhou um átomo de sódio

        O sistema desconta o efeito do adduct para calcular a **massa molecular** do candidato.
        """
    )

with st.expander("Dados externos disponíveis (Score Qualidade Dados)"):
    st.markdown(
        """
        Indica quantas informações sobre o candidato foram encontradas em bases de dados
        públicas como **PubChem** e **ChEBI** — fórmula molecular, peso teórico, classe
        química, identificadores externos.

        **Este indicador não afeta o ranking.** É útil para avaliar quão bem documentada
        é a molécula na literatura científica.

        Um valor baixo pode significar que é um composto pouco estudado — não necessariamente
        que a identificação está errada.
        """
    )

st.divider()

# ---------------------------------------------------------------------------
# Seção 6 — Como usar os resultados
# ---------------------------------------------------------------------------
st.subheader("Como usar os resultados na prática?")

st.markdown(
    """
    **Fluxo de trabalho sugerido:**

    1. **Acesse a página principal** (🧬 Identificação de Compostos) para ver os resultados
       da análise mais recente.

    2. **Verifique as métricas de resumo** no topo: quantos compostos foram detectados,
       quantos candidatos foram gerados e qual é a confiança média dos primeiros colocados.

    3. **Use o filtro lateral** para explorar um composto específico e ver todos os seus
       candidatos com os detalhes da identificação.

    4. **Avalie o Rank 1** considerando:
       - A pontuação de identificação (quanto maior, mais compatível)
       - Os scores individuais (fragmentação, isotópico, massa)
       - A plausibilidade química no contexto da amostra

    5. **Consulte o histórico** (📋 Histórico de Análises) para comparar resultados
       entre diferentes experimentos.
    """
)

with st.container(border=True):
    st.markdown("#### Limitações importantes")
    st.markdown(
        """
        - O **Rank 1 não é uma certeza** — é o candidato mais compatível com os dados espectrais.
        - **Isômeros** com estruturas muito parecidas podem ter pontuações próximas,
          tornando difícil a distinção automática.
        - A **plausibilidade biológica ou ambiental** do composto (faz sentido estar nessa amostra?)
          não é avaliada automaticamente — requer conhecimento do especialista sobre a matriz.
        - Compostos sem registro em PubChem/ChEBI terão **dados externos incompletos**,
          mas isso não invalida a identificação.
        """
    )

st.divider()
st.caption("Omics ETL Pipeline · IST Ambiental / SENAI")
