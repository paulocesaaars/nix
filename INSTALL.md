# Instalar o Nix

Servidor [MCP](https://modelcontextprotocol.io/) que expõe vaults do Obsidian a agentes de desenvolvimento (Cursor, Claude Code, Copilot e o Devin CLI). Busca híbrida, leitura e escrita nas notas — com embeddings e banco vetorial **locais e gratuitos**. O raciocínio fica no cliente; o Nix só entrega ferramentas.

Estas instruções são para **usar** o Nix no seu projeto. Se você vai desenvolver o código, veja o [README.md](README.md).

## Requisitos

- Windows amd64, Linux (amd64 ou arm64) ou macOS Apple Silicon
- Um vault do Obsidian (notas `.md`)
- ~2,3 GB livres na primeira sincronização (download do modelo `BAAI/bge-m3`)

Não é preciso instalar Python.

## Instalação

O instalador baixa o binário da [última release](https://github.com/paulocesaaars/nix/releases/latest), confere o SHA-256 e dispara `nix init` se ainda não houver `settings.db` (pergunta o caminho do vault, ou aceite `--vault`).

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/paulocesaaars/nix/main/install.ps1 | iex
```

Com o vault já conhecido, salve o script e rode `.\install.ps1 --vault "C:/Obsidian/MeuVault"`. `install.bat` faz o mesmo.

**Linux e macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/paulocesaaars/nix/main/install.sh | sh
```

Com o vault já conhecido: `sh install.sh --vault "$HOME/Vault"`.

A pasta da instalação:

| Sistema | `NIX_HOME` |
| --- | --- |
| Windows | `%LOCALAPPDATA%\nix` (ex.: `C:\Users\voce\AppData\Local\nix`) |
| macOS | `~/Library/Application Support/nix` |
| Linux | `~/.local/share/nix` (ou `$XDG_DATA_HOME/nix`) |

Se `NIX_HOME` já existir, o instalador usa essa pasta e só troca o binário em `{NIX_HOME}/bin`. Windows arm64 e macOS Intel não têm binário publicado: o instalador explica e para. `NIX_VERSION=1.2.3` (com ou sem `v`) escolhe a release.

Depois de informar o vault, o instalador confirma que a **configuração foi concluída**. Abra um **novo terminal** e rode `nix doctor` / `nix sync` — o PATH já estará registrado (se o registro automático falhar, veja [Registrar NIX_HOME e o PATH à mão](#registrar-nix_home-e-o-path-à-mão)).

Quem já usa o gerenciador **Nix** (NixOS/Nixpkgs) vai ver um aviso: o comando `nix` deste projeto entra na frente do PATH. Use o caminho absoluto do outro `nix` se ainda precisar dele.

No Windows use barras `/` no caminho do vault (`C:/Obsidian/MeuVault`).

A primeira execução descompacta o binário num cache (`%LOCALAPPDATA%\nix\onefile-<versão>` no Windows, `~/Library/Caches/nix/onefile-<versão>` no macOS, `~/.cache/nix/onefile-<versão>` no Linux). O instalador já faz essa partida. As seguintes reutilizam o cache.

## Comandos depois da instalação

O instalador grava `NIX_HOME` e coloca `{NIX_HOME}/bin` no PATH. **Num terminal novo**, em qualquer diretório:

```bat
nix doctor
nix sync
```

```bash
nix doctor
nix sync
```

Se `nix` não for encontrado, o terminal ainda está com o PATH antigo: feche-o e abra outro.

## Desinstalação

O desinstalador remove `NIX_HOME` e o comando `nix` do PATH, apaga o binário e, por padrão, também `.nix/` (índice, backups, logs) e `settings.db`. **O vault do Obsidian não é alterado.** Não precisa da pasta do repositório.

Confirme com `s`. Em script, passe `--yes`.

```bat
uninstall.bat
:: ou, sem pergunta:
uninstall.bat --yes
:: para manter settings.db e o índice:
uninstall.bat --keep-data --yes
```

```powershell
.\uninstall.ps1
# ou: .\uninstall.ps1 --yes
# ou: .\uninstall.ps1 --keep-data --yes
```

```bash
sh uninstall.sh
# ou: sh uninstall.sh --yes
# ou: sh uninstall.sh --keep-data --yes
```

Pelo raw, o mesmo script da release:

```powershell
irm https://raw.githubusercontent.com/paulocesaaars/nix/main/uninstall.ps1 | iex
```

```bash
curl -fsSL https://raw.githubusercontent.com/paulocesaaars/nix/main/uninstall.sh | sh
```

Abra um **novo terminal** depois: o `nix` deste projeto deixa de valer. Se o registro permanente falhar, veja [Remover NIX_HOME e o PATH à mão](#remover-nix_home-e-o-path-à-mão). Remova também o servidor `nix` do `mcp.json` do editor.

O modelo `BAAI/bge-m3` (~2,3 GB) pode permanecer no cache do Hugging Face; o desinstalador não apaga esse cache (pode ser compartilhado com outros programas). O cache de extração do binário (`onefile-<versão>`) também fica; apague essa pasta se quiser o espaço de volta.

## Registrar NIX_HOME e o PATH à mão

O instalador tenta gravar `NIX_HOME` (pasta do Nix) e `{NIX_HOME}/bin` no PATH do usuário. Se isso falhar (permissão, política, registro bloqueado), a configuração do vault **continua**; registre as variáveis você mesmo e **abra um terminal novo**.

Use a pasta real da instalação no lugar dos exemplos.

### Windows (interface)

1. `Win+R`, rode `sysdm.cpl` → **Avançado** → **Variáveis de Ambiente**.
2. Em **Variáveis do usuário**, **Novo**:
   - Nome: `NIX_HOME`
   - Valor: pasta do Nix, por exemplo `C:\Users\voce\AppData\Local\nix`
3. Selecione **Path** (usuário) → **Editar** → **Novo** → `%NIX_HOME%\bin`
4. Confirme com **OK** em todas as janelas.

### Windows (PowerShell, permanente)

```powershell
$nixHome = "$env:LOCALAPPDATA\nix"
[Environment]::SetEnvironmentVariable("NIX_HOME", $nixHome, "User")
$expand = "%NIX_HOME%\bin"
$p = [Environment]::GetEnvironmentVariable("Path", "User")
if ($p -notlike "*$expand*") {
  [Environment]::SetEnvironmentVariable("Path", "$p;$expand", "User")
}
```

### Linux, macOS e Git Bash

Acrescente ao `~/.bashrc` (e ao `~/.profile` se o terminal for de login). No macOS o caminho é `$HOME/Library/Application Support/nix`; no Linux, `$HOME/.local/share/nix`.

```bash
# >>> nix >>>
export NIX_HOME="$HOME/.local/share/nix"
case ":$PATH:" in *":$NIX_HOME/bin:"*) ;; *) export PATH="$NIX_HOME/bin:$PATH" ;; esac
# <<< nix <<<
```

Depois: `source ~/.bashrc` ou abra um terminal novo.

### Só nesta sessão (não grava)

```powershell
$env:NIX_HOME = "$env:LOCALAPPDATA\nix"
$env:Path = "$env:NIX_HOME\bin;$env:Path"
```

```bash
export NIX_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/nix"
export PATH="$NIX_HOME/bin:$PATH"
```

## Remover NIX_HOME e o PATH à mão

Se o desinstalador não desfizer as variáveis, apague o que o instalador gravou e **abra um terminal novo**. O vault continua intacto.

Use a pasta real da instalação no lugar de `%LOCALAPPDATA%\nix`.

### Windows (interface)

1. `Win+R`, rode `sysdm.cpl` → **Avançado** → **Variáveis de Ambiente**.
2. Em **Variáveis do usuário**, selecione **NIX_HOME** → **Excluir** (só se o valor for a pasta deste Nix).
3. Selecione **Path** (usuário) → **Editar** → remova `%NIX_HOME%\bin` (e o caminho absoluto `...\nix\bin`, se existir).
4. Confirme com **OK** em todas as janelas.

### Windows (PowerShell, permanente)

```powershell
$nixHome = "$env:LOCALAPPDATA\nix"
$stored = [Environment]::GetEnvironmentVariable("NIX_HOME", "User")
if ($stored -and ($stored -ieq $nixHome)) {
  [Environment]::SetEnvironmentVariable("NIX_HOME", $null, "User")
}
$bin = Join-Path $nixHome "bin"
$p = [Environment]::GetEnvironmentVariable("Path", "User")
if ($p) {
  $kept = $p.Split(";") | Where-Object {
    $t = $_.Trim().Trim('"')
    $t -and $t -ne "%NIX_HOME%\bin" -and $t -ne $bin
  }
  [Environment]::SetEnvironmentVariable("Path", ($kept -join ";"), "User")
}
```

### Linux, macOS e Git Bash

Apague o bloco entre `# >>> nix >>>` e `# <<< nix <<<` em `~/.bashrc`, `~/.zshrc`, `~/.bash_profile` e `~/.profile` (só os arquivos que existirem), se `NIX_HOME` nesse bloco for a pasta desta instalação.

Depois: `source ~/.bashrc` ou abra um terminal novo.

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

O mesmo padrão vale para Claude Code, Copilot e o Devin CLI (`devin mcp add`). O Devin na nuvem não alcança o nix desta máquina. stdout é do protocolo MCP: logs só em `.nix/logs/nix.log` na pasta do Nix.

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
| `nix init [--name NOME] [--vault PATH] [--embedding-model NOME] [--force]` | Grava o primeiro vault e o modelo no `settings.db`. Sem `--name`, o nome é `Default` |
| `nix vault list\|add\|rename\|remove\|default\|path\|set` | Cadastra até 5 vaults, renomeia, remove, escolhe o padrão, troca a pasta e grava os ajustes daquele vault |
| `nix config list\|get\|set\|unset\|history\|undo` | Lê, grava e desfaz a configuração global |
| `nix sync [--full] [--dry-run] [--json] [--vault NOME]... [--all]` | Sincroniza o índice (nunca automático) |
| `nix status [--json] [--vault NOME]... [--all]` | Notas, chunks, último sync e defasagem |
| `nix doctor [--json]` | Diagnóstico de ambiente, config e índice de cada vault |
| `nix ui [--no-browser] [--port N]` | Abre a interface local (status, sync, diagnóstico, vaults, configuração, histórico) |

De 1 a 5 vaults no mesmo Nix. Sem `--vault` e sem `--all`, `nix sync` e `nix status` usam o padrão. `--vault` pode repetir; `--all` percorre todos, em sequência — não combine os dois. Outro vault entra com `nix vault add NOME CAMINHO`. `nix vault rename` não move o índice nem os backups; se a busca ficar vazia, rode `nix sync --full --vault NOME`.

## Ferramentas MCP

Vinte ferramentas. Notas do vault padrão aparecem como recurso `nix://note/{+rel_path}`; um vault nomeado, como `nix://vault/{name}/note/{+rel_path}`.

| Ferramenta | Uso |
| --- | --- |
| `search_notes` | Busca híbrida (semântica + léxica), com filtros de pasta, tags e datas |
| `read_note` | Lê a nota inteira. Em notas longas, prefira o outline e a leitura por linhas |
| `get_note_outline` | Título, chaves do frontmatter, total de linhas e headings |
| `read_note_lines` | Intervalo de linhas do arquivo ou um heading (até 400 linhas) |
| `list_notes` | Lista notas indexadas (pasta, tag) |
| `list_all_tags` | Tags indexadas com contagem; alimenta o filtro `tag` |
| `get_linked_notes` | Navega wikilinks (`outgoing`, `incoming` ou `both`) |
| `create_note` | Cria nota e indexa na hora (write-through) |
| `append_to_note` | Anexa conteúdo e reindexa |
| `update_note` | `replace` exige `confirm=true`; `patch` anexa; `prepend` insere após o YAML |
| `update_frontmatter` | Altera chaves de topo e preserva o restante do YAML |
| `manage_tags` | Adiciona ou remove tags do frontmatter; não mexe nas tags do corpo |
| `move_note` | Move uma nota `.md` e reescreve os links que apontam para ela |
| `move_file` | Move anexo (PDF, imagem etc.); notas `.md` ficam com `move_note` |
| `delete_note` | Remove nota e índice; exige `confirm=true` |
| `sync_index` | Sincronização manual (`full`, `dry_run`) |
| `index_status` | Contagens, último sync e defasagem, por vault |
| `vault_insights` | Órfãs, duplicatas, sugestão de links ou resumo |
| `remember` | Grava fato duradouro em `longterm_folder` do vault |
| `list_vaults` | Nome, caminho, padrão e se o índice daquele vault está desatualizado |

## Configuração

Fica em `settings.db`, na pasta do Nix. Caminhos relativos resolvem contra essa pasta. Variáveis `NIX_SECAO__CAMPO` ganham do banco nos campos globais (ex.: `NIX_INDEX__EMBEDDING_MODEL`). O cadastro dos vaults não usa essa variável. `nix init` grava o primeiro vault e o modelo. O mesmo ajuste global pode ser feito com `nix config` ou com `nix ui`.

| Chave | Padrão | Função |
| --- | --- | --- |
| vault (cadastro) | nome `Default` no `nix init` | Pasta de cada vault, via `nix vault`. De 1 a 5, um padrão |
| exclusões do vault | `.obsidian`, `.trash`, `Templates`, `Privado` | Pastas ignoradas daquele vault. Mude com `nix vault set NOME exclude VALOR` |
| pasta de notas novas | `Inbox` | Destino de notas sem pasta no caminho |
| pasta do `remember` | `Nix/Memória` | Destino da ferramenta `remember` |
| `index.data_dir` | `.nix/data` | Base do índice; cada vault usa `.nix/data/<nome>` |
| `logging.file` | `.nix/logs/nix.log` | Logs; consultas só entram se `log_prompts` estiver ligado |
