# Registro de alterações no pipeline omics-etl

Este documento lista o que foi alterado no projeto, **por quê**, e trechos **antes × depois** (o “antes” reflete a lógica da versão anterior ao ajuste; o “depois” aponta para linhas do código atual).

**Nota:** Referências `omics-etl-pipeline/...` assumem a raiz do workspace em `ProjetoAplicadoII`. Se abrires só a pasta `omics-etl-pipeline`, remove esse prefixo nos caminhos.

---

## 1. Pacotes `src` — `src/__init__.py`, `src/etl/__init__.py`, `src/api/__init__.py`

**Por quê:** Tratar `src` como pacote Python e alinhar imports `from src....`

**Antes:** *(ficheiros inexistentes — nada a citar).*

**Depois** — exemplo `src/__init__.py`:

```1:1:omics-etl-pipeline/src/__init__.py
# Pacote raiz do pipeline (omics-etl-pipeline).
```

*(Os outros dois ficheiros seguem a mesma ideia: comentário mínimo por pasta.)*

---

## 2. `pyrightconfig.json` (raiz de `omics-etl-pipeline`)

**Por quê:** Resolver imports (`src.*`, `pandas`) e associar o ambiente `.venv` ao analisador.

**Antes:** *(ficheiro inexistente.)*

**Depois:**

```1:7:omics-etl-pipeline/pyrightconfig.json
{
  "include": ["src"],
  "extraPaths": ["."],
  "venvPath": ".",
  "venv": ".venv"
}
```

---

## 3. `.vscode/settings.json`

**Por quê:** O IDE usar o Python do `.venv` e incluir a raiz do projeto em `extraPaths` (Pylance).

### Workspace `ProjetoAplicadoII` (pasta pai)

**Antes:** *(inexistente ou sem estas chaves.)*

**Depois** — ficheiro `ProjetoAplicadoII/.vscode/settings.json` (quando o workspace aberto é a pasta **ProjetoAplicadoII**):

```1:4:.vscode/settings.json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/omics-etl-pipeline/.venv/Scripts/python.exe",
  "python.analysis.extraPaths": ["${workspaceFolder}/omics-etl-pipeline"]
}
```

### Workspace só `omics-etl-pipeline`

**Depois:**

```1:4:omics-etl-pipeline/.vscode/settings.json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
  "python.analysis.extraPaths": ["${workspaceFolder}"]
}
```

---

## 4. `src/etl/extract.py`

### 4.1 Imports e leitura de ficheiros (CSV vs Excel)

**Antes:**

```python
import pandas as pd
import logging
from pathlib import Path
from typing import Optional
# ...
        df_ident = pd.read_csv(caminho_ident, encoding='latin1', sep=';')
        df_abund = pd.read_csv(caminho_abund, encoding='latin1', sep=';')
```

**Por quê:** Ficheiros `.xlsx` não devem ser lidos com `read_csv`; é preciso Excel + `openpyxl`.

**Depois** — helper e uso:

```16:23:omics-etl-pipeline/src/etl/extract.py
def _ler_tabela(caminho: Path) -> pd.DataFrame:
    """Lê CSV (sep `;`, latin1) ou Excel (.xlsx via openpyxl)."""
    suf = caminho.suffix.lower()
    if suf in (".xlsx", ".xlsm"):
        return pd.read_excel(caminho, engine="openpyxl")
    if suf == ".xls":
        return pd.read_excel(caminho)
    return pd.read_csv(caminho, encoding="latin1", sep=";")
```

```78:81:omics-etl-pipeline/src/etl/extract.py
        # Leitura dos dados
        logger.info("Lendo ficheiros CSV/Excel para a memória...")
        df_ident = _ler_tabela(caminho_ident)
        df_abund = _ler_tabela(caminho_abund)
```

*(Também foi acrescentado `import os` na linha 1 para as variáveis de ambiente no `__main__`.)*

### 4.2 Normalização após `merge` (colunas `_x` / `_y`)

**Antes:**

```python
        df_consolidado = pd.merge(df_ident, df_abund, on='Compound', how='inner')
        # (sem passo seguinte — ficavam m/z_x, m/z_y, etc.)
```

**Por quê:** O `transform.py` e a pré-visualização esperam `m/z` e `Retention time (min)` sem sufixo.

**Depois:**

```26:53:omics-etl-pipeline/src/etl/extract.py
def _normalizar_colunas_apos_merge(df: pd.DataFrame) -> pd.DataFrame:
    """
    Após merge, o pandas renomeia colunas iguais com _x / _y.
    Unifica nomes esperados pelo restante do pipeline (ex.: transform.py).
    Prioridade: coluna da direita (_y), típica de abundância.
    """
    out = df.copy()

    for base in ("m/z", "Retention time (min)"):
        if base in out.columns:
            continue
        for suf in ("_y", "_x"):
            alt = f"{base}{suf}"
            if alt in out.columns:
                out[base] = out[alt]
                break

    if "Description" not in out.columns and "Description_x" in out.columns:
        out["Description"] = out["Description_x"]

    drop_candidates = [
        c
        for c in out.columns
        if c.endswith("_x") or c.endswith("_y")
    ]
    # Mantém só o que sobrou duplicado; remove sufixos já copiados para canonical
    out = out.drop(columns=[c for c in drop_candidates if c in out.columns], errors="ignore")
    return out
```

