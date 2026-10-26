# TDD — Nix

Especificações técnicas do Nix, servidor MCP que expõe vaults do Obsidian a agentes de desenvolvimento.

Contexto de negócio e requisitos: [PRD.md](./PRD.md).

---

## 1. Princípios de design

1. **Núcleo independente de interface.** Toda a lógica vive em `nix.core`. CLI, MCP e a interface local são adaptadores finos que chamam os mesmos serviços. Nenhuma regra de negócio é duplicada.
2. **Local por padrão.** Embeddings e banco vetorial rodam na máquina do usuário, sem custo e sem enviar o vault para terceiros. O Nix não faz chamadas remotas.
3. **Indexação sob consentimento.** Não existe watcher de arquivos. O vault só é varrido quando o usuário pede (`nix sync` / ferramenta `sync_index`) ou quando as próprias ferramentas escrevem (write-through).
4. **O vault é a fonte da verdade.** O índice é um artefato derivado e descartável: apagar `index.data_dir` (padrão `.nix/data` na pasta do aplicativo) e rodar `nix sync --full` reconstrói tudo.
5. **Ferramentas antes de prompts.** A capacidade exposta ao cliente é um conjunto pequeno e bem tipado de ferramentas, definido uma vez em `core/tools/registry.py`.
6. **Falhar de forma explícita.** Erros de configuração, defasagem de índice e ausência de resultados são comunicados, nunca mascarados.

## 2. Stack

| Camada | Tecnologia | Justificativa |
| --- | --- | --- |
| Linguagem | Python 3.11+ (CI e tipos em 3.14) | Ecossistema de IA e requisito do projeto |
| Embeddings | FastEmbed com `BAAI/bge-m3` (ONNX, CPU) | Local, gratuito, multilíngue (PT/EN), sem GPU, sem dependência de PyTorch |
| Banco vetorial | ChromaDB 1.5.x em modo persistente | Local, gratuito, embutido; faixa pinada pelo grafo de import (OTEL/gRPC) |
| Busca léxica | SQLite FTS5 | Já disponível na stdlib; complementa a busca vetorial em termos exatos |
| Estado do índice | SQLite | Controle de arquivos, hashes e chunks; transacional |
| CLI de bootstrap | Typer + Rich | Comandos tipados, ajuda automática, saída formatada e progresso |
| Servidor MCP | SDK oficial `mcp` (FastMCP, **somente stdio**) | O cliente inicia o processo; stdout é do protocolo |
| Interface local | Starlette + Uvicorn (já no SDK `mcp`) + Jinja2, HTMX e Pico.css vendidos no pacote | Formulário e operação no navegador, sem Node e sem CDN |
| Configuração | SQLite (`settings.db`) + Pydantic | Histórico e desfazer no mesmo arquivo, validação forte, override por variável de ambiente |
| Parsing de Markdown | `python-frontmatter` + splitter consciente de cabeçalhos | Preserva metadados e estrutura das notas |
| Qualidade | ruff, mypy | Padrão do ecossistema |

**Por que embeddings locais e não `text-embedding-3`:** o requisito é custo zero na indexação. Um vault grande gera dezenas de milhares de chunks e cada reindexação completa teria custo. `bge-m3` roda em CPU, é multilíngue e tem qualidade adequada para busca semântica em notas pessoais.

**Por que Chroma e não FAISS/LanceDB:** Chroma persiste sozinho, guarda metadados junto do vetor e permite deletar por `file_id` na sincronização incremental. Filtros de pasta/tag/data são aplicados na camada de recuperação (prefixo de pasta, tags, `mtime`), não como `where` de igualdade no Chroma — subpastas continuam visíveis. FAISS exigiria gerenciar o mapeamento id↔metadado manualmente.

## 3. Visão de componentes

```mermaid
graph TB
    subgraph Interfaces
        Client["Cursor / Claude Code / Copilot"]
        CLI["CLI<br/>init / config / sync / status / doctor / ui"]
        UI["Interface local<br/>nix ui"]
        MCP["Servidor MCP<br/>stdio"]
    end

    subgraph Core["nix.core"]
        TOOLS["Toolbelt<br/>registry.py"]
        RAG["Serviço de recuperação<br/>híbrido + reordenação"]
        IDX["Serviço de indexação<br/>sync incremental / write-through"]
        VAULT["Serviço de vault<br/>leitura, escrita, confinamento"]
        CFG["Configuração<br/>settings.db + env"]
    end

    subgraph Infra["Infraestrutura local"]
        CHROMA[("ChromaDB<br/>.nix/data/chroma")]
        SQLITE[("SQLite<br/>.nix/data/index.db")]
        EMB["FastEmbed / bge-m3<br/>CPU"]
        FS[("Vault Obsidian<br/>*.md")]
    end

    Client -->|"MCP stdio"| MCP
    CLI --> CFG
    CLI --> IDX
    UI --> CFG
    UI --> IDX
    MCP --> TOOLS
    TOOLS --> RAG
    TOOLS --> VAULT
    TOOLS --> IDX
    RAG --> CHROMA
    RAG --> SQLITE
    RAG --> EMB
    IDX --> CHROMA
    IDX --> SQLITE
    IDX --> EMB
    IDX --> VAULT
    VAULT --> FS
    CFG -.-> Core
```

