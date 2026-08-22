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
setup.bat --vault "C:/Obsidian/MeuVault"
```

```powershell
cd nix
.\setup.ps1
# ou: .\setup.ps1 --vault "C:/Obsidian/MeuVault"
```

```bash
cd nix
chmod +x setup.sh
./setup.sh
# ou: ./setup.sh --vault "$HOME/Vault"
```

Depois de informar o vault, o instalador confirma que a **configuração foi concluída**. Abra um **novo terminal** e rode `nix doctor` / `nix sync` — o PATH já estará registrado (se o registro automático falhar, veja [Registrar NIX_HOME e o PATH à mão](#registrar-nix_home-e-o-path-à-mão)).

Quem já usa o gerenciador **Nix** (NixOS/Nixpkgs) vai ver um aviso: o comando `nix` deste projeto entra na frente do PATH. Use o caminho absoluto do outro `nix` se ainda precisar dele.

No Windows use barras `/` no caminho do vault (`C:/Obsidian/MeuVault`). Barra invertida quebra o TOML.

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

Se `nix` não for encontrado, o terminal ainda está com o PATH antigo: feche-o e abra outro. O `nix doctor` também imprime o comando de ativação manual (`bin/env.sh` / `env.cmd` / `env.ps1`).

## Desinstalação

O desinstalador remove `NIX_HOME` e o comando `nix` do PATH, apaga `.venv` e, por padrão, também `.nix/` (índice, backups, logs) e `nix.toml`. **O vault do Obsidian e o código-fonte desta pasta não são alterados.**

Rode **dentro da pasta do Nix** e confirme com `s`. Em script, passe `--yes`.

```bat
cd nix
uninstall.bat
:: ou, sem pergunta:
uninstall.bat --yes
:: para manter nix.toml e o índice:
uninstall.bat --keep-data --yes
```

```powershell
cd nix
.\uninstall.ps1
# ou: .\uninstall.ps1 --yes
# ou: .\uninstall.ps1 --keep-data --yes
```

```bash
cd nix
chmod +x uninstall.sh
./uninstall.sh
# ou: ./uninstall.sh --yes
# ou: ./uninstall.sh --keep-data --yes
```

Abra um **novo terminal** depois: o `nix` deste projeto deixa de valer. Se o registro permanente falhar, veja [Remover NIX_HOME e o PATH à mão](#remover-nix_home-e-o-path-à-mão). Remova também o servidor `nix` do `mcp.json` do editor.

O modelo `BAAI/bge-m3` (~2,3 GB) pode permanecer no cache do Hugging Face; o desinstalador não apaga esse cache (pode ser compartilhado com outros programas).

## Registrar NIX_HOME e o PATH à mão

O instalador tenta gravar `NIX_HOME` (pasta do Nix) e `{NIX_HOME}/bin` no PATH do usuário. Se isso falhar (permissão, política, registro bloqueado), a configuração do vault **continua**; registre as variáveis você mesmo e **abra um terminal novo**.

Use a pasta real da instalação no lugar de `C:\Git\nix` / `/c/Git/nix`.

### Windows (interface)

1. `Win+R`, rode `sysdm.cpl` → **Avançado** → **Variáveis de Ambiente**.
2. Em **Variáveis do usuário**, **Novo**:
   - Nome: `NIX_HOME`
   - Valor: pasta do Nix, por exemplo `C:\Git\nix`
3. Selecione **Path** (usuário) → **Editar** → **Novo** → `%NIX_HOME%\bin`
4. Confirme com **OK** em todas as janelas.

### Windows (PowerShell, permanente)

```powershell
$nixHome = "C:\Git\nix"   # pasta do Nix
[Environment]::SetEnvironmentVariable("NIX_HOME", $nixHome, "User")
$bin = Join-Path $nixHome "bin"
$p = [Environment]::GetEnvironmentVariable("Path", "User")
if ($p -notlike "*$bin*") {
  [Environment]::SetEnvironmentVariable("Path", "$p;$bin", "User")
}
```

### Linux, macOS e Git Bash

Acrescente ao `~/.bashrc` (e ao `~/.profile` se o terminal for de login):

```bash
export NIX_HOME="/c/Git/nix"   # Linux/macOS: $HOME/nix ou o caminho da extração
export PATH="$NIX_HOME/bin:$PATH"
```

Depois: `source ~/.bashrc` ou abra um terminal novo.

### Só nesta sessão (não grava)

```bat
call C:\Git\nix\bin\env.cmd
```

```bash
source /c/Git/nix/bin/env.sh
```

```powershell
. C:\Git\nix\bin\env.ps1
```

## Remover NIX_HOME e o PATH à mão

Se o desinstalador não desfizer as variáveis, apague o que o instalador gravou e **abra um terminal novo**. O vault continua intacto.

Use a pasta real da instalação no lugar de `C:\Git\nix` / `/c/Git/nix`.

### Windows (interface)

1. `Win+R`, rode `sysdm.cpl` → **Avançado** → **Variáveis de Ambiente**.
2. Em **Variáveis do usuário**, selecione **NIX_HOME** → **Excluir** (só se o valor for a pasta deste Nix).
3. Selecione **Path** (usuário) → **Editar** → remova `%NIX_HOME%\bin` (e o caminho absoluto `...\nix\bin`, se existir).
4. Confirme com **OK** em todas as janelas.

### Windows (PowerShell, permanente)

```powershell
$nixHome = "C:\Git\nix"   # pasta do Nix
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

O cliente inicia o processo. A IDE **não** herda o `PATH` do terminal: o comando `nix` do venv não é encontrado e a conexão fecha (`'nix' não é reconhecido`).

Aponte para o Python do ambiente virtual e passe `-P` (Python 3.11+), para o diretório `nix/` do workspace não ser importado no lugar do pacote. Recarregue os servidores MCP depois de salvar.

**Cursor** — `.cursor/mcp.json` no workspace:

```json
{
  "mcpServers": {
    "nix": {
      "command": "${env:NIX_HOME}/bin/nix.cmd"
    }
  }
}
```

| Sistema | `command` |
| --- | --- |
| Windows | `${workspaceFolder}/nix/.venv/Scripts/python.exe` |
| Linux / macOS | `${workspaceFolder}/nix/.venv/bin/python` |

Em qualquer um dos casos os `args` são `["-P", "-m", "nix"]`. Não use o comando `nix` do PATH no `mcp.json`: a IDE **não** herda o PATH do terminal.

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

Arquivo (primeiro encontrado): `$NIX_CONFIG` (se definido, só ele) → `nix.toml` na pasta do Nix (`$NIX_HOME` ou o checkout) → `nix.toml` no diretório atual e nos pais (último recurso). Caminhos relativos resolvem contra o diretório do TOML. Variáveis `NIX_SECAO__CAMPO` sobrescrevem o arquivo (ex.: `NIX_VAULT__PATH`). `nix init` grava nesse mesmo caminho.

Pontos úteis do TOML gerado pelo `init`:

| Chave | Padrão | Função |
| --- | --- | --- |
| `vault.path` | — | Pasta raiz do Obsidian |
| `vault.exclude` | `.obsidian`, `.trash`, `Templates`, `Privado` | Pastas ignoradas |
| `vault.default_new_note_folder` | `Inbox` | Destino de notas sem pasta no caminho |
| `vault.longterm_folder` | `Nix/Memória` | Destino da ferramenta `remember` |
| `index.data_dir` | `.nix/data` | SQLite + Chroma (na pasta do app, fora do vault) |
| `logging.file` | `.nix/logs/nix.log` | Logs; consultas só entram se `log_prompts = true` |