```83:86:omics-etl-pipeline/src/etl/extract.py
        # Cruzamento (Merge) usando a coluna padrão do equipamento 'Compound'
        logger.info("Realizando o cruzamento (Merge) entre Identificação e Abundância...")
        df_consolidado = pd.merge(df_ident, df_abund, on="Compound", how="inner")
        df_consolidado = _normalizar_colunas_apos_merge(df_consolidado)
```

### 4.3 `__main__`: nomes de ficheiros e pré-visualização

**Antes:**

```python
    ARQUIVO_IDENT = RAW_DIR / "IDENTIFICACAO.xlsx"
    ARQUIVO_ABUND = RAW_DIR / "ABUND.xlsx"
    # ...
        print(df_resultado[['Compound', 'Description', 'm/z', 'Retention time (min)']].head())
```

**Por quê:** Nomes configuráveis via ambiente; colunas fixas geravam `KeyError` após o merge.

**Depois:**

```108:124:omics-etl-pipeline/src/etl/extract.py
    # Sobrescreva com variáveis de ambiente se os nomes forem outros, ex.:
    # $env:OMICS_IDENT_FILE = "IDENTIFICACAO.csv"; $env:OMICS_ABUND_FILE = "ABUND.csv"
    nome_ident = os.environ.get("OMICS_IDENT_FILE", "IDENTIFICACAO.xlsx")
    nome_abund = os.environ.get("OMICS_ABUND_FILE", "ABUND.xlsx")
    ARQUIVO_IDENT = RAW_DIR / nome_ident
    ARQUIVO_ABUND = RAW_DIR / nome_abund
    
    df_resultado = extrair_dados_brutos(ARQUIVO_IDENT, ARQUIVO_ABUND)
    
    if df_resultado is not None:
        print("\nPré-visualização do DataFrame Consolidado:")
        # Mostra as colunas essenciais que vamos enviar para a API
        desejadas = ["Compound", "Description", "m/z", "Retention time (min)"]
        cols = [c for c in desejadas if c in df_resultado.columns]
        if not cols:
            cols = list(df_resultado.columns)[:8]
        print(df_resultado[cols].head())
```

---

## 5. `src/etl/transform.py`

### 5.1 Encoding do terminal (Windows) e ordem no `sys.path`

**Antes:**

```python
import pandas as pd
import logging
import sys
from pathlib import Path

# Configuração para o Python encontrar as nossas pastas 'src'
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))
```

**Por quê:** `print` com símbolos fora de cp1252 falhava; `insert(0, ...)` prioriza a raiz do projeto.

**Depois:**

```1:17:omics-etl-pipeline/src/etl/transform.py
import os
import pandas as pd
import logging
import sys
from pathlib import Path

# Evita UnicodeEncodeError no print (Windows/cp1252) com emojis nos logs
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Configuração para o Python encontrar as nossas pastas 'src'
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
```

### 5.2 Bloco `__main__` e mensagem final

**Antes:**

```python
    RAW_DIR = BASE_DIR / 'data' / 'raw'
    ARQUIVO_IDENT = RAW_DIR / "IDENTIFICACAO.xlsx"
    ARQUIVO_ABUND = RAW_DIR / "ABUND.xlsx"
    # ...
        print("\n📊 VISUALIZAÇÃO DO DATAFRAME FINAL (Pronto para o PostgreSQL/SQLite):")
```

**Por quê:** Mesmos nomes configuráveis que em `extract.py`; emoji no `print` podia gerar `UnicodeEncodeError`.

**Depois:**

```93:109:omics-etl-pipeline/src/etl/transform.py
if __name__ == "__main__":
    # Caminhos dos arquivos brutos (mesmas variáveis que em extract.py)
    RAW_DIR = BASE_DIR / "data" / "raw"
    nome_ident = os.environ.get("OMICS_IDENT_FILE", "IDENTIFICACAO.xlsx")
    nome_abund = os.environ.get("OMICS_ABUND_FILE", "ABUND.xlsx")
    ARQUIVO_IDENT = RAW_DIR / nome_ident
    ARQUIVO_ABUND = RAW_DIR / nome_abund
    
    # 1. EXTRAIR
    df_bruto = extrair_dados_brutos(ARQUIVO_IDENT, ARQUIVO_ABUND)
    
    if df_bruto is not None:
        # 2. TRANSFORMAR E ENRIQUECER
        df_pronto_para_banco = enriquecer_dados_laboratorio(df_bruto)
        
        print("\n[VISUALIZACAO] DataFrame final (pronto para SQLite/PostgreSQL):")
        print(df_pronto_para_banco.to_string())
```

---

## 6. O que **não** entrou neste registro

- `load.py`, `main.py`, UI, etc., **não** foram alterados nesta rodada (além do contexto acima).
- Dados em `data/raw/` e `banco_ist.db` continuam ignorados pelo `.gitignore` original.

---

## Como reproduzir o ambiente após clonar

```text
cd omics-etl-pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Interpreter do IDE: `omics-etl-pipeline\.venv\Scripts\python.exe`.
