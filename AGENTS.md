# Instruções de IA — Nix (Servidor MCP de Conhecimento)

Você atua como **Engenheiro de Software Sênior** no Nix. Gere código
**robusto, performático e enxuto**.

O Nix é um **servidor MCP em Python 3.11+** que expõe um **vault do Obsidian**
como ferramentas para agentes de desenvolvimento (Cursor, Claude Code, Copilot).
O núcleo de domínio é `src/nix/core` (vault, indexação, recuperação e
ferramentas). A **CLI** (`src/nix/cli`, Typer) é só bootstrap (`init`, `sync`,
`status`, `doctor`); o **servidor MCP** (`src/nix/mcp`) fala **stdio**. Sem
subcomando, `nix` inicia o servidor. Embeddings e banco vetorial são **locais e
gratuitos** (FastEmbed + ChromaDB), com o estado do índice em SQLite. Não há
LLM próprio: o raciocínio fica no cliente MCP.

---

## Documentação de referência

Consulte o documento certo para cada necessidade — **não duplique** regras que
já estão nos outros arquivos.

| Necessidade | Documento |
|-------------|-----------|
| Escopo, funcionalidades, regras de negócio, roadmap | [`PRD.md`](PRD.md) |
| Arquitetura (componentes, indexação, recuperação, MCP stdio, configuração, segurança) | [`ARCHITECTURE.md`](ARCHITECTURE.md) |

---

## Skills do agente

Quando a tarefa corresponder a uma skill abaixo, **leia o `SKILL.md` completo
antes** de agir — as skills têm fluxos e restrições que não estão duplicadas
neste arquivo.

### Projeto (versionadas no repositório)

| Necessidade | Skill | Caminho |
|-------------|-------|---------|
| Revisão de código (sugestões, SOLID, arquitetura; **sem implementar**) | `revisao-codigo` | [`.cursor/skills/revisao-codigo/SKILL.md`](.cursor/skills/revisao-codigo/SKILL.md) |

**Prioridade:** para *code review* com sugestões alinhadas ao `ARCHITECTURE.md` e sem
editar arquivos, use **`revisao-codigo`**.

---

## Regras obrigatórias do agente

### Antes de codar

1. Leia **`PRD.md`** quando a tarefa envolver comportamento do produto, comandos,
   fluxos do usuário ou regras de negócio.
2. Leia **`ARCHITECTURE.md`** quando a tarefa envolver estrutura de pastas, camadas,
   dependências, pipeline de indexação, recuperação, servidor MCP ou configuração.
3. Se algo estiver **ambíguo ou contraditório**, não invente: registre a
   suposição em uma linha ou peça esclarecimento **antes** de codar.

### Python — convenções

- **Camadas:** `nix.core` é o núcleo e **não** importa de `nix.cli` nem de `nix.mcp`.
  CLI e MCP são adaptadores finos: fazem *parsing* de entrada, formatação de saída e
  delegam — **nenhuma regra de negócio** vive neles.
- **Ferramentas:** toda capacidade exposta ao cliente é definida **uma única vez** em
  `core/tools/registry.py` e registrada no MCP. Nunca implemente a mesma operação
  duas vezes para atender CLI e MCP.
- **Vetorização** (RN-01/RN-02 do `PRD.md`): **proibido** criar *watcher* de arquivos ou
  indexar alterações externas automaticamente — isso só ocorre por `nix sync` ou pela
  ferramenta MCP `sync_index`. Escritas originadas nas ferramentas reindexam o arquivo
  na mesma operação (*write-through*), via `core/index/writeback.py`.
- **Acesso a arquivos:** apenas por `core/vault/`, com caminhos resolvidos e validados em
  `core/vault/paths.py`. Nenhuma leitura ou escrita fora do vault; escrita atômica
  (temporário + *rename*), *backup* antes de sobrescrever e confirmação em operações
  destrutivas.
- **Persistência do índice:** acesse Chroma e SQLite apenas por `core/index/vectorstore.py`
  e `core/index/store.py`; sincronização é transacional por arquivo.
- **MCP:** stdout pertence ao protocolo — sem `print`, logs só em arquivo. O transporte
  é **somente stdio**; o cliente (Cursor, Claude Code, Copilot) inicia o processo.
- **Configuração e segredos:** leia configuração apenas pelo objeto validado de `config/`.
  Não commite segredos; use variáveis de ambiente.
- **Tipagem e estilo:** *type hints* obrigatórios em funções públicas; `ruff` e `mypy`
  sem erros. Mensagens de erro devem indicar a **ação corretiva**.
- **Testes:** **não** crie nem execute testes por iniciativa própria. Só
  escreva testes quando o usuário pedir explicitamente. A validação padrão de uma
  alteração é `ruff` e `mypy` limpos mais uma verificação manual do comportamento.

### Comandos

Ambiente (escolha um): `setup.bat` no Windows, `./setup.sh` no Unix, ou o fluxo manual abaixo. O instalador só orquestra venv + pip + `nix init` — **nenhuma regra de negócio** vive em `scripts/bootstrap.py`.

```bash
python -m venv .venv && source .venv/Scripts/activate   # Linux/macOS: .venv/bin/activate
pip install -r requirements-dev.txt && pip install -e .
ruff check src && mypy src
```

Dependências ficam em `requirements.txt` (runtime) e `requirements-dev.txt` (desenvolvimento);
o `pyproject.toml` guarda apenas metadados do pacote e o *entry point* do comando `nix`.
No cliente MCP da IDE, use o Python do `.venv` (`python -m nix`), não o comando `nix` no PATH.

### Comunicação e idioma

- **Português (Brasil):** explicações ao usuário, comentários, docstrings, logs, mensagens
  de erro e textos exibidos na CLI.
- **Inglês:** nomes de variáveis, funções, classes, módulos, tabelas e ferramentas.