## 4. Estrutura do projeto

```
nix/
├── install.bat / install.sh / install.ps1  # baixa o binário, confere SHA-256, registra PATH e inicia `nix init`
├── uninstall.bat / uninstall.sh / uninstall.ps1  # remove PATH/NIX_HOME, o binário, .nix e settings.db
├── bin/nix / bin/nix.cmd   # shims só do checkout de desenvolvimento (acham o .venv)
├── bin/env.sh / bin/env.cmd / bin/env.ps1  # ativação manual do PATH no checkout
├── __main__.py             # `python -m nix` a partir do projeto pai (pasta nix/)
├── scripts/bootstrap.py    # venv + pip + init (desenvolvimento)
├── scripts/build_frozen.py # Nuitka onefile, Python 3.12, na plataforma local
├── scripts/smoke_frozen.py # gate de --version e doctor do binário
├── scripts/register_path.py # NIX_HOME e PATH do checkout de desenvolvimento
├── scripts/uninstall.py    # desfaz PATH e apaga artefatos do checkout
├── nix.jpeg                # foto da Nix (mascote no README)
├── settings.db            # config local (não versionado; criado por `nix init`)
├── .nix/                   # estado local: data (SQLite+Chroma), backups, logs
├── pyproject.toml          # metadados do pacote e entry point do comando `nix`
├── requirements.txt        # dependências de runtime
├── requirements-dev.txt    # dependências de desenvolvimento
├── README.md
├── PRD.md
├── TDD.md
├── AGENTS.md / CLAUDE.md   # instruções de agente (CLAUDE.md importa o AGENTS.md)
├── skills-lock.json        # origem das skills (paulocesaaars/skills)
├── .claude/skills/ / .agents/skills/  # cópias das skills de desenvolvimento; não editar aqui
├── .cursor/
│   └── mcp.json            # command = binário em NIX_HOME (caminho absoluto no Unix)
└── src/
    ├── nix_launch.py           # relança o venv, desfaz sombreamento da pasta nix/
    ├── nix_frozen.py           # entrada do binário; não relança o .venv
    └── nix/
        ├── __init__.py
        ├── __main__.py             # python -m nix (pacote instalado)
        ├── config/
        │   ├── schema.py           # modelos Pydantic da configuração e textos de ajuda
        │   ├── embedding_models.py # catálogo técnico dos embeddings (validação + FastEmbed)
        │   ├── embedding_present.py # textos de apresentação dos modelos (CLI e interface)
        │   ├── store.py            # settings.db: valores, histórico, versão do esquema
        │   ├── editor.py           # gravação validada (CLI e interface)
        │   ├── loader.py           # precedência env > banco > padrão
        │   └── paths.py            # app_root; no binário, NIX_HOME ou a pasta de dados da plataforma
        ├── core/
        │   ├── vault/
        │   │   ├── reader.py       # varredura, filtros, leitura segura
        │   │   ├── writer.py       # escrita atômica, backup, YAML, confinamento
        │   │   ├── markdown.py     # frontmatter, cabeçalhos, wikilinks, tags, links
        │   │   ├── frontmatter_edit.py  # edição linha a linha do YAML
        │   │   ├── paths.py        # normalização e validação de caminhos
        │   │   └── longterm.py     # remember → notas no vault
        │   ├── index/
        │   │   ├── store.py        # SQLite: arquivos, chunks, metadados
        │   │   ├── chunker.py      # divisão consciente da estrutura
        │   │   ├── embedder.py     # FastEmbed em lote; stdout capturado por padrão
        │   │   ├── native_compat.py # mmh3 nativo ou stub (só import FastEmbed)
        │   │   ├── tokenize.py     # tiktoken, com aproximação se a DLL falhar
        │   │   ├── vectorstore.py  # adaptador Chroma
        │   │   ├── sync.py         # diff e sincronização incremental
        │   │   ├── lock.py         # trava entre processos (.nix/sync.lock)
        │   │   ├── writeback.py    # reindexação write-through
        │   │   ├── attachments.py  # texto de PDFs referenciados
        │   │   ├── graph.py        # grafo de wikilinks (cache)
        │   │   └── staleness.py    # aviso de defasagem (só Markdown)
        │   ├── retrieval/
        │   │   ├── vector.py       # busca densa
        │   │   ├── lexical.py      # busca FTS5
        │   │   ├── fusion.py       # Reciprocal Rank Fusion
        │   │   ├── rerank.py       # cross-encoder opcional
        │   │   └── service.py      # fachada de recuperação
        │   ├── insights/           # órfãs, duplicatas, links, resumo
        │   ├── admin/              # init e relatório do doctor, sem saída de terminal
        │   └── tools/
        │       ├── registry.py     # definição canônica das ferramentas
        │       ├── search.py
        │       ├── notes.py
        │       └── maintenance.py
        ├── cli/
        │   ├── app.py              # entrypoint Typer (sem args → servidor stdio)
        │   ├── ascii-art.txt
        │   ├── commands/
        │   │   ├── setup.py        # init, doctor
        │   │   ├── config_cmds.py  # config list/get/set/unset/history/undo
        │   │   ├── ui_cmd.py       # nix ui
        │   │   └── index_cmds.py   # sync, status (status via call_tool)
        │   ├── embedding_copy.py   # tabela do nix init; textos em config/embedding_present.py
        │   └── render.py           # banner, tabelas de sync/status, erros em stderr
        ├── mcp/
        │   ├── server.py           # FastMCP/MCPServer stdio; recarrega a config entre chamadas
        │   ├── traffic.py          # log de interações MCP (arquivo)
        │   └── resources.py        # nix://note/{+rel_path}
        ├── web/                    # nix ui: Starlette, templates Jinja2, HTMX e Pico vendidos
        └── observability/
            ├── logging.py
            └── stdio.py            # isola stdout de bibliotecas
```

