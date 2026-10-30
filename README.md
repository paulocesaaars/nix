# Nix

<p align="center">
  <img src="nix.jpeg" alt="Nix, a Lulu da Pomerânia que inspirou o nome do projeto" width="280">
</p>

<p align="center">
  <a href="https://github.com/paulocesaaars/nix/releases/latest"><img src="https://img.shields.io/github/v/release/paulocesaaars/nix?label=download&style=for-the-badge" alt="Baixar a última versão"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B%20%2F%203.14-blue?style=for-the-badge" alt="Python 3.11+ / 3.14"></a>
</p>

Servidor [MCP](https://modelcontextprotocol.io/) que expõe vaults do Obsidian a agentes de desenvolvimento (Cursor, Claude Code, Copilot, Devin CLI e Devin Desktop). Busca híbrida, leitura e escrita nas notas — com embeddings e banco vetorial **locais e gratuitos**. O raciocínio fica no cliente; o Nix só entrega ferramentas.

Transporte: **MCP stdio**. Sem subcomando, `nix` inicia o servidor.

## Por que usar

- O agente do editor **encontra ideias**, não só palavras: busca semântica + léxica no vault.
- **Cria e atualiza notas** no formato do Obsidian, sem sair do Cursor.
- Tudo roda **na sua máquina**. Nenhum trecho do vault vai para API de embedding.
- Você controla quando o índice muda: não há watcher em segundo plano.

## Requisitos

- Windows amd64, Linux (amd64 ou arm64) ou macOS Apple Silicon
- Um vault do Obsidian (notas `.md`)
- ~220 MB livres na primeira sincronização (modelo padrão `lulu`). O `spitz` (`BAAI/bge-m3`) pesa ~2,3 GB

Não é preciso instalar Python para o binário da release: o arquivo baixado já traz o runtime. Se a empresa bloqueia o `.exe`, o PowerShell e os links de download do instalador, baixe o zip do código na release e instale pelo Python no Git Bash, na seção [Quando o executável, o PowerShell e os links de download estão bloqueados](#quando-o-executável-o-powershell-e-os-links-de-download-estão-bloqueados).

## Instalação

O instalador baixa `nix` e `nix-hook` da [última release](https://github.com/paulocesaaars/nix/releases/latest), confere o SHA-256 de cada um, grava `NIX_HOME` e dispara `nix init` se ainda não houver `settings.db`. Os hooks de sessão chamam o `nix-hook`.

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

No Windows use barras `/` no caminho do vault (`C:/Obsidian/MeuVault`).

A pasta da instalação é `%LOCALAPPDATA%\nix` no Windows, `~/Library/Application Support/nix` no macOS e `~/.local/share/nix` no Linux (ou o `NIX_HOME` que já existir). Os binários ficam em `{NIX_HOME}/bin`. Windows arm64 e macOS Intel não têm binário: o instalador diz isso e para.

A primeira execução descompacta o binário num cache (`%LOCALAPPDATA%\nix\onefile-<versão>` no Windows, `~/Library/Caches/nix/onefile-<versão>` no macOS, `~/.cache/nix/onefile-<versão>` no Linux). O instalador já faz essa partida. As seguintes reutilizam o cache. O `nix-hook` fica ao lado de `nix`: o binário completo confere o CRC de todo o payload a cada partida e não cabe no orçamento de 300 ms do hook de sessão. O `nix hooks install` aponta os agentes para o `nix-hook`, cujo cache fica em `hook-<versão>` na mesma pasta.

<p>
  <img src="nix.png" alt="Nix, a Lulu da Pomerânia que inspirou o nome do projeto" width="280">
</p>

Depois registre o servidor no editor — veja [Registro no cliente MCP](#registro-no-cliente-mcp). O instalador grava `NIX_HOME` e coloca `nix` no PATH. Abra um novo terminal e rode `nix doctor` / `nix sync`. Se o registro automático falhar, veja [Registrar NIX_HOME e o PATH à mão](#registrar-nix_home-e-o-path-à-mão). Se o gerenciador Nix (NixOS) já estiver no PATH, o instalador avisa: este `nix` passa a ter prioridade.

`NIX_VERSION=1.2.3` (com ou sem o `v`) instala uma release específica.

### Quando o executável, o PowerShell e os links de download estão bloqueados

Algumas redes bloqueiam o `.exe`, a execução do PowerShell e o download que o `install.ps1` faz (`irm` do script e dos binários da release). O caminho é baixar o zip do código-fonte na [última release](https://github.com/paulocesaaars/nix/releases/latest) — o arquivo **Source code (zip)** — e usar a instalação por Python, a mesma base da seção [A partir do código (desenvolvedor)](#a-partir-do-código-desenvolvedor). Nenhum `nix.exe` entra na máquina.

Se o computador da empresa não abre o GitHub, baixe esse zip em outra máquina e copie o arquivo. Descompacte e entre na pasta (`nix-<versão>`). No Git Bash, com Python 3.11 ou mais novo:

```bash
python scripts/bootstrap.py --vault "C:/Obsidian/MeuVault"
```

O `bootstrap.py` cria o `.venv`, instala os pacotes de `requirements.txt`, grava `NIX_HOME`, coloca `nix` no PATH e roda `nix init`. O zip da release traz esse script e o `requirements.txt`. O `requirements-dev.txt` fica só no clone completo do Git: a lista de comandos da seção do desenvolvedor que usa esse arquivo vale para quem alterou o código a partir do clone. O `pip` precisa alcançar o PyPI. Sem `--vault`, o `init` pergunta o caminho. No Windows, use barras `/` no caminho do vault.

Se `python` não existir nesse bash, use `py` ou `python3`. Com Git liberado, o mesmo script roda depois de um clone:

```bash
git clone https://github.com/paulocesaaars/nix.git
cd nix
python scripts/bootstrap.py --vault "C:/Obsidian/MeuVault"
```

Abra um terminal novo e rode `nix doctor`. No terminal que já está aberto:

```bash
source bin/env.sh
```

No MCP não há `nix.exe`. Aponte `command` para o Python do ambiente e passe o módulo em `args`. Troque a pasta se o zip ou o clone ficou em outro lugar:

```json
{
  "mcpServers": {
    "nix": {
      "command": "C:/Git/nix/.venv/Scripts/python.exe",
      "args": ["-P", "-m", "nix"]
    }
  }
}
```

Os hooks dessa instalação chamam `python -m nix hook`. O `nix-hook.exe` da release não entra.

Para desfazer essa instalação, na pasta descompactada ou no clone: `python scripts/uninstall.py`. O vault do Obsidian não é alterado. `--yes` pula a pergunta; `--keep-data` preserva `settings.db` e o índice. O binário instalado por `install.ps1` ou `install.sh` sai pelos comandos da seção [Desinstalar](#desinstalar).

A primeira sincronização ainda baixa o modelo de embedding (cerca de 220 MB, o `lulu`).

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

### Skills de agente (desenvolvedor)

As skills de desenvolvimento (implementar SDD pelo fluxo inteiro, especificar, criar testes, revisar código, atualizar a documentação, commitar, guardrails, gerar uma skill, iniciar o projeto e publicar a release) ficam versionadas neste repositório, em `.claude/skills/` (Claude Code e Cursor) e `.agents/skills/` (Cursor, Copilot e Devin). O `skills-lock.json` registra a origem das que estão sincronizadas.

## Sessões

Opcional e por repositório. Os hooks gravam a conversa daquele projeto; a skill `sessoes-nix` ensina o agente a consultar o que ficou gravado. Essa skill vem com a Nix e não entra no repositório de skills de desenvolvimento.

Rode estes comandos **na pasta do projeto** em que a conversa acontece. Um hook ou uma skill na pasta da conta (configuração global do Claude ou do Devin) não registra o projeto: a Nix descarta o evento e não há sessão para retomar. A conversa anterior a esse `install` também não fica gravada.

```bash
nix config set sessions.enabled true
nix hooks install --agent claude --agent devin --yes
nix skills install --agent claude --agent devin --yes
```

`sessions.enabled` vem desligado. Com ele desligado os hooks ainda podem gravar, mas `nix session` e as ferramentas `list_sessions`, `read_session` e `session_handoff` ficam indisponíveis. Depois de ligar, reinicie o cliente MCP.

Os agentes aceitos em `--agent` são `cursor`, `claude`, `copilot`, `devin` e `devin-desktop`. Repita a opção para vários. Sem `--agent`, cada comando pergunta um a um e só escreve depois de confirmar. `--yes` pula a confirmação. `--dry-run` só mostra o que seria escrito. `--project PASTA` escolhe outro repositório sem sair da pasta atual.

O hook fica no repositório, nunca na pasta da conta:

| Agente | Arquivo do hook | Pasta da skill |
| --- | --- | --- |
| Claude Code | `.claude/settings.local.json` | `.claude/skills/sessoes-nix/` |
| Cursor | `.cursor/hooks.json` | `.agents/skills/sessoes-nix/` |
| Copilot | `.github/hooks/nix.json` | `.agents/skills/sessoes-nix/` |
| Devin CLI | `.devin/hooks.v1.json` | `.agents/skills/sessoes-nix/` |
| Devin Desktop | `.devin/hooks.json` | `.agents/skills/sessoes-nix/` |

Dois agentes que leem a mesma pasta de skill geram uma cópia só. `nix hooks status` e `nix skills status` mostram o que está ativo. `remove` apaga só o que a Nix marcou.

### Continuar uma sessão em outro agente

Encerre a sessão no agente de origem (no Claude Code, saia da conversa naquele repositório). O fim da sessão deixa um handoff pendente. Há no máximo um por projeto, e ele é entregue uma única vez.

```bash
nix session handoff
```

Se não houver pendente, crie a partir da sessão mais recente:

```bash
nix session handoff --create
```

`--cancel` descarta o pendente. `--agent NOME`, junto com `--create`, tira da origem a sessão que esse agente acabou de abrir.

No **Devin CLI**, abra o mesmo repositório. O início da sessão recebe o handoff. Peça para continuar.

No **Devin Desktop** não há evento de início nem de fim de sessão, e o stdout do hook não entra na conversa. Com o MCP da Nix ligado, peça para continuar. A skill chama `session_handoff` com `agent` igual a `devin-desktop` e `accept=true`. `accept=false` só mostra, sem consumir.

O Devin na nuvem não alcança a Nix desta máquina. O MCP precisa estar no Devin CLI ou no Devin Desktop local.

`nix session list` mostra as sessões do projeto. `nix session show ID` lê uma. `nix session render` grava a nota no vault. Os detalhes de cada comando estão em [CLI](#cli).

## Desinstalar

O desinstalador remove `NIX_HOME` e o comando `nix` do PATH, apaga `nix` e `nix-hook`, o cache de extração (`onefile-*` e `hook-*`) e, por padrão, também `.nix/` (índice, backups, logs) e `settings.db`. Se a pasta da instalação ficar vazia, ela também sai. **O vault do Obsidian não é alterado.**

Confirme com `s`. Em script, passe `--yes`. `--keep-data` preserva `settings.db` e o índice.

### Nix instalado pelo PowerShell

Quem instalou com `install.ps1` desinstala sem a pasta do repositório. No PowerShell:

```powershell
irm https://raw.githubusercontent.com/paulocesaaars/nix/main/uninstall.ps1 -OutFile "$env:TEMP\uninstall-nix.ps1"
& "$env:TEMP\uninstall-nix.ps1"
```

Responda `s` em `Continuar? [s/N]`. O script também apaga o cache `onefile-*` e `hook-*`. Se `%LOCALAPPDATA%\nix` ficar vazia, a pasta sai. A linha que confirma o fim diz que a pasta foi apagada, ou que o que restava foi removido dela. Abra um terminal novo em seguida.

```powershell
& "$env:TEMP\uninstall-nix.ps1" --yes
# para manter settings.db e o índice:
& "$env:TEMP\uninstall-nix.ps1" --keep-data --yes
```

No Linux e no macOS, o script da release:

```bash
curl -fsSL https://raw.githubusercontent.com/paulocesaaars/nix/main/uninstall.sh | sh
# ou: curl -fsSL .../uninstall.sh -o uninstall.sh && sh uninstall.sh --yes
```

### Na pasta do repositório ou do zip

Na pasta do clone, ou na pasta descompactada do **Source code (zip)** — a instalação por `bootstrap.py`:

```bash
python scripts/uninstall.py
# ou: python scripts/uninstall.py --yes
# ou: python scripts/uninstall.py --keep-data --yes
```

Esse comando tira o `NIX_HOME` se ele apontar para essa pasta, apaga o `.venv` e, salvo `--keep-data`, também `.nix/` e `settings.db`. O código-fonte da pasta permanece.

Com os scripts da raiz do repositório:

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

Abra um **novo terminal** depois: o `nix` deste projeto deixa de valer. Se o registro permanente falhar, veja [Remover NIX_HOME e o PATH à mão](#remover-nix_home-e-o-path-à-mão). Remova também o servidor `nix` do `mcp.json` do editor.

O modelo de embedding pode permanecer no cache do Hugging Face (`BAAI/bge-m3` pesa ~2,3 GB). Esse cache é compartilhado com outros programas, e o desinstalador não o apaga. O servidor `nix` no `mcp.json` de cada projeto também fica: apague essa entrada no editor.

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

Na instalação por Python, sem `nix.exe`, use o interpretador do `.venv` como em [Quando o executável, o PowerShell e os links de download estão bloqueados](#quando-o-executável-o-powershell-e-os-links-de-download-estão-bloqueados).

## Primeiros passos

Depois do `init` (o instalador já dispara isso), **abra um novo terminal** e rode:

```bash
nix doctor
nix sync
nix status
```

Se `nix` não for encontrado, o terminal ainda tem o PATH antigo: feche-o e abra outro.

O primeiro `sync` (ou qualquer operação que embede) baixa o modelo configurado. O padrão é a `lulu` (~220 MB). O embedding roda na CPU; a barra só avança ao terminar o arquivo. O `spitz` (`BAAI/bge-m3`, ~2,3 GB) melhora a busca e cada nota pode levar minutos. Troque no `nix init` ou com `nix config set index.embedding_model spitz` e rode `nix sync --full`.

Notas novas sem pasta no caminho vão para `vault.default_new_note_folder` (padrão `Inbox`).

## Registrar NIX_HOME e o PATH à mão

O instalador tenta gravar `NIX_HOME` (pasta do Nix) e `{NIX_HOME}/bin` no PATH do usuário. Se isso falhar (permissão, política, registro bloqueado), a configuração do vault **continua**. Registre as variáveis você mesmo e **abra um terminal novo**.

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

## Indexação

Esta é a regra central:

> Alterações feitas **fora** do Nix (Obsidian, editor) **não** são indexadas sozinhas. Alterações feitas pelas ferramentas MCP atualizam o índice na mesma operação.

Depois de editar no Obsidian, rode `nix sync` ou peça `sync_index` ao agente. Se a vetorização de uma escrita falhar, o arquivo permanece no vault (fonte da verdade) e um `nix sync` corrige o índice.

## CLI

Estes são os comandos que você roda no terminal. `nix --help` lista os grupos. `nix COMANDO --help` mostra as opções daquele comando. Nada aqui indexa o vault sozinho: o índice muda com `nix sync` ou com uma escrita feita pelas ferramentas MCP.

| Comando | Quando usar |
| --- | --- |
| `nix` | O editor sobe o servidor MCP. No terminal, sem cliente, o processo espera o protocolo e encerra com Ctrl+C |
| `nix --version` | Mostra a versão e sai |
| `nix init [--name NOME] [--vault PATH] [--embedding-model NOME] [--force]` | Primeira configuração: grava o vault e o modelo |
| `nix vault list\|add\|rename\|remove\|default\|path\|set` | Até 5 vaults: cadastra, renomeia, remove, escolhe o padrão, troca a pasta e grava os ajustes daquele vault |
| `nix config list\|get\|set\|unset\|history\|undo` | Lê, grava e desfaz a configuração global da instalação |
| `nix sync [--full] [--dry-run] [--json] [--vault NOME]... [--all]` | Atualiza o índice depois de editar no Obsidian |
| `nix status [--json] [--vault NOME]... [--all]` | Vê se o índice está atrás do vault |
| `nix doctor [--json]` | Descobre por que o editor não acha o Nix ou o índice falhou |
| `nix ui [--no-browser] [--port N]` | As mesmas operações no navegador, sem agente |
| `nix session list\|show\|handoff\|render` | Lê sessões do repositório atual, cria ou cancela o handoff e grava a nota |
| `nix hooks install\|remove\|status [--agent A] [--yes] [--project PASTA]` | Liga, tira e consulta os hooks **deste** repositório |
| `nix skills install\|remove\|status [--agent A] [--yes] [--project PASTA]` | Copia, tira e consulta a skill `sessoes-nix` **deste** repositório |

### Servidor

`nix`, sem subcomando, é o processo que o cliente MCP inicia. Não use esse comando para configurar o vault. `nix --version` imprime a versão e termina.

### Primeira configuração

`nix init` grava o primeiro vault e o modelo de embedding no `settings.db`. O instalador já chama isso quando ainda não há configuração.

- `--vault CAMINHO` informa a pasta. Sem isso, o terminal pergunta.
- `--name NOME` batiza o primeiro vault. Sem a opção, o nome é `Default`. Vale só na criação. O vault seguinte entra com `nix vault add`.
- `--embedding-model NOME` escolhe o modelo (`lulu` ou `spitz`). Sem a opção, o terminal pergunta na criação.
- `--force` regrava a configuração do zero.

### Vaults

De 1 a 5 vaults na mesma instalação. Omitir o vault no `sync` e no `status` usa o padrão.

- `nix vault list` mostra nome, pasta e qual é o padrão. `--json` entrega a mesma lista em JSON.
- `nix vault add NOME CAMINHO` cadastra outro. Um nome no formato `AAAAMMDDTHHMMSS` é recusado.
- `nix vault rename ANTIGO NOVO` troca o nome. O índice e os backups ficam onde estão. Se a busca ficar vazia, rode `nix sync --full --vault NOVO`.
- `nix vault default NOME` escolhe o padrão. Remover o padrão é recusado até outro ocupar o lugar. O último vault não sai.
- `nix vault remove NOME` tira o cadastro. A pasta do Obsidian permanece.
- `nix vault path NOME CAMINHO` aponta o mesmo nome para outra pasta.
- `nix vault set NOME CAMPO VALOR` grava um ajuste daquele vault: `include`, `exclude`, `follow_symlinks` ou as pastas. Listas e objetos entram como JSON. Não mexe na configuração global.

Renomear, remover, `path` e `set` esperam se aquele vault estiver sincronizando.

Nas ferramentas MCP, omitir `vault` usa o padrão. Busca, listas, status e sync aceitam um nome, uma lista ou `"*"` (todos). Escrita aceita um nome só.

### Configuração global

Os campos ficam no `settings.db` da instalação (`NIX_HOME`; no checkout por Python, a pasta do clone). `nix config set secao.chave valor` grava um campo. Listas e objetos entram como JSON.

- `nix config list` mostra os campos. `--json` muda o formato.
- `nix config get secao.chave` lê um.
- `nix config unset secao.chave` volta o campo ao padrão.
- `nix config history` mostra as alterações. `--limit N` corta a lista (padrão 20).
- `nix config undo` desfaz a última. `nix config undo ID` desfaz uma entrada do histórico.

Para as ferramentas de sessão: `nix config set sessions.enabled true`. Reinicie o cliente MCP em seguida.

Uma variável `NIX_SECAO__CAMPO` ganha do banco naquele campo e o trava no `nix config` e na interface. O cadastro dos vaults não usa essa variável.

### Índice

Editar no Obsidian não atualiza o índice. Rode `nix sync` quando quiser alinhar.

- Sem `--vault` e sem `--all`, vale o vault padrão.
- `--vault NOME` pode repetir. `--all` percorre todos, em sequência. Não combine os dois.
- `--full` reconstrói o índice inteiro. Use depois de trocar o modelo (`nix config set index.embedding_model spitz`).
- `--dry-run` só mostra o que mudaria.
- `--json` entrega o relatório em JSON. O mesmo vale para `nix status` e `nix doctor`.

`nix status` mostra notas, chunks, o último sync e se o vault está à frente do índice. `nix doctor` confere ambiente, configuração, o comando que o MCP deve chamar e o índice de cada vault. Comece por ele quando o editor não conecta.

### Interface

`nix ui` abre o navegador em `127.0.0.1` com status, sync, diagnóstico, busca, conexão dos clientes, sessões, tráfego MCP, backups, vaults e configuração. Exige o `nix init`. Encerra com Ctrl+C ou pelo botão Encerrar. `--no-browser` só imprime a URL. `--port N` fixa a porta.

### Sessões

Exige `sessions.enabled`. Rode na pasta do repositório, ou passe `--project PASTA`. O passo a passo para continuar uma conversa em outro agente está em [Sessões](#sessões).

- `nix session list` lista as sessões, da mais recente para a mais antiga. `--agent NOME` filtra. `--limit N` corta (padrão 20, no máximo 500). `--json` muda o formato.
- `nix session show ID` imprime uma sessão. O id pode ser o curto que aparece na lista.
- `nix session handoff` mostra o pendente. `--create` monta um a partir da sessão mais recente. `--cancel` descarta. `--agent NOME` com `--create` não usa a sessão que esse agente acabou de abrir.
- `nix session render` grava ou atualiza a nota no vault. Com um id, só aquela sessão. Sem id, as do projeto.

### Hooks e skills

Os dois grupos só escrevem no repositório. Não existe instalação global: a pasta da conta não registra o projeto.

`--agent` aceita `cursor`, `claude`, `copilot`, `devin` e `devin-desktop`, e pode repetir. `--yes` não pergunta. `--dry-run` não escreve. `--project PASTA` aponta outro repositório.

- `nix hooks install` ativa a captura. `remove` tira só o que a Nix marcou. `status` mostra o que está ativo.
- `nix skills install` copia a `sessoes-nix`. `remove` apaga só a pasta com a marca da Nix. `status` mostra as pastas.

Os arquivos e o handoff entre agentes estão em [Sessões](#sessões).

## Ferramentas MCP

Vinte ferramentas de vault e, com `sessions.enabled`, três de sessão. A definição fica em `src/nix/core/tools/registry.py`. Notas do vault padrão aparecem como recurso `nix://note/{+rel_path}`; um vault nomeado, como `nix://vault/{name}/note/{+rel_path}`.

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
| `list_sessions` | Sessões gravadas neste projeto, da mais recente para a mais antiga. Exige `sessions.enabled` |
| `read_session` | Eventos de uma sessão, do fim para o começo. O texto é histórico |
| `session_handoff` | Onde a sessão anterior parou e o caminho da nota. `accept=false` só mostra |

## Configuração

Fica em `settings.db`, na pasta do Nix (`NIX_HOME`; no checkout de desenvolvimento, a pasta do repositório). Caminhos relativos resolvem contra essa pasta. Variáveis `NIX_SECAO__CAMPO` ganham do banco nos campos globais (ex.: `NIX_INDEX__EMBEDDING_MODEL`) e o campo correspondente fica travado no `nix config` e na interface. O cadastro dos vaults não usa essa variável: nome, pasta, padrão e ajustes (`include`, `exclude`, pastas) ficam no `nix vault`. `nix vault set NOME CAMPO VALOR` grava um ajuste; listas e objetos entram como JSON. `nix vault path NOME CAMINHO` troca a pasta. `nix init` grava o primeiro vault e o modelo. `nix config set secao.chave valor` altera um campo global; listas e objetos entram como JSON. `nix config undo` restaura o valor anterior.

`nix ui` abre as mesmas operações no navegador, sem precisar de um LLM:

- **Operação:** status, sincronização com prévia e progresso (os botões ficam desligados até o job terminar, também se a página for recarregada) e diagnóstico.
- **Vault (somente leitura):** busca em um, em vários ou em todos, notas (com outline e trechos), tags e insights. O seletor "Vault ativo", no topo da barra lateral, usa `?vault=`; sem ele, vale o padrão.
- **Integração:** trechos prontos para conectar Cursor, Claude Code, VS Code, Devin CLI e Devin Desktop; sessões do projeto (lista, nota e handoff pendente); tráfego MCP, com as chamadas que os clientes fazem, gravadas em `.nix/traffic.db`.
- **Manutenção:** backups das escritas (comparação e download) e a restauração de um backup, a única escrita no vault feita pela interface, com confirmação; tela Vaults; formulário de configuração e histórico.

O comando exige o `nix init`, escuta só em `127.0.0.1` e encerra com Ctrl+C ou pelo botão Encerrar. `--no-browser` só imprime a URL; `--port` fixa a porta.

| Chave | Padrão | Função |
| --- | --- | --- |
| vault (cadastro) | nome `Default` no `nix init` | Pasta de cada vault, via `nix vault`. De 1 a 5, um padrão |
| exclusões do vault | `.obsidian`, `.trash`, `Templates`, `Privado` | Pastas ignoradas daquele vault. Mude com `nix vault set NOME exclude VALOR` |
| pasta de notas novas | `Inbox` | Destino de notas sem pasta no caminho |
| pasta do `remember` | `Nix/Memória` | Destino da ferramenta `remember` |
| `index.data_dir` | `.nix/data` | Base do índice; cada vault usa `.nix/data/<nome>` |
| `logging.file` | `.nix/logs/nix.log` | Logs; consultas só entram se `log_prompts` estiver ligado |

## Publicar uma versão

Uma release no GitHub é criada automaticamente quando uma tag `vX.Y.Z` chega no remoto. O workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) confere a versão, roda `ruff` e `mypy`, compila `nix` e `nix-hook` por plataforma (Windows amd64, Linux amd64, Linux arm64, macOS arm64) e publica os arquivos com `checksums.txt` em [Releases](https://github.com/paulocesaaars/nix/releases).

1. Atualize `[project].version` em `pyproject.toml` (ex.: `1.2.3`). A tag **precisa** bater com esse valor — senão o job falha.
2. Faça o commit e o push na branch principal.
3. Crie e envie a tag (o `v` no prefixo é obrigatório):

```bash
git tag v1.2.3
git push origin v1.2.3
```

4. Acompanhe o workflow **Release** em Actions. Em caso de sucesso, a release traz `nix` e `nix-hook` por plataforma e o `checksums.txt`. O zip de código-fonte da tag traz só o que instala e usa o Nix; skills de desenvolvimento, documentação e testes ficam de fora.

Para republicar os artefatos de uma tag que já existe, dispare o workflow à mão: Actions → Release → Run workflow, e informe a tag (ex.: `v1.2.3`).

## Documentação

- [PRD.md](PRD.md) — produto, requisitos e regras de negócio
- [TDD.md](TDD.md) — especificações técnicas: componentes, indexação, recuperação e MCP stdio
