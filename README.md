# Omics ETL Pipeline

Sistema de apoio à decisão para identificação de compostos em dados de LC-MS/MS.
Desenvolvido para o IST Ambiental / SENAI no contexto do Projeto Aplicado II.

---

## O que o sistema faz

Recebe planilhas brutas exportadas do equipamento LC-MS/MS (identificação de candidatos moleculares + abundância de sinais), enriquece os dados via APIs externas (PubChem e ChEBI), calcula um score de ranking para cada candidato e persiste tudo com rastreabilidade completa por experimento.

O analista acessa os resultados por uma interface web com ranking interativo, histórico de execuções e upload direto de novos experimentos.

---

## Arquitetura

```
data/raw/
  IDENTIFICACAO.xlsx   ← exportado do software do instrumento
  ABUND.xlsx           ← abundância dos sinais medidos

src/
  pipeline.py          ← orquestrador único (entry point do ETL)
  etl/
    validate.py        ← validação de arquivos + SHA-256 + deduplicação
    extract.py         ← leitura Excel/CSV + merge por Compound
    transform.py       ← enriquecimento via PubChem + ChEBI (com cache)
    load.py            ← scoring + ranking + carga no banco
    job.py             ← data carrier (PipelineJob)
  database/
    schema.py          ← DDL + criação de tabelas e views
    batch.py           ← ciclo de vida de batches (registro, status, listagem)
    migrate.py         ← migrações não-destrutivas v1→v2→v3
    connection.py      ← caminho do banco SQLite
  api/
    pubchem.py         ← fórmula, CID e peso molecular via PUG REST
    chebi.py           ← classe ontológica via ChEBI API
  ui/
    app.py             ← página principal: ranking de candidatos
    pages/
      1_Historico.py   ← histórico de execuções com rastreabilidade
      2_Carregar_Dados.py ← upload de novos experimentos
    utils.py           ← acesso ao banco para a UI

main.py                ← entry point CLI
banco_ist.db           ← banco SQLite (gerado automaticamente)
```

---

## Instalação

**Pré-requisitos:** Python 3.11+ e pip.

```bash
# Clonar o repositório
git clone <url-do-repositorio>
cd omics-etl-pipeline

# Criar ambiente virtual e instalar dependências
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

pip install -r requirements.txt
```

---

## Uso

### Processar um experimento via linha de comando

Coloque os arquivos em `data/raw/` com os nomes padrão e execute:

```bash
python main.py
```

Para usar nomes de arquivo diferentes:

```bash
# Windows PowerShell
$env:OMICS_IDENT_FILE = "MEU_EXPERIMENTO_IDENT.xlsx"
$env:OMICS_ABUND_FILE = "MEU_EXPERIMENTO_ABUND.xlsx"
python main.py
```

Para limitar o número de sinais processados (útil para testes ou datasets grandes):

```bash
$env:OMICS_MAX_COMPOSTOS = "10"   # processa apenas os 10 primeiros sinais
python main.py
```

### Iniciar a interface web

```bash
python -m streamlit run src/ui/app.py
```

Acesse em **http://localhost:8501**.

A interface possui três páginas:
- **Ranking** — visualização dos candidatos moleculares com scores e filtros
- **Histórico** — todos os experimentos processados com status e rastreabilidade
- **Carregar Dados** — upload de novos experimentos diretamente pelo browser

---

## Formato dos arquivos de entrada

### Arquivo de Identificação (`IDENTIFICACAO.xlsx`)

Exportado diretamente do software do equipamento LC-MS/MS.

| Coluna | Obrigatória | Descrição |
|---|---|---|
| `Compound` | Sim | Código único do sinal analítico |
| `Description` | Sim | Nome do candidato molecular |
| `Score` | Não | Score geral do instrumento (0–100) |
| `Fragmentation Score` | Não | Score de fragmentação MS/MS (0–100) |
| `Isotope Similarity` | Não | Similaridade isotópica (0–100) |
| `Mass Error (ppm)` | Não | Erro de massa em ppm |
| `Neutral mass (Da)` | Não | Massa neutra do candidato |
| `Adducts` | Não | Tipo de aducto detectado |

### Arquivo de Abundância (`ABUND.xlsx`)