Quem usa o Nix instala um binário único (Nuitka, arquivo só, sem Python na máquina). O instalador (`install.ps1` / `install.sh`, e `install.bat` que delega ao PowerShell) baixa o artefato da release, confere o SHA-256, grava `NIX_HOME` e dispara `nix init`. O desinstalador em shell puro desfaz o PATH e apaga o binário, `.nix/` e `settings.db`.

O checkout de desenvolvimento continua com `venv` e `pip`: `python scripts/bootstrap.py` cria `.venv`, instala `requirements.txt` e o pacote em modo editável (`pip install -e .`). `scripts/uninstall.py` desfaz esse checkout. O `pyproject.toml` se limita aos metadados do pacote e à declaração do *entry point* `nix`. O binário é compilado por `scripts/build_frozen.py` com Python 3.12.

## 5. Modelo de dados

### 5.1 SQLite (`index.data_dir/index.db`, padrão `.nix/data/index.db` na pasta do app)

Guarda o estado do índice: o que já foi processado, com qual conteúdo e com qual modelo. É a base do diff incremental.

```sql
CREATE TABLE files (
    id            TEXT PRIMARY KEY,       -- uuid estável por caminho relativo
    rel_path      TEXT NOT NULL UNIQUE,   -- 'Projetos/Nix.md'
    title         TEXT,
    content_hash  TEXT NOT NULL,          -- sha256 do conteúdo
    mtime         REAL NOT NULL,
    size_bytes    INTEGER NOT NULL,
    frontmatter   TEXT,                   -- JSON
    tags          TEXT,                   -- JSON array
    links         TEXT,                   -- JSON array de wikilinks
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    indexed_at    TEXT NOT NULL,
    status        TEXT NOT NULL           -- indexed | error | ignored
);

CREATE TABLE chunks (
    id            TEXT PRIMARY KEY,       -- '{file_id}:{ordinal}'
    file_id       TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    ordinal       INTEGER NOT NULL,
    heading_path  TEXT,                   -- 'Arquitetura > Indexação'
    content       TEXT NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    token_count   INTEGER NOT NULL,
    start_line    INTEGER,
    end_line      INTEGER
);

-- Busca léxica sobre os mesmos chunks
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    content, heading_path, title,
    content='chunks', content_rowid='rowid', tokenize='unicode61'
);

CREATE TABLE index_meta (
    key   TEXT PRIMARY KEY,               -- embedding_model, dim, vault_path,
    value TEXT NOT NULL                   -- schema_version, last_sync_at
);

CREATE TABLE sync_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    trigger      TEXT NOT NULL,           -- manual | writeback
    added        INTEGER DEFAULT 0,
    updated      INTEGER DEFAULT 0,
    removed      INTEGER DEFAULT 0,
    failed       INTEGER DEFAULT 0,
    error_log    TEXT
);
```

`index_meta.embedding_model` é comparado a cada execução: se o usuário trocar o modelo na configuração, o índice é considerado incompatível e o Nix exige `nix sync --full` em vez de misturar vetores de espaços diferentes.

### 5.2 Coleção Chroma

Uma coleção `nix_notes`, um vetor por chunk, `id` idêntico ao `chunks.id`. Metadados armazenados junto:

| Campo | Uso |
| --- | --- |
| `file_id` | Deleção em massa na reindexação de um arquivo |
| `rel_path`, `title` | Citação e abertura da nota |
| `heading_path` | Contexto do trecho na resposta |
| `tags` | Filtro por tag (após a busca; armazenado como string concatenada no Chroma) |
| `folder` | Prefixo da pasta (inclui subpastas), filtrado após a busca — sem `where` de igualdade no Chroma |
| `mtime` | Filtro por recência e desempate |
| `ordinal` | Reconstrução da ordem e expansão de vizinhos |

## 6. Pipeline de indexação

### 6.1 Detecção de mudanças

