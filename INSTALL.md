# Instalar o Nix

Servidor [MCP](https://modelcontextprotocol.io/) que expõe um vault do Obsidian a agentes de desenvolvimento (Cursor, Claude Code, Copilot). Busca híbrida, leitura e escrita nas notas — com embeddings e banco vetorial **locais e gratuitos**. O raciocínio fica no cliente; o Nix só entrega ferramentas.

Estas instruções são para **usar** o Nix no seu projeto. Se você vai desenvolver o código, veja o [README.md](README.md).

## Requisitos

- Python 3.11+ no `PATH`
- Um vault do Obsidian (notas `.md`)
- ~2,3 GB livres na primeira sincronização (download do modelo `BAAI/bge-m3`)

## Instalação

O instalador cria `.venv`, instala o pacote e dispara `nix init` (pergunta o caminho do vault, ou aceite `--vault`).

1. Baixe a [última release](https://github.com/paulocesaaars/nix/releases/latest) (`nix-x.y.z.zip`).
2. Extraia **na raiz do workspace** e renomeie a pasta para `nix` (o zip vem como `nix-1.0.0/`).
3. Rode o instalador **dentro dessa pasta**:

```bat
cd nix
setup.bat
:: ou, se já souber o vault:
setup.bat --vault "C:/Users/voce/Vault"
```

```bash
cd nix
chmod +x setup.sh
./setup.sh
# ou: ./setup.sh --vault "$HOME/Vault"
```

No Windows use barras `/` no caminho do vault (`C:/Users/voce/Vault`). Barra invertida quebra o TOML.

## Comandos depois da instalação

Os comandos da CLI não dependem de você estar *dentro* da pasta `nix`. Na raiz do workspace:

```bat
nix.cmd doctor
nix.cmd sync
```

```bash
./nix doctor
./nix sync
```

## Registro no cliente MCP

O cliente inicia o processo. A IDE **não** herda o `PATH` do terminal: o comando `nix` do venv não é encontrado e a conexão fecha (`'nix' não é reconhecido`).

Aponte para o Python do ambiente virtual e passe `-P` (Python 3.11+), para o diretório `nix/` do workspace não ser importado no lugar do pacote. Recarregue os servidores MCP depois de salvar.

**Cursor** — `.cursor/mcp.json` no workspace:

```json
{
  "mcpServers": {
    "nix": {
      "command": "${workspaceFolder}/nix/.venv/Scripts/python.exe",
      "args": ["-P", "-m", "nix"]
    }
  }
}
```

| Sistema | `command` |
| --- | --- |
| Windows | `${workspaceFolder}/nix/.venv/Scripts/python.exe` |
| Linux / macOS | `${workspaceFolder}/nix/.venv/bin/python` |

Em qualquer um dos casos os `args` são `["-P", "-m", "nix"]`. O wrapper (`nix.cmd` no Windows, `./nix` no Unix) também inicia o servidor e resolve o `.venv` pela própria pasta — útil se você preferir não apontar o `python.exe`.

O mesmo padrão vale para Claude Code e Copilot. stdout é do protocolo MCP: logs só em `~/.nix/logs/nix.log`.

## Primeiros passos

Depois do `init` (o instalador já dispara isso):

O primeiro `sync` (ou qualquer operação que embede) baixa o modelo `BAAI/bge-m3` (~2,3 GB) do Hugging Face. Nas seguintes, só o que mudou é reprocessado.

Notas novas sem pasta no caminho vão para `vault.default_new_note_folder` (padrão `Inbox`).

## Indexação

Esta é a regra central:

> Alterações feitas **fora** do Nix (Obsidian, editor) **não** são indexadas sozinhas. Alterações feitas pelas ferramentas MCP atualizam o índice na mesma operação.

Depois de editar no Obsidian, rode `nix sync` ou peça `sync_index` ao agente. Se a vetorização de uma escrita falhar, o arquivo permanece no vault (fonte da verdade) e um `nix sync` corrige o índice.

## CLI

| Comando | Função |
| --- | --- |
| `nix` | Inicia o servidor MCP stdio |
| `nix init [--vault PATH] [--force]` | Cria a configuração e grava o caminho do vault |
| `nix sync [--full] [--dry-run] [--json]` | Sincroniza o índice (nunca automático) |
| `nix status [--json]` | Notas, chunks, último sync e defasagem |
| `nix doctor [--json]` | Diagnóstico de ambiente, config e índice |

## Ferramentas MCP

Doze ferramentas. Notas também aparecem como recurso `nix://note/{+rel_path}`.

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

Arquivo (primeiro encontrado): `$NIX_CONFIG` → `nix.toml` no diretório atual e nos pais → `nix.toml` na pasta do Nix e no projeto que a contém → `~/.nix/config.toml`. Variáveis `NIX_SECAO__CAMPO` sobrescrevem o arquivo (ex.: `NIX_VAULT__PATH`).

Pontos úteis do TOML gerado pelo `init`:

| Chave | Padrão | Função |
| --- | --- | --- |
| `vault.path` | — | Pasta raiz do Obsidian |
| `vault.exclude` | `.obsidian`, `.trash`, `Templates`, `Privado` | Pastas ignoradas |
| `vault.default_new_note_folder` | `Inbox` | Destino de notas sem pasta no caminho |
| `vault.longterm_folder` | `Nix/Memória` | Destino da ferramenta `remember` |
| `index.data_dir` | `~/.nix/data` | SQLite + Chroma (fora do vault) |
| `logging.file` | `~/.nix/logs/nix.log` | Logs; consultas só entram se `log_prompts = true` |
