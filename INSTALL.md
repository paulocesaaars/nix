# Instalar o Nix

Servidor [MCP](https://modelcontextprotocol.io/) que expõe um vault do Obsidian a agentes de desenvolvimento (Cursor, Claude Code, Copilot). Busca híbrida, leitura e escrita nas notas — com embeddings e banco vetorial **locais e gratuitos**. O raciocínio fica no cliente; o Nix só entrega ferramentas.

Estas instruções são para **usar** o Nix no seu projeto. Se você vai desenvolver o código, veja o [README.md](README.md).

## Requisitos

- Windows amd64, Linux (amd64 ou arm64) ou macOS Apple Silicon
- Um vault do Obsidian (notas `.md`)
- ~2,3 GB livres na primeira sincronização (download do modelo `BAAI/bge-m3`)

Não é preciso instalar Python.

## Instalação

O instalador baixa o binário da [última release](https://github.com/paulocesaaars/nix/releases/latest), confere o SHA-256 e dispara `nix init` se ainda não houver `nix.toml` (pergunta o caminho do vault, ou aceite `--vault`).

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

No Windows use barras `/` no caminho do vault (`C:/Obsidian/MeuVault`). Barra invertida quebra o TOML.

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

O desinstalador remove `NIX_HOME` e o comando `nix` do PATH, apaga o binário e, por padrão, também `.nix/` (índice, backups, logs) e `nix.toml`. **O vault do Obsidian não é alterado.** Não precisa da pasta do repositório.

Confirme com `s`. Em script, passe `--yes`.

```bat
uninstall.bat
:: ou, sem pergunta:
uninstall.bat --yes
:: para manter nix.toml e o índice:
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

O mesmo padrão vale para Claude Code e Copilot. stdout é do protocolo MCP: logs só em `.nix/logs/nix.log` na pasta do Nix.

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
| `nix init [--vault PATH] [--embedding-model NOME] [--force]` | Cria a configuração; pergunta vault e modelo de embedding |
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

Arquivo (primeiro encontrado): `$NIX_CONFIG` (se definido, só ele) → `nix.toml` em `NIX_HOME`. No binário, se a variável não existir, a pasta é a de dados da plataforma (`%LOCALAPPDATA%\nix`, `~/Library/Application Support/nix` ou `~/.local/share/nix`). No checkout de desenvolvimento, o `nix.toml` do repositório vem antes. Caminhos relativos resolvem contra o diretório do TOML. Variáveis `NIX_SECAO__CAMPO` sobrescrevem o arquivo (ex.: `NIX_VAULT__PATH`). `nix init` grava nesse mesmo caminho.

Pontos úteis do TOML gerado pelo `init`:

| Chave | Padrão | Função |
| --- | --- | --- |
| `vault.path` | — | Pasta raiz do Obsidian |
| `vault.exclude` | `.obsidian`, `.trash`, `Templates`, `Privado` | Pastas ignoradas |
| `vault.default_new_note_folder` | `Inbox` | Destino de notas sem pasta no caminho |
| `vault.longterm_folder` | `Nix/Memória` | Destino da ferramenta `remember` |
| `index.data_dir` | `.nix/data` | SQLite + Chroma (na pasta do app, fora do vault) |
| `logging.file` | `.nix/logs/nix.log` | Logs; consultas só entram se `log_prompts = true` |