```mermaid
sequenceDiagram
    participant U as Usuario
    participant S as Servico de sync
    participant V as Vault
    participant DB as SQLite
    participant E as Embedder
    participant C as Chroma

    U->>S: nix sync ou sync_index
    S->>DB: verifica compatibilidade do modelo
    S->>V: varre .md aplicando include/exclude
    V-->>S: lista de arquivos com mtime e tamanho
    S->>DB: carrega estado conhecido
    S->>S: candidatos = mtime ou tamanho diferentes
    S->>V: le candidatos e calcula sha256
    S->>S: diff = novos + alterados + removidos
    Note over S: hash igual, arquivo pulado
    loop por arquivo alterado
        S->>S: parse frontmatter, headings, links
        S->>S: chunking estrutural
        S->>C: delete where file_id
        S->>E: embed dos chunks em lote
        E-->>S: vetores
        S->>C: upsert
        S->>DB: substitui chunks e atualiza arquivo
    end
    loop por arquivo removido
        S->>C: delete where file_id
        S->>DB: delete cascade
    end
    S->>DB: grava sync_run
    S-->>U: resumo adicionados/atualizados/removidos/erros/tempo
```

O filtro em duas etapas — `mtime`/tamanho primeiro, hash depois — evita ler todo o vault a cada sincronização e evita reindexar arquivos que só tiveram o timestamp alterado (comum em sincronização por Dropbox/Git).

Cada arquivo é uma transação independente: uma interrupção deixa o índice consistente, e a execução seguinte reprocessa apenas o que faltou (RNF-07).

### 6.2 Chunking

Notas de Obsidian têm estrutura semântica em cabeçalhos, e cortá-las por número fixo de caracteres destrói essa estrutura. A estratégia:

1. Extrair frontmatter YAML (vira metadado JSON-serializável — datas ISO — não texto indexado).
2. Dividir por cabeçalhos Markdown (`#` até `####`), mantendo o caminho hierárquico (`Projeto Nix > Arquitetura > Indexação`).
3. Seções maiores que o limite são subdivididas recursivamente por parágrafo/sentença, com sobreposição configurável.
4. Seções muito pequenas (ex.: um cabeçalho com duas linhas) são agrupadas com a seção seguinte, evitando chunks sem sinal.
5. Blocos de código nunca são partidos ao meio.
6. Cada chunk é prefixado, apenas para o embedding, com `título da nota > caminho de cabeçalhos`, o que melhora a recuperação de trechos curtos.

Valores padrão: 800 tokens por chunk, 120 de sobreposição, mínimo de 80 tokens — todos configuráveis.

### 6.3 Vetorização write-through

Quando a escrita parte das ferramentas MCP, a atualização do índice faz parte da operação (RN-02):

```mermaid
sequenceDiagram
    participant A as MCP
    participant W as Vault writer
    participant WB as Writeback
    participant C as Chroma e SQLite

    A->>W: create_note / update_note / append_to_note
    W->>W: valida confinamento e faz backup
    W->>W: escrita atomica tmp + rename
    W-->>WB: caminho gravado
    WB->>WB: reparse e rechunk do arquivo
    WB->>C: delete por file_id + upsert dos novos chunks
    C-->>A: path e chunks_indexed
```

O reprocessamento é de um único arquivo. Se a indexação falhar após a escrita, o arquivo no vault permanece (fonte da verdade), o registro vai para `status = 'error'` e a resposta informa que a nota foi salva mas não indexada — o usuário deve rodar `nix sync` ou `sync_index`. Frontmatter YAML é gravado com valores escapados; datas (`created: auto` → ISO) serializam como string, para o JSON do SQLite não quebrar em objetos `date`.

### 6.4 Aviso de defasagem

`index_status` compara a **contagem de notas Markdown** visíveis no vault com a de arquivos `.md` indexados, e o `mtime` máximo com `index_meta.last_sync_at`. PDFs anexos no índice não entram nessa conta (evita aviso falso de defasagem). Se houver divergência, devolve `stale=true`. A mensagem `stale_reason` só é preenchida quando `index.warn_when_stale=true`. Não há indexação implícita (RN-01).

## 7. Recuperação

```mermaid
graph LR
    Q[Consulta] --> D[Busca densa Chroma]
    Q --> L[Busca lexica FTS5]
    D --> FIL[Filtros pasta/tag/data e include/exclude]
    L --> FIL
    FIL --> F[Fusao RRF]
    F --> EXP[Expansao de vizinhos]
    EXP --> CUT[Corte min_score e relativo ao melhor]
    CUT --> CTX[Trechos com caminho e citacao]
```

