# Nix

<p align="center">
  <img src="nix.jpeg" alt="Nix, a Lulu da Pomerânia que inspirou o nome do projeto" width="280">
</p>

<p align="center">
  <a href="https://github.com/paulocesaaars/nix/releases/latest"><img src="https://img.shields.io/github/v/release/paulocesaaars/nix?label=download&style=for-the-badge" alt="Baixar a última versão"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B%20%2F%203.14-blue?style=for-the-badge" alt="Python 3.11+ / 3.14"></a>
</p>

Servidor [MCP](https://modelcontextprotocol.io/) que expõe um vault do Obsidian a agentes de desenvolvimento (Cursor, Claude Code, Copilot). Busca híbrida, leitura e escrita nas notas — com embeddings e banco vetorial **locais e gratuitos**. O raciocínio fica no cliente; o Nix só entrega ferramentas.

Transporte: **MCP stdio**. Sem subcomando, `nix` inicia o servidor.

## Por que usar

- O agente do editor **encontra ideias**, não só palavras: busca semântica + léxica no vault.
- **Cria e atualiza notas** no formato do Obsidian, sem sair do Cursor.
- Tudo roda **na sua máquina**. Nenhum trecho do vault vai para API de embedding.
- Você controla quando o índice muda: não há watcher em segundo plano.

## Requisitos

- Windows amd64, Linux (amd64 ou arm64) ou macOS Apple Silicon
- Um vault do Obsidian (notas `.md`)
- ~2,3 GB livres na primeira sincronização (download do modelo `BAAI/bge-m3`)

Não é preciso instalar Python. O arquivo baixado já traz o runtime.

## Instalação

O instalador baixa o binário da [última release](https://github.com/paulocesaaars/nix/releases/latest), confere o SHA-256, grava `NIX_HOME` e dispara `nix init` se ainda não houver `nix.toml`.

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/paulocesaaars/nix/main/install.ps1 | iex
# ou, se já souber o vault, baixe o script e rode:
# .\install.ps1 --vault "C:/Obsidian/MeuVault"
```

**Linux e macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/paulocesaaars/nix/main/install.sh | sh
# com o vault já conhecido:
# curl -fsSL .../install.sh -o install.sh && sh install.sh --vault "$HOME/Vault"
```

No Windows use barras `/` no caminho do vault (`C:/Obsidian/MeuVault`). Barra invertida quebra o TOML.

A pasta da instalação é `%LOCALAPPDATA%\nix` no Windows, `~/Library/Application Support/nix` no macOS e `~/.local/share/nix` no Linux (ou o `NIX_HOME` que já existir). O binário fica em `{NIX_HOME}/bin`. Windows arm64 e macOS Intel não têm binário: o instalador diz isso e para.

<p>
  <img src="nix.png" alt="Nix, a Lulu da Pomerânia que inspirou o nome do projeto" width="280">
</p>

Depois registre o servidor no editor — veja [Registro no cliente MCP](#registro-no-cliente-mcp). O instalador grava `NIX_HOME` e coloca `nix` no PATH. Abra um novo terminal e rode `nix doctor` / `nix sync`. Se o registro automático falhar, veja [INSTALL.md](INSTALL.md#registrar-nix_home-e-o-path-à-mão). Se o gerenciador Nix (NixOS) já estiver no PATH, o instalador avisa: este `nix` passa a ter prioridade.

`NIX_VERSION=1.2.3` (com ou sem o `v`) instala uma release específica.

### A partir do código (desenvolvedor)

Quem altera o Nix usa um `venv`. O `install.ps1` da raiz baixa o binário publicado; não instala este checkout.

```bash
python -m venv .venv
# Windows (Git Bash): source .venv/Scripts/activate
# Linux/macOS:        source .venv/bin/activate

pip install -r requirements-dev.txt
pip install -e .
python -m nix init                # ou: python -m nix init --vault "C:/Obsidian/MeuVault"
```

O mesmo fluxo, com registro de PATH, é `python scripts/bootstrap.py`. Para desfazer o checkout: `python scripts/uninstall.py`.

`python -m nix` vale depois de ativar o venv. O Cursor não herda o `PATH` do terminal — no MCP de desenvolvimento aponte `command` para o Python do `.venv` com `-P -m nix`, ou para o shim `bin/nix` deste checkout.

## Desinstalar

`uninstall.bat`, `.\uninstall.ps1` ou `sh uninstall.sh`. Confirme com `s`, ou passe `--yes`. Isso remove o PATH, o binário, o índice (`.nix/`) e o `nix.toml` da pasta `NIX_HOME`. O vault **não** é apagado. `--keep-data` preserva a configuração e o índice. Detalhes: [INSTALL.md](INSTALL.md#desinstalação).

## Registro no cliente MCP

O cliente inicia o processo. Recarregue os servidores MCP depois de salvar.

`command` deve apontar para o binário **dentro da pasta da instalação** (`NIX_HOME`), não para o nome `nix` no PATH. O editor aberto pelo Dock ou pelo menu **não** herda o PATH do terminal (`spawn nix ENOENT`). O caminho aparece em `nix doctor`, na linha `comando nix:`.

**Cursor** — `.cursor/mcp.json` no workspace:

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

No Windows a IDE lê a variável de usuário `NIX_HOME`. Também vale o caminho absoluto, por exemplo `C:/Users/voce/AppData/Local/nix/bin/nix.exe`.

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

Troque pelo caminho da linha `comando nix:` do `nix doctor`. No Linux a pasta padrão é `~/.local/share/nix/bin/nix`. `"command": "nix"` falha na IDE. `${env:NIX_HOME}` em geral **não** expande: o app não lê `.zshrc` / `.bashrc`.

O mesmo padrão vale para Claude Code e Copilot. stdout é do protocolo MCP: logs só em `.nix/logs/nix.log` na pasta do Nix.

## Primeiros passos

Depois do `init` (o instalador já dispara isso), **abra um novo terminal** e rode:

```bash
nix doctor
nix sync
nix status
```

Se `nix` não for encontrado, o terminal ainda tem o PATH antigo: feche-o e abra outro.

## Registrar NIX_HOME e o PATH à mão

Se o instalador não gravar as variáveis, o passo a passo está só no [INSTALL.md](INSTALL.md#registrar-nix_home-e-o-path-à-mão). Grave o que faltou e abra um **terminal novo**.

O primeiro `sync` (ou qualquer operação que embede) baixa o modelo configurado. O padrão `BAAI/bge-m3` pesa ~2,3 GB. **Não precisa de GPU**, mas na CPU a primeira carga e cada nota podem levar muitos minutos — a barra só avança ao terminar o arquivo. Em máquina fraca com português, use `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (~220 MB) e rode `nix sync --full`. O `nix init` lista a comparação.

Notas novas sem pasta no caminho vão para `vault.default_new_note_folder` (padrão `Inbox`).

## Indexação

Esta é a regra central:

> Alterações feitas **fora** do Nix (Obsidian, editor) **não** são indexadas sozinhas. Alterações feitas pelas ferramentas MCP atualizam o índice na mesma operação.

Depois de editar no Obsidian, rode `nix sync` ou peça `sync_index` ao agente. Se a vetorização de uma escrita falhar, o arquivo permanece no vault (fonte da verdade) e um `nix sync` corrige o índice.

## CLI

| Comando | Função |
| --- | --- |
| `nix` | Inicia o servidor MCP stdio |
| `nix init [--vault PATH] [--embedding-model NOME] [--force]` | Cria a configuração; pergunta vault e modelo de embedding |
| `nix sync [--full] [--dry-run] [--json]` | Sincroniza o índice (nunca automático) |
| `nix status [--json]` | Notas, chunks, último sync e defasagem |
| `nix doctor [--json]` | Diagnóstico de ambiente, config e índice |

## Ferramentas MCP

Doze ferramentas, definidas em `src/nix/core/tools/registry.py`. Notas também aparecem como recurso `nix://note/{+rel_path}`.

| Ferramenta | Uso |
| --- | --- |
| `search_notes` | Busca híbrida (semântica + léxica), com filtros de pasta, tags e datas |
| `read_note` | Lê a nota inteira |
| `list_notes` | Lista notas indexadas (pasta, tag) |
| `get_linked_notes` | Navega wikilinks (`outgoing`, `incoming` ou `both`) |
| `create_note` | Cria nota e indexa na hora (write-through) |
| `append_to_note` | Anexa conteúdo e reindexa |
| `update_note` | `replace` exige `confirm=true`; `patch` anexa |
| `delete_note` | Remove nota e índice; exige `confirm=true` |
| `sync_index` | Sincronização manual (`full`, `dry_run`) |
| `index_status` | Contagens, último sync e defasagem |
| `vault_insights` | Órfãs, duplicatas, sugestão de links ou resumo |
| `remember` | Grava fato duradouro em `vault.longterm_folder` |

## Configuração

Arquivo (primeiro encontrado): `$NIX_CONFIG` (se definido, só ele) → `nix.toml` em `NIX_HOME` (no binário, a pasta de dados da plataforma se a variável não existir). No checkout de desenvolvimento, o `nix.toml` do repositório vem antes. Caminhos relativos resolvem contra o diretório do TOML. Variáveis `NIX_SECAO__CAMPO` sobrescrevem o arquivo (ex.: `NIX_VAULT__PATH`). `nix init` grava nesse mesmo caminho.

Pontos úteis do TOML gerado pelo `init`:

| Chave | Padrão | Função |
| --- | --- | --- |
| `vault.path` | — | Pasta raiz do Obsidian |
| `vault.exclude` | `.obsidian`, `.trash`, `Templates`, `Privado` | Pastas ignoradas |
| `vault.default_new_note_folder` | `Inbox` | Destino de notas sem pasta no caminho |
| `vault.longterm_folder` | `Nix/Memória` | Destino da ferramenta `remember` |
| `index.data_dir` | `.nix/data` | SQLite + Chroma (na pasta do app, fora do vault) |
| `logging.file` | `.nix/logs/nix.log` | Logs; consultas só entram se `log_prompts = true` |

## Publicar uma versão

Uma release no GitHub é criada automaticamente quando uma tag `vX.Y.Z` chega no remoto. O workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) confere a versão, roda `ruff` e `mypy`, compila um binário por plataforma (Windows amd64, Linux amd64, Linux arm64, macOS arm64) e publica os arquivos com `checksums.txt` em [Releases](https://github.com/paulocesaaars/nix/releases).

1. Atualize `[project].version` em `pyproject.toml` (ex.: `1.0.2`). A tag **precisa** bater com esse valor — senão o job falha.
2. Faça o commit e o push na branch principal.
3. Crie e envie a tag (o `v` no prefixo é obrigatório):

```bash
git tag v1.1.3
git push origin v1.1.3
```

4. Acompanhe o workflow **Release** em Actions. Em caso de sucesso, a release traz um binário por plataforma e o `checksums.txt`.

Para republicar os artefatos de uma tag que já existe, dispare o workflow à mão: Actions → Release → Run workflow, e informe a tag (ex.: `v1.0.2`).

## Documentação

- [PRD.md](PRD.md) — produto, requisitos e regras de negócio
- [TDD.md](TDD.md) — especificações técnicas: componentes, indexação, recuperação e MCP stdio
