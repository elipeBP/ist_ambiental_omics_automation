# Omics ETL Pipeline

Pipeline de ETL para triagem molecular: recebe planilhas de laboratório (identificação + abundância), valida e deduplica os lotes, enriquece cada composto com dados de bancos biológicos externos (ChEBI, HMDB, PubChem, UniProt) e carrega tudo num banco de dados — com relatórios em PDF/Excel e um dashboard em Streamlit no final.

Projeto Integrador (Projeto Aplicado II) do curso de Ciência de Dados e Inteligência Artificial — UniSENAI/SC.

## O que o pipeline faz

1. **Validação** — confere os arquivos de entrada (`IDENTIFICACAO.xlsx`, `ABUND.xlsx`), descarta lotes duplicados por hash e limpa lotes "zumbis" (travados de execuções anteriores).
2. **Extract → Transform → Load** — extrai os dados brutos, enriquece cada composto consultando ChEBI, HMDB, PubChem e UniProt, e carrega o resultado no banco.
3. **Relatórios** — gera relatório executivo e analítico em PDF, export em Excel, gráficos e insights narrativos automáticos.
4. **Dashboard** — interface Streamlit para upload de novos lotes e visualização dos resultados.

O mesmo orquestrador (`src/pipeline.py`) é chamado tanto pela CLI (`main.py`) quanto pela UI de upload — nenhuma das duas conhece os detalhes internos do ETL.

## Stack

- **Dados:** pandas, openpyxl
- **Enriquecimento:** requests (ChEBI, HMDB, PubChem, UniProt)
- **Relatórios:** reportlab, matplotlib, altair
- **Dashboard:** Streamlit
- **Empacotamento:** PyInstaller

## Dashboard

![Dashboard](imagens_dashbord/Captura%20de%20tela%202026-05-11%20212849.png)

## Estrutura

```
omics-etl-pipeline/
  main.py            # entry point CLI
  src/
    etl/              # extract, transform, load, validate, job
    api/              # clientes ChEBI, HMDB, PubChem, UniProt
    database/         # schema, migrations, controle de batch
    reports/          # PDF executivo/analítico, Excel, gráficos, narrativa
    ui/               # dashboard Streamlit
```

## Como rodar

```bash
cd omics-etl-pipeline
pip install -r requirements.txt

# via CLI
python main.py

# via dashboard
streamlit run src/ui/app.py
```

Coloque `IDENTIFICACAO.xlsx` e `ABUND.xlsx` em `data/raw/` antes de rodar via CLI (ou use os nomes definidos nas variáveis de ambiente `OMICS_IDENT_FILE` / `OMICS_ABUND_FILE`).