- **Densa** resolve similaridade conceitual ("como configurar o retry" ↔ "política de nova tentativa").
- **Léxica** resolve termos exatos que embeddings costumam diluir: nomes próprios, siglas, códigos de erro, nomes de arquivo. `retrieval.expand_query=true` junta tokens com OR (mais recall); `false` usa AND (mais precisão).
- **Filtro de pasta** vale para a pasta e subpastas (`Inbox` inclui `Inbox/sub/nota.md`), aplicado em cada ramo **antes** do RRF.
- **RRF** funde os dois rankings: `score(d) = Σ 1 / (k + rank_i(d))`, com `k = 60`.
- **Expansão de vizinhos** recupera os chunks `ordinal ± 1` dos melhores resultados.
- **Corte de score** descarta trechos abaixo de `max(min_score, melhor × 0.65)`.
- **Reordenação** é opcional (`retrieval.rerank`), com cross-encoder local (`index.rerank_model`), aplicada ao top-20.

Cada trecho devolvido por `search_notes` inclui `rel_path`, `title`, `heading_path`, `content` e `citation` no formato `[[Título]]` / `[[Título#Seção]]` (RN-04). A síntese em linguagem natural é responsabilidade do cliente MCP.

## 8. Ferramentas

Definidas uma única vez em `core/tools/registry.py` e registradas no servidor MCP. A CLI de bootstrap chama `call_tool` para `index_status`; `nix sync` usa o mesmo `Indexer.sync` da ferramenta (com barra de progresso).

| Ferramenta | Assinatura | Efeito no índice |
| --- | --- | --- |
| `search_notes` | `(query, top_k=5, folder?, tags?, date_from?, date_to?) -> list[Chunk]` | — |
| `read_note` | `(rel_path) -> NoteContent` | — |
| `get_note_outline` | `(rel_path) -> NoteOutline` (título, chaves, linhas, headings) | — |
| `read_note_lines` | `(rel_path, start_line?, end_line?, heading?) -> NoteLines` | — |
| `list_notes` | `(folder?, tag?, limit=50) -> list[NoteRef]` (`rel_path`, `title`, `tags`) | — |
| `list_all_tags` | `(folder?, limit=200) -> list[{tag, count}]` | — |
| `get_linked_notes` | `(rel_path, direction=both) -> list[NoteRef]` | — |
| `create_note` | `(rel_path, content, frontmatter?) -> WriteResult` | write-through; pasta padrão `vault.default_new_note_folder` (`Inbox`) se o caminho não tiver `/` |
| `append_to_note` | `(rel_path, content, section?) -> WriteResult` | write-through |
| `update_note` | `(rel_path, content, mode=replace\|patch\|prepend, confirm) -> WriteResult` | write-through; `prepend` não exige `confirm` |
| `update_frontmatter` | `(rel_path, set?, remove?) -> WriteResult` | write-through; só a chave alterada é reemitida |
| `manage_tags` | `(rel_path, add?, remove?) -> WriteResult` | write-through; tags inline do corpo ficam |
| `move_note` | `(src, dest, update_links=true, overwrite, confirm) -> WriteResult` | `after_move`: remove o id antigo, indexa o caminho novo e as notas reescritas |
| `move_file` | `(src, dest, update_links=true, overwrite, confirm) -> WriteResult` | igual a `move_note` para o id; PDF só entra no índice com `index.index_attachments` |
| `delete_note` | `(rel_path, confirm) -> WriteResult` | remove do índice |
| `sync_index` | `(full=False, dry_run=False) -> SyncReport` | sincronização manual |
| `index_status` | `() -> IndexStatus` | — |
| `vault_insights` | `(kind, limit=20) -> insights` | — |
| `remember` | `(content, title?) -> WriteResult` | write-through em `vault.longterm_folder` |

Ferramentas destrutivas (`update_note` em modo `replace`, `delete_note`) exigem `confirm=true` e levam `destructiveHint` para o cliente pedir aprovação ao usuário (RF-34). `move_note` e `move_file` não levam `destructiveHint`; sobrescrever o destino ainda exige `overwrite=true` e `confirm=true`. `read_note_lines` devolve no máximo 400 linhas (`truncated`, `next_start_line`). As linhas de `search_notes`, do outline e de `read_note_lines` são do arquivo bruto, com o frontmatter incluído.

`vault_insights` (órfãs, duplicatas, sugestão de wikilinks, resumo) usa o índice SQLite. A sugestão de links não relê o vault.

Todas as ferramentas recebem `rel_path` relativo ao vault. `core/vault/paths.py` resolve, normaliza, rejeita `..`, caminhos absolutos e links simbólicos que escapem do vault (RN-03).

## 9. Interfaces

### 9.1 Instalador e CLI de bootstrap

O instalador na raiz do repositório não entra no núcleo: só baixa o binário e registra o PATH. Não exige Python.

```
install.ps1 / install.sh          # release estável (ou NIX_VERSION) → SHA-256 → {NIX_HOME}/bin/nix
install.bat                       # delega a install.ps1
uninstall.ps1 / uninstall.sh      # PATH, binário, settings.db e .nix (não o vault)
uninstall.bat                     # delega a uninstall.ps1
scripts/bootstrap.py              # só desenvolvimento: .venv → pip → register_path → nix init
scripts/build_frozen.py           # Nuitka --mode=onefile com Python 3.12
scripts/smoke_frozen.py           # stdout de --version e imports do doctor
```