| Coluna | Obrigatória | Descrição |
|---|---|---|
| `Compound` | Sim | Código do sinal — deve ser idêntico ao arquivo de Identificação |
| `m/z` | Sim | Razão massa/carga medida |

Os arquivos são cruzados pela coluna `Compound`. Ambos devem pertencer ao mesmo experimento.

---

## Score Ranking

O pipeline calcula dois scores independentes para cada candidato:

### Score Ranking (0–100) — determina o rank

Média ponderada linear dos scores de identificação:

| Componente | Peso | Fonte |
|---|---|---|
| Fragmentação MS/MS | **40%** | Instrumento (`Fragmentation Score`) |
| Score Lab | **30%** | Instrumento (`Score`) |
| Similaridade Isotópica | **20%** | Instrumento (`Isotope Similarity`) |
| Erro de Massa (ppm) | **10%** | Calculado pelo pipeline |

Componentes nulos são excluídos e os pesos restantes são renormalizados automaticamente.
**Os pesos são provisórios e devem ser calibrados com o IST.**

Referências: Schymanski et al. (2014) *Environ. Sci. Technol.* 48(4):2097–2098.

### Score Qualidade Dados (0–100%) — não entra no ranking

Percentual de metadados externos preenchidos (fórmula, CID PubChem, peso molecular, ChEBI ID, classe química). Indica a completude do enriquecimento via API para aquela molécula.

---

## Deduplicação

O pipeline calcula o SHA-256 dos dois arquivos de entrada antes de processar. Se o par de arquivos já foi processado com sucesso anteriormente, o pipeline é interrompido e o batch original é indicado. Qualquer diferença nos arquivos (mesmo um único byte) gera um novo batch.

---

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `OMICS_IDENT_FILE` | `IDENTIFICACAO.xlsx` | Nome do arquivo de identificação em `data/raw/` |
| `OMICS_ABUND_FILE` | `ABUND.xlsx` | Nome do arquivo de abundância em `data/raw/` |
| `OMICS_MAX_COMPOSTOS` | *(sem limite)* | Limita o número de sinais únicos processados |

---

## Banco de dados

O banco `banco_ist.db` (SQLite) é criado automaticamente na raiz do projeto na primeira execução.

**Tabelas principais:**

| Tabela | Descrição |
|---|---|
| `batch_execucao` | Registro de cada execução com status, timestamps e estatísticas |
| `fact_sinal` | Sinais analíticos brutos, scoped por batch |
| `dim_molecula` | Cache global de moléculas — cada molécula é consultada uma única vez nas APIs |
| `candidato_sinal` | Relação N:N entre sinais e candidatos com todos os scores |

**Views:**

| View | Descrição |
|---|---|
| `vw_ranking_candidatos` | Ranking do batch mais recente com sucesso |
| `vw_ranking_historico` | Ranking de todos os batches com sucesso |

O banco evolui automaticamente via migrações não-destrutivas. Dados históricos são preservados em todas as versões.

---

## Limitações conhecidas

- Os pesos do Score Ranking são provisórios — precisam de calibração com o IST
- Processamento síncrono: a interface web fica bloqueada durante o pipeline (esperado para o volume atual)
- Sem retry automático em falhas de API — campos ficam nulos e são reprocessados na próxima execução
- Datasets grandes (>500 sinais) requerem `OMICS_MAX_COMPOSTOS` para execução viável em tempo razoável
- Sem autenticação na interface web — adequado para uso interno em rede local

---

## Estrutura do projeto

```
omics-etl-pipeline/
├── data/
│   └── raw/                  ← arquivos de entrada (não versionados)
├── src/
│   ├── api/                  ← clientes das APIs externas
│   ├── database/             ← schema, migrações e acesso ao banco
│   ├── etl/                  ← Extract, Transform, Load
│   └── ui/                   ← interface Streamlit
├── main.py                   ← entry point CLI
├── requirements.txt
└── banco_ist.db              ← gerado automaticamente (não versionado)
```

---

## Desenvolvimento

Projeto desenvolvido por **Felipe Padilha** como parte do Projeto Aplicado II — Curso de Ciência de Dados, em parceria com o **IST Ambiental / SENAI**.
