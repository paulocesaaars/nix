# Nix

<p align="center">
  <img src="nix.jpeg" alt="Nix, a Lulu da Pomerânia que inspirou o nome do projeto" width="280">
</p>

<p align="center">
  <a href="https://github.com/paulocesaaars/nix/releases/latest"><img src="https://img.shields.io/github/v/release/paulocesaaars/nix?label=download&style=for-the-badge" alt="Baixar a última versão"></a>
</p>

Servidor MCP que expõe um vault do Obsidian a agentes de desenvolvimento (Cursor, Claude Code, Copilot). Busca híbrida, leitura e escrita nas notas — com embeddings e banco vetorial **locais e gratuitos**. O raciocínio fica no cliente; o Nix só entrega ferramentas.

Transporte: **MCP stdio**. Sem subcomando, `nix` inicia o servidor.

## Requisitos

- Python 3.11+
- Um vault do Obsidian (notas `.md`)

## Instalação

Baixe `nix-X.Y.Z.zip` na [última release](https://github.com/paulocesaaars/nix/releases/latest) e extraia (ou clone o repositório). Todas as versões ficam em [releases](https://github.com/paulocesaaars/nix/releases). O arquivo `.sha256` ao lado do zip permite conferir o download: `sha256sum -c nix-X.Y.Z.zip.sha256`.

O caminho mais curto: rode o instalador na raiz do repositório. Ele cria `.venv`, instala os pacotes e inicia `nix init`.

```bat
setup.bat
:: ou, se já souber o vault:
setup.bat --vault "C:/Users/voce/Vault"
```

```bash
chmod +x setup.sh
./setup.sh
# ou: ./setup.sh --vault "$HOME/Vault"
```

Instalação manual:

```bash
python -m venv .venv
# Windows (Git Bash):
source .venv/Scripts/activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements-dev.txt
pip install -e .
nix init                          # pergunta o caminho do vault e cria ~/.nix/config.toml
# ou: nix init --vault "C:/Users/voce/Vault"
```

O comando `nix` e `python -m nix` são equivalentes **depois** de ativar o venv. O Cursor não herda o `PATH` do terminal — no MCP use o Python do `.venv` (veja [Registro no cliente MCP](#registro-no-cliente-mcp)).

## Primeiros passos

Depois do `init` (o instalador já dispara isso):

```bash
nix doctor
nix sync                          # indexa o vault (incremental)
nix status
```

O primeiro `nix sync` (ou qualquer operação que embede) baixa o modelo `BAAI/bge-m3` (~2,3 GB) do Hugging Face.

Arquivo de configuração (primeiro encontrado): `$NIX_CONFIG` → `./nix.toml` → `~/.nix/config.toml`. Variáveis `NIX_SECAO__CAMPO` sobrescrevem o arquivo.

Notas novas sem pasta no caminho vão para `vault.default_new_note_folder` (padrão `Inbox`).

## Comandos

| Comando | Função |
| --- | --- |
| `nix` | Inicia o servidor MCP stdio |
| `nix init [--vault PATH] [--force]` | Cria o arquivo de configuração e grava o caminho do vault |
| `nix sync [--full] [--dry-run] [--json]` | Sincroniza o índice (nunca automático) |
| `nix status [--json]` | Notas, chunks, último sync e defasagem |
| `nix doctor [--json]` | Diagnóstico de ambiente, config e índice |

Alterações feitas **fora** do Nix (Obsidian, editor) **não** são indexadas sozinhas — rode `nix sync` ou peça `sync_index` ao agente. Escritas feitas pelas ferramentas atualizam o índice na mesma operação; se a vetorização falhar, o arquivo permanece no vault e um `nix sync` corrige o índice.

## Ferramentas MCP

Doze ferramentas, definidas em `src/nix/core/tools/registry.py`:

| Ferramenta | Uso |
| --- | --- |
| `search_notes` | Busca híbrida (semântica + léxica), com filtros de pasta, tags e datas |
| `read_note` | Lê a nota inteira |
| `list_notes` | Lista notas indexadas (pasta, tag); inclui tags |
| `get_linked_notes` | Navega wikilinks (`outgoing`, `incoming` ou `both`) |
| `create_note` | Cria nota e indexa na hora (write-through) |
| `append_to_note` | Anexa conteúdo e reindexa |
| `update_note` | `replace` exige `confirm=true`; `patch` anexa |
| `delete_note` | Remove nota e índice; exige `confirm=true` |
| `sync_index` | Sincronização manual (`full`, `dry_run`) |
| `index_status` | Contagens, último sync e defasagem |
| `vault_insights` | Órfãs, duplicatas, sugestão de links ou resumo |
| `remember` | Grava fato duradouro em `vault.longterm_folder` |

Notas também aparecem como recurso `nix://note/{+rel_path}`.

## Registro no cliente MCP

O cliente inicia o processo. O Cursor **não** herda o `PATH` do terminal: o comando `nix` do venv não é encontrado e a conexão fecha (`'nix' não é reconhecido`).

Aponte para o Python do ambiente virtual do projeto. No Windows, `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "nix": {
      "command": "C:/Git/nix/.venv/Scripts/python.exe",
      "args": ["-m", "nix"]
    }
  }
}
```

Ajuste `command` para o `python.exe` (Windows) ou `.venv/bin/python` (Linux/macOS) da sua instalação. Recarregue os servidores MCP no Cursor.

stdout é do protocolo: logs só em `~/.nix/logs/nix.log`. Consultas e argumentos só entram no log se `logging.log_prompts = true`.

## Avaliação de recuperação

O conjunto `eval/` ainda não está neste repositório. O alvo de acurácia top-5 é ≥ 90% ([PRD.md](PRD.md), seção 9). Quando o harness existir:

```bash
python eval/run.py --questions eval/questions.json
```

- [PRD.md](PRD.md) — produto, requisitos e regras de negócio
- [ARCHITECTURE.md](ARCHITECTURE.md) — componentes, indexação, recuperação e MCP stdio

git add .github .gitattributes scripts/check_version.py README.md
git commit -m "Adiciona workflow de release com pacote zip"
git push
git tag v1.0.0 && git push origin v1.0.0