O binário publicado cobre Windows amd64, Linux amd64 (glibc do Ubuntu 22.04), Linux arm64 e macOS arm64. Windows arm64 e macOS Intel não têm artefato: o instalador recusa com a arquitetura esperada. O modelo ONNX continua fora do arquivo; o primeiro `nix sync` baixa do Hugging Face.

`NIX_HOME` já definido (variável de usuário no Windows, ou o bloco dos rc no Unix) é a pasta da instalação, e o binário novo substitui `{NIX_HOME}/bin`. Sem `NIX_HOME`, a pasta é `%LOCALAPPDATA%\nix`, `~/Library/Application Support/nix` ou `${XDG_DATA_HOME:-~/.local/share}/nix`. Argumentos extras (`--vault PATH`, `--force`) vão para `nix init` só quando `settings.db` ainda não existe. O instalador roda `nix --version` uma vez para aquecer o cache do modo onefile (`{CACHE_DIR}/nix/onefile-{VERSION}`). O comando `nix` vale num **novo** terminal. Se já existir outro `nix` no PATH (gerenciador NixOS), o instalador avisa.

O desinstalador pede confirmação (dispensada com `--yes`). Remove `NIX_HOME` e a entrada do PATH só se apontarem para esta instalação; `--keep-data` preserva `settings.db` e `.nix/`. O vault não é alterado.

No binário, `app_root()` ignora o checkout (o `__file__` da extração não é o repositório) e não usa o CWD: vale `$NIX_HOME` ou a pasta de dados da plataforma. `settings.db` e `.nix/` ficam nessa pasta. Copiar só o executável para outro diretório continua usando a mesma pasta de dados.

```
nix                           # inicia o servidor MCP stdio
nix init [--vault PATH] [--embedding-model NOME] [--force]
                              # pergunta (ou recebe) o vault; grava settings.db
                              # sem --force, configuração existente só atualiza vault.path
nix config list|get|set|unset|history|undo
nix sync [--full] [--dry-run] [--json]
nix status [--json]           # via call_tool("index_status")
nix doctor [--json]           # relatório; --json serializa o mesmo DoctorReport
nix ui [--no-browser] [--port N]
                              # interface local; exige nix init
```

`--json` em `sync` e `status` emite o relatório em formato estruturado. `nix doctor --json` serializa o relatório de diagnóstico (ambiente, configuração e checagens). Erros de domínio (`NixError`) saem no stderr, sem traceback. Fora de `init` e `doctor`, os comandos falham com ação corretiva se o `nix init` ainda não rodou.

Se `nix` roda sem subcomando num terminal interativo, um aviso vai para stderr e o servidor stdio inicia mesmo assim — o cliente MCP (stdin não-TTY) não vê essa mensagem.

### 9.2 Servidor MCP

Transporte **somente stdio**. O cliente inicia o processo (o binário em `{NIX_HOME}/bin`; no checkout de desenvolvimento, `python -P -m nix` no venv). Expõe as ferramentas da seção 8 e, adicionalmente, notas como recursos MCP (`nix://note/{+rel_path}` — barras no caminho; `|` também é aceito), permitindo que o cliente anexe uma nota inteira ao contexto sem consumir uma chamada de ferramenta.

O servidor tenta `FastMCP` e, se o SDK recente expuser só `MCPServer`, usa essa classe — ambas precisam de `.tool()`, `.run()` e `transport="stdio"`. Falha de instância ou de transporte vira `ConfigError` com ação corretiva (`pip install 'mcp>=1.9.0'`). `NixError` na subida vai para stderr e encerra com código 1, sem vazar traceback no stdout.

Registro no Cursor (`.cursor/mcp.json`). `command` aponta para o binário **na pasta da instalação** (`NIX_HOME`), não para `nix` no PATH: a IDE aberta pelo Dock/menu não herda o PATH do shell (`spawn nix ENOENT`). A linha `comando nix:` do `nix doctor` é esse caminho. No checkout de desenvolvimento, os shims `bin/nix` e `bin/nix.cmd` chamam o Python do `.venv` com `-P -m nix`.

**Windows**

```json
{
  "mcpServers": {
    "nix": {
      "command": "${env:NIX_HOME}/bin/nix.exe"
    }
  }
}
```

No Windows a variável de usuário `NIX_HOME` está visível na IDE. O caminho absoluto (`C:/Users/voce/AppData/Local/nix/bin/nix.exe`) também vale.

**macOS / Linux**

```json
{
  "mcpServers": {
    "nix": {
      "command": "/Users/voce/Library/Application Support/nix/bin/nix"
    }
  }
}
```

Troque pelo caminho da linha `comando nix:` do `nix doctor`. `"command": "nix"` falha na IDE. `${env:NIX_HOME}` em geral não expande: o processo da IDE não lê os rcs do shell. No Linux a pasta padrão é `~/.local/share/nix/bin/nix`.

O servidor não escreve em stdout — o canal é do protocolo. Interações (`initialize`, `tools/list`, `tools/call`, `resources/read`) vão só para o arquivo de log. Argumentos das ferramentas (consultas, caminhos) só entram no log se `logging.log_prompts=true`. `ping` e notificações ficam em nível debug. Trocar `logging.file` ou o nível passa a valer quando o processo recarrega a configuração.

Antes de cada ferramenta, o processo compara a data da última gravação do `settings.db`. Se mudou, recompõe o `Runtime` com a configuração nova e mantém `index.embedding_model` e `index.data_dir` deste processo (a pasta é comparada já resolvida). Enquanto esses dois divergirem, a resposta da ferramenta inclui `config_warning`. A leitura de resource registra o mesmo aviso no log e devolve só o texto da nota. Troca de modelo continua exigindo `nix sync --full`.

### 9.3 Interface local

`nix ui` sobe Starlette em `127.0.0.1`, numa porta livre (ou `--port`), imprime a URL e abre o navegador (`--no-browser` só imprime). O processo termina com Ctrl+C ou com o botão Encerrar. Se houver sincronização, o botão pede para esperar e o Ctrl+C só fecha o índice depois que a thread termina. Sem `nix init`, o comando não sobe.

O token da URL vira cookie `HttpOnly` (`SameSite=Strict`). Pedidos seguintes exigem esse cookie. POST exige o mesmo token no formulário ou no header `X-CSRF-Token`. `Host` e `Origin` têm de ser o endereço local. Arquivos estáticos (HTMX, extensão SSE, Pico.css) estão no pacote; não há CDN.

Telas: status do índice, sincronização (prévia, progresso por SSE e confirmação extra para `--full`), diagnóstico, formulário de configuração (campo de ambiente fica travado) e histórico com desfazer. O formulário grava os campos alterados numa transação; se o conjunto fica inválido, nada daquele envio entra no banco. A sincronização roda numa thread e segura a trava de `.nix/sync.lock`, a mesma do `nix sync` e do write-through. Enquanto ela corre, status e diagnóstico não abrem o SQLite do índice por outra thread. O diagnóstico da interface usa o runtime deste processo; `nix doctor` no terminal abre o seu.

## 10. Configuração

Banco `{app_root}/settings.db`, fora de `index.data_dir`. No binário, `app_root` é `$NIX_HOME` ou a pasta de dados da plataforma. No checkout, `app_root` é a pasta do repositório, senão `$NIX_HOME`, senão o CWD. Caminhos relativos (`data_dir`, `backup_dir`, `logging.file`) resolvem contra `app_root`, não contra o CWD. Precedência: **variável de ambiente > settings.db > padrão** (RF-03). Variáveis no formato `NIX_SECAO__CAMPO` (ex.: `NIX_VAULT__PATH`). `nix init` grava no banco. Estado do índice (SQLite, Chroma, backups, logs) continua em `{app_root}/.nix/`.

```sql
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,   -- schema_version, initialized
    value TEXT NOT NULL
);
CREATE TABLE settings (
    section    TEXT NOT NULL,
    key        TEXT NOT NULL,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (section, key)
);
CREATE TABLE settings_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    section        TEXT NOT NULL,
    key            TEXT NOT NULL,
    old_value_json TEXT,          -- nulo se a chave não existia
    new_value_json TEXT,          -- nulo se a chave foi removida
    source         TEXT NOT NULL, -- init | cli | ui
    changed_at     TEXT NOT NULL
);
```

`schema_version` é `1`. Versão diferente da que o processo entende impede o uso e pede atualização. Só entram chaves de `vault`, `index`, `retrieval`, `safety` e `logging`. O texto de ajuda de cada campo está no schema Pydantic. `index.auto_sync_external_changes` não pode ser ligado (RN-01). Trocar modelo, pasta do índice ou tamanho de chunk avisa que é preciso `nix sync --full` e, no caso do modelo e de `data_dir`, reiniciar o processo. Trocar `include`, `exclude`, `follow_symlinks`, `index_attachments` ou `vault.path` avisa que é preciso `nix sync`.

Toda gravação valida o conjunto com Pydantic antes de persistir. Erros trazem o campo e a ação corretiva (RF-04, RNF-09). No Windows, `vault.path` é gravado com `/`. O histórico permite desfazer uma alteração (`nix config undo` ou o botão da interface), gravando o desfazer como uma mudança nova.

## 11. Segurança

| Vetor | Controle |
| --- | --- |
| Escrita fora do vault | Resolução canônica de caminho e verificação de prefixo; rejeição de `..`, caminhos absolutos e symlinks que escapem |
| Perda de conteúdo | Escrita atômica (arquivo temporário + rename), backup versionado antes de sobrescrever, confirmação obrigatória |
| Exposição de notas privadas | Filtros `exclude` aplicados na indexação **e** na leitura, para que uma nota excluída não seja acessível nem por `read_note` |
| Corrupção do protocolo MCP | stdout reservado ao stdio; logs só em arquivo; `silence_progress_env` na inicialização; FastEmbed com `capture_stdout=True` por padrão (a CLI de `sync` desliga só para mostrar o download); `NixError` só no stderr |
| Injeção via conteúdo de nota | Trechos recuperados são dados estruturados (caminho + conteúdo); ferramentas destrutivas sempre exigem confirmação humana |
| Corrupção do índice | Transação por arquivo, verificação de compatibilidade de modelo, reconstrução completa sempre disponível; trava de sync entre processos |
| Interface local | Escuta só em 127.0.0.1; token de uso único vira cookie HttpOnly; checagem de Host e Origin; CSRF nos POST |

## 12. Desempenho

| Operação | Alvo | Estratégia |
| --- | --- | --- |
| Sync incremental sem mudanças (5.000 notas) | < 2s | Comparação por `mtime`/tamanho antes de ler conteúdo |
| Sync inicial (1.000 notas) | ~5 min sem GPU | Embedding em lote, ONNX em CPU, paralelismo de parsing |
| Reindexação write-through de 1 nota | < 100ms | Escopo de um único arquivo |
| Busca híbrida | < 500ms | HNSW do Chroma + FTS5, ambos locais |

O carregamento do modelo de embedding é preguiçoso. Modelos que o FastEmbed 0.8 não lista (ex.: `BAAI/bge-m3`) são registrados a partir do catálogo em `config/embedding_models.py`. O primeiro uso baixa o ONNX do Hugging Face. `nix status` não carrega o modelo. `prepare_native_imports` roda na subida do `Runtime`, antes do Chroma e do FastEmbed: no Windows o Controle de Aplicativo pode bloquear `mmh3` e `cygrpc` (comum no Python 3.14 do checkout; o binário publicado é 3.12 e, se ainda bloquear, o `doctor` aponta o cache `onefile-<versão>`). O Nix desbloqueia o import (o Chroma local usa `RustBindingsAPI` e não precisa de gRPC). A dependência é `chromadb>=1.5,<1.6` porque o stub OTEL cobre o grafo de import da série 1.5.

## 13. Decisões arquiteturais

| # | Decisão | Alternativas consideradas | Motivo |
| --- | --- | --- | --- |
| AD-01 | Embeddings locais (`bge-m3` via FastEmbed) | `text-embedding-3-small` da OpenAI | Custo zero na indexação e reindexação; multilíngue e sem GPU |
| AD-02 | ChromaDB persistente | FAISS, LanceDB, Qdrant local, pgvector | Persistência e deleção por `file_id` nativas; filtros de pasta/tag na camada de recuperação |
| AD-03 | SQLite como estado do índice | Arquivo JSON de manifesto | Transacional, consultável, e traz FTS5 de graça para a busca léxica |
| AD-04 | Sem LLM no Nix | LangGraph + OpenAI no processo | O raciocínio fica no cliente MCP (Cursor, Claude Code, Copilot); o Nix só entrega ferramentas |
| AD-05 | Sincronização manual, sem watcher | `watchdog` observando o vault | Requisito de controle do usuário; evita processo em background e reindexações em rajada durante edição |
| AD-06 | Registry único de ferramentas | Implementações separadas para CLI e MCP | Elimina divergência de comportamento e duplicação de regras de segurança |
| AD-07 | Busca híbrida desde a fundação | Somente densa | Notas pessoais são cheias de nomes próprios e siglas que o embedding dilui |
| AD-08 | Artefatos de índice na pasta do aplicativo (`.nix/`), fora do vault | `.nix/` dentro do vault | Evita poluir a sincronização do Obsidian; o estado acompanha o aplicativo |
| AD-09 | MCP somente stdio | HTTP como transporte do MCP | O cliente inicia o processo; não há porta no protocolo. A interface local é outro processo, só enquanto `nix ui` está aberto |
| AD-10 | Binário único Nuitka (`install.*` baixa o artefato da release; checkout de desenvolvimento segue com `scripts/bootstrap.py`) | PyInstaller onefile, venv com o Python do sistema | Um arquivo por plataforma, sem runtime na máquina do usuário. A partida seguinte reusa o cache `{CACHE_DIR}/nix/onefile-{VERSION}`. O modo arquivo único do PyInstaller descompacta a cada processo e atrasa o stdio do MCP |
| AD-11 | Configuração em `settings.db` na pasta da instalação | TOML, JSON, índice SQLite | A config não se perde ao apagar `.nix/data`. Histórico e desfazer ficam no mesmo arquivo. O ambiente continua ganhando do valor gravado |
| AD-12 | Interface com Starlette, HTMX e Pico.css vendidos no pacote | Streamlit, NiceGUI, app com Node | Sem build e sem chamada remota. Starlette e Uvicorn já vêm com o SDK MCP |

## 14. Evolução prevista

- Conjunto de avaliação `eval/` (harness e perguntas; ainda não está no repositório).
- Reordenação com cross-encoder ligada por padrão e outras melhorias de qualidade.
- Registro documentado para mais clientes MCP (Claude Code, Copilot) além do exemplo do Cursor.
