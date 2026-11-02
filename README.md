# Nix

<p align="center">
  <img src="nix.jpeg" alt="Nix, a Lulu da Pomerânia que inspirou o nome do projeto" width="280">
</p>

<p align="center">
  <a href="https://github.com/paulocesaaars/nix/releases/latest"><img src="https://img.shields.io/github/v/release/paulocesaaars/nix?label=download&style=for-the-badge" alt="Baixar a última versão"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B%20%2F%203.14-blue?style=for-the-badge" alt="Python 3.11+ / 3.14"></a>
</p>

<p align="center">
  <a href="https://paulocesaaars.github.io/nix/">https://paulocesaaars.github.io/nix/</a>
</p>

Servidor [MCP](https://modelcontextprotocol.io/) que expõe wikis em Markdown a agentes de desenvolvimento (Cursor, VS Code, Claude Code e Codex). Busca híbrida, leitura e escrita nas notas — com embeddings e banco vetorial **locais e gratuitos**. O raciocínio fica no cliente; o Nix só entrega ferramentas. O Mega Brain, desligado por padrão, guarda memória entre agentes na wiki que você escolher.

Transporte: **MCP stdio**. No terminal, `nix` sem subcomando abre a interface. O cliente MCP, sem terminal, continua recebendo o servidor.

## Por que usar

- O agente do editor **encontra ideias**, não só palavras: busca semântica + léxica no vault.
- **Cria e atualiza notas** em Markdown, sem sair do Cursor.
- Tudo roda **na sua máquina**. Nenhum trecho do vault vai para API de embedding.
- Você controla quando o índice muda: não há watcher em segundo plano.

## Requisitos

- Windows amd64, Linux (amd64 ou arm64) ou macOS Apple Silicon
- Uma pasta de notas Markdown (`.md`)
- ~220 MB livres na primeira sincronização (modelo padrão `lulu`). O `spitz` (`BAAI/bge-m3`) pesa ~2,3 GB

Não é preciso instalar Python para o binário da release: o arquivo baixado já traz o runtime. Se a empresa bloqueia o `.exe`, o PowerShell e os links de download do instalador, baixe o zip do código na release e instale pelo Python no Git Bash, na seção [Quando o executável, o PowerShell e os links de download estão bloqueados](#quando-o-executável-o-powershell-e-os-links-de-download-estão-bloqueados).

## Instalação

O instalador baixa `nix` e `nix-hook` da [última release](https://github.com/paulocesaaars/nix/releases/latest), confere o SHA-256 de cada um e grava `NIX_HOME`. A wiki é cadastrada depois, na interface. Os hooks de sessão chamam o `nix-hook`.

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/paulocesaaars/nix/main/install.ps1 | iex
```

**Linux e macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/paulocesaaars/nix/main/install.sh | sh
```

Ao terminar, execute `nix` para abrir a interface. Se o comando não funcionar, feche o terminal, abra outro e tente de novo.

A pasta da instalação é `%LOCALAPPDATA%\nix` no Windows, `~/Library/Application Support/nix` no macOS e `~/.local/share/nix` no Linux (ou o `NIX_HOME` que já existir). Os binários ficam em `{NIX_HOME}/bin`. Windows arm64 e macOS Intel não têm binário: o instalador diz isso e para.

A primeira execução descompacta o binário num cache (`%LOCALAPPDATA%\nix\onefile-<versão>` no Windows, `~/Library/Caches/nix/onefile-<versão>` no macOS, `~/.cache/nix/onefile-<versão>` no Linux). O instalador já faz essa partida. As seguintes reutilizam o cache. O `nix-hook` fica ao lado de `nix`: o binário completo confere o CRC de todo o payload a cada partida e não cabe no orçamento de 300 ms do hook de sessão. O `nix hooks install` aponta os agentes para o `nix-hook`, cujo cache fica em `hook-<versão>` na mesma pasta.

<p>
  <img src="src/nix/mcp/nix.png" alt="Nix, a Lulu da Pomerânia que inspirou o nome do projeto" width="280">
</p>

Depois registre o servidor no editor — veja [Registro no cliente MCP](#registro-no-cliente-mcp). O instalador grava `NIX_HOME` e coloca `nix` no PATH. Execute `nix` para abrir a interface. Se o comando não funcionar, feche o terminal, abra outro e tente de novo. Se o registro automático falhar, veja [Registrar NIX_HOME e o PATH à mão](#registrar-nix_home-e-o-path-à-mão). Se o gerenciador Nix (NixOS) já estiver no PATH, o instalador avisa: este `nix` passa a ter prioridade.

`NIX_VERSION=1.2.3` (com ou sem o `v`) instala uma release específica.

### Quando o executável, o PowerShell e os links de download estão bloqueados

Algumas redes bloqueiam o `.exe`, a execução do PowerShell e o download que o `install.ps1` faz (`irm` do script e dos binários da release). O caminho é baixar o zip do código-fonte na [última release](https://github.com/paulocesaaars/nix/releases/latest) — o arquivo **Source code (zip)** — e usar a instalação por Python, a mesma base da seção [A partir do código (desenvolvedor)](#a-partir-do-código-desenvolvedor). Nenhum `nix.exe` entra na máquina.

Se o computador da empresa não abre o GitHub, baixe esse zip em outra máquina e copie o arquivo. Descompacte e entre na pasta (`nix-<versão>`). No Git Bash, com Python 3.11 ou mais novo:

```bash
python scripts/bootstrap.py
```

O `bootstrap.py` cria o `.venv`, instala os pacotes de `requirements.txt`, grava `NIX_HOME` e coloca `nix` no PATH. A wiki é cadastrada depois, na interface. O zip da release traz esse script e o `requirements.txt`. O `requirements-dev.txt` fica só no clone completo do Git: a lista de comandos da seção do desenvolvedor que usa esse arquivo vale para quem alterou o código a partir do clone. O `pip` precisa alcançar o PyPI.

Se `python` não existir nesse bash, use `py` ou `python3`. Com Git liberado, o mesmo script roda depois de um clone:

```bash
git clone https://github.com/paulocesaaars/nix.git
cd nix
python scripts/bootstrap.py
```

Execute `nix` para abrir a interface. Se o comando não funcionar, feche o terminal, abra outro e tente de novo. No terminal que já está aberto:

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

Para desfazer essa instalação, na pasta descompactada ou no clone: `python scripts/uninstall.py`. A pasta da wiki não é alterada. `--yes` pula a pergunta; `--keep-data` preserva `settings.db` e o índice. O binário instalado por `install.ps1` ou `install.sh` sai pelos comandos da seção [Desinstalar](#desinstalar).

A primeira sincronização ainda baixa o modelo de embedding (cerca de 220 MB, o `lulu`).

### A partir do código (desenvolvedor)

Quem altera o Nix usa um `venv`. O `install.ps1` da raiz baixa o binário publicado; não instala este checkout.

```bash
python -m venv .venv
# Windows (Git Bash): source .venv/Scripts/activate
# Linux/macOS:        source .venv/bin/activate

pip install -r requirements-dev.txt
pip install -e .
python -m nix init                # ou: python -m nix init --wiki "C:/Notas/MinhaWiki"
```

O mesmo fluxo, com registro de PATH, é `python scripts/bootstrap.py`. Para desfazer o checkout: `python scripts/uninstall.py`.

`python -m nix` vale depois de ativar o venv. O Cursor não herda o `PATH` do terminal — no MCP de desenvolvimento aponte `command` para o Python do `.venv` com `-P -m nix`, ou para o shim `bin/nix` deste checkout.

### Skills de agente (desenvolvedor)

As skills de desenvolvimento (implementar SDD pelo fluxo inteiro, especificar, criar testes, revisar código, atualizar a documentação, commitar, guardrails, gerar uma skill, iniciar o projeto e publicar a release) ficam versionadas neste repositório, em `.claude/skills/` (Claude Code e Cursor) e `.agents/skills/` (Cursor e VS Code). O `skills-lock.json` registra a origem das que estão sincronizadas.

## Mega Brain

Desligado por padrão. Escolha a wiki das páginas e ligue:

```bash
nix brain enable --wiki Default
```

Essa wiki conta no limite de 100 e não pode ser removida enquanto o Mega Brain estiver ligado. A captura ainda exige um hook. Nenhum agente vem marcado. Há prévia, confirmação e backup antes de alterar um arquivo que já existe. O escopo global avisa que eventos de outros repositórios podem ser gravados.

```bash
nix brain hooks install --scope project
nix brain hooks install --scope global
```

O projeto é a raiz Git, ou a pasta se não houver repositório. Um `.nix.toml` pode definir `project`, `[capture] enabled` / `exclude` e `[profile] contribute` / `consume`. Toml ilegível desliga a captura.

| Agente | Arquivo do hook no projeto |
| --- | --- |
| Cursor | `.cursor/hooks.json` |
| VS Code | `.github/hooks/nix.json` |
| Claude Code | `.claude/settings.local.json` |
| Codex | `.codex/hooks.json` (só executa depois de confiar em `/hooks`) |

`nix brain hooks install --all` instala esses clientes, nesta ordem. O escopo global grava arquivo só quando o caminho está confirmado; nos demais, a captura fica parcial e nenhum JSON é inventado.

A página da sessão vai para `projects/<projeto>/sessions/` na wiki do Mega Brain. Ela só é gravada quando a sessão encerra e o `nix brain work` roda. O handoff e o recado ficam na base, não nessa página.

**Painel.** Cada cartão é um projeto: a raiz Git da pasta em que o agente trabalhou, ou a própria pasta se não houver repositório. O nome é o da pasta, ou o campo `project` do `.nix.toml`. O cartão aparece depois da primeira sessão capturada e mostra a quantidade de sessões, os agentes e a última atividade. Abrir o projeto mostra visão geral, agentes, tokens, sessões e conhecimento.

**Caixa de entrada.** É a fila de recados entre agentes, separada do handoff. `brain_message_send` grava o texto para um destinatário ou para qualquer um do projeto. O estado fica esperando. `brain_message_pop` entrega o mais antigo uma única vez e marca entregue. Cancelar tira da fila antes disso. A tela lista projeto, destinatário, texto e estado, inclusive os já entregues.

**Perfil.** São preferências que você escreveu nos pedidos, sem modelo de linguagem. A Nix procura “sempre use”, “prefiro”, “nunca use” e o equivalente em inglês, seguidos de uma palavra. Ferramentas conhecidas (`pnpm`, `pytest`, `ruff`, `docker`, `git` e outras) vão para `profile/tools/`. O resto vai para `profile/habits/`. A frase só entra quando o mesmo assunto apareceu em pelo menos dois projetos (`profile.min_projects`, padrão 2). A frase mais nova prevalece. `nix brain profile rebuild` reaprende; `forget` vira lápide e a passada seguinte não recria a entrada. No início da sessão o briefing inclui as frases ativas, salvo `[profile] consume = false` no `.nix.toml`.

`nix brain handoff create --text "..."` abre no máximo um handoff por projeto. `nix brain handoff accept --agent NOME` reivindica uma única vez. O início da sessão mostra o briefing como histórico, não como ordem.

`nix run claude` (ou outro agente) instala o hook e o MCP se faltarem. `--no-autowire` desliga isso. Para Claude Code e Codex, uma cópia só leitura do histórico anterior fica em `NIX_PREVIOUS_SESSION_HISTORY` e some quando o agente termina. Sem leitor, o comando segue com aviso.

`remember` continua gravando na wiki padrão e não faz parte do Mega Brain.

## Atualizar

Para trocar a versão que já está instalada, encerre `nix` e `nix-hook`, apague só esses dois binários e rode o instalador de novo. A wiki, o `settings.db` e a pasta `.nix` (índice e Mega Brain) ficam. O desinstalador da seção seguinte também apaga `settings.db` e `.nix`, salvo `--keep-data`.

**Windows (PowerShell):**

```powershell
Stop-Process -Name nix,nix-hook -Force -ErrorAction SilentlyContinue
$root = if ($env:NIX_HOME) { $env:NIX_HOME } else { Join-Path $env:LOCALAPPDATA "nix" }
Remove-Item -Force (Join-Path $root "bin\nix.exe"), (Join-Path $root "bin\nix-hook.exe")
irm https://raw.githubusercontent.com/paulocesaaars/nix/main/install.ps1 | iex
```

Feche e abra de novo o cliente MCP para ele carregar o binário novo.

**Linux e macOS:** o instalador substitui os arquivos. Encerre os processos e rode o instalador de novo:

```bash
pkill -x nix || true
pkill -x nix-hook || true
curl -fsSL https://raw.githubusercontent.com/paulocesaaars/nix/main/install.sh | sh
```

## Desinstalar

O desinstalador remove `NIX_HOME` e o comando `nix` do PATH, apaga `nix` e `nix-hook`, o cache de extração (`onefile-*` e `hook-*`) e, por padrão, também `.nix/` (índice, backups, logs) e `settings.db`. Se a pasta da instalação ficar vazia, ela também sai. **A pasta da wiki não é alterada.** Para só trocar a versão, use [Atualizar](#atualizar).

No Windows, se `nix.exe` ou `nix-hook.exe` estiver aberto, o desinstalador para antes de alterar o PATH e avisa que o arquivo está em uso. Feche o cliente que mantém o Nix aberto, ou encerre os processos, e rode de novo.

Confirme com `s`. Em script, passe `--yes`. `--keep-data` preserva `settings.db` e o índice.

### Nix instalado pelo PowerShell

Quem instalou com `install.ps1` desinstala sem a pasta do repositório. No PowerShell:

```powershell
irm https://raw.githubusercontent.com/paulocesaaars/nix/main/uninstall.ps1 -OutFile "$env:TEMP\uninstall-nix.ps1"
& "$env:TEMP\uninstall-nix.ps1"
```

Responda `s` em `Continuar? [s/N]`. Se a resposta for que o arquivo está em uso, encerre os processos e rode o mesmo desinstalador de novo:

```powershell
Stop-Process -Name nix,nix-hook -Force -ErrorAction SilentlyContinue
& "$env:TEMP\uninstall-nix.ps1"
```

O script também apaga o cache `onefile-*` e `hook-*`. Se `%LOCALAPPDATA%\nix` ficar vazia, a pasta sai. A linha que confirma o fim diz que a pasta foi apagada, ou que o que restava foi removido dela. Abra um terminal novo em seguida.

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

O mesmo padrão vale para Claude Code e o VS Code. O Codex usa `~/.codex/config.toml`. stdout é do protocolo MCP: logs só em `.nix/logs/nix.log` na pasta do Nix.

Na instalação por Python, sem `nix.exe`, use o interpretador do `.venv` como em [Quando o executável, o PowerShell e os links de download estão bloqueados](#quando-o-executável-o-powershell-e-os-links-de-download-estão-bloqueados).

## Primeiros passos

A instalação não roda `nix init`. No terminal, execute `nix` para abrir a interface. Se o comando não existir, feche o terminal, abra outro e tente de novo.

A primeira wiki entra na tela Wikis ou com `nix init`. A tela grava a pasta (a primeira vira o padrão). O `nix init` também escolhe o modelo e grava a marca que o servidor MCP e o comando `nix ui` exigem. Sem essa marca, o editor não conecta.

```bash
nix init
nix doctor
nix sync
nix status
```

O primeiro `sync` (ou qualquer operação que embede) baixa o modelo configurado. O padrão é a `lulu` (~220 MB). O embedding roda na CPU; a barra só avança ao terminar o arquivo. O `spitz` (`BAAI/bge-m3`, ~2,3 GB) melhora a busca e cada nota pode levar minutos. Troque no `nix init` ou com `nix config set index.embedding_model spitz` e rode `nix sync --full`.

Notas novas sem pasta no caminho vão para `default_new_note_folder` da wiki (padrão `Inbox`).

## Registrar NIX_HOME e o PATH à mão

O instalador tenta gravar `NIX_HOME` (pasta do Nix) e `{NIX_HOME}/bin` no PATH do usuário. Se isso falhar (permissão, política, registro bloqueado), a instalação dos binários **continua**. Registre as variáveis você mesmo e **abra um terminal novo**.

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

Se o desinstalador não desfizer as variáveis, apague o que o instalador gravou e **abra um terminal novo**. A pasta da wiki continua intacta.

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

> Alterações feitas **fora** do Nix, por exemplo, em um editor de texto, **não** são indexadas sozinhas. Alterações feitas pelas ferramentas MCP atualizam o índice na mesma operação.

Depois de editar as notas fora do Nix, rode `nix sync` ou peça `sync_index` ao agente. Se a vetorização de uma escrita falhar, o arquivo permanece na wiki (fonte da verdade) e um `nix sync` corrige o índice.

## CLI

Estes são os comandos que você roda no terminal. `nix --help` lista os grupos. `nix COMANDO --help` mostra as opções daquele comando. A wiki não entra no índice sozinha: o índice muda com `nix sync` ou com uma escrita feita pelas ferramentas MCP.

| Comando | O que faz |
| --- | --- |
| `nix` | No terminal, abre a interface. Sem terminal, o cliente MCP recebe o servidor |
| `nix --version` | Mostra a versão e sai |
| `nix init` | Cadastra a primeira wiki e o modelo de embedding. `--wiki` é a pasta; sem ela, o terminal pergunta. `--name` batiza a wiki (padrão `Default`). `--embedding-model` escolhe `lulu` ou `spitz`. `--force` regrava a configuração do zero, sem alterar as notas |
| `nix sync` | Atualiza o índice com o que mudou na wiki fora do Nix. `--full` reconstrói tudo. `--dry-run` só mostra. `--json` entrega o relatório. `--wiki NOME` escolhe uma ou várias. `--all` percorre todas |
| `nix status` | Mostra se o índice está atrás da wiki. Aceita `--json`, `--wiki` e `--all` |
| `nix doctor` | Confere ambiente, configuração, o comando que o MCP deve chamar e o índice. `--json` entrega o relatório inteiro |
| `nix ui` | Abre a interface no navegador. Exige o `nix init`. `--no-browser` só imprime a URL. `--port N` fixa a porta |
| `nix run AGENTE` | Sobe Cursor, VS Code (`copilot`), Claude Code (`claude`) ou Codex (`codex`). Instala o hook e o MCP do projeto se faltarem. `--no-autowire` não mexe nesses arquivos. `--project PASTA` escolhe o repositório. Para Claude Code e Codex, deixa o histórico nativo anterior em `NIX_PREVIOUS_SESSION_HISTORY` até o agente terminar |
| `nix wiki list` | Lista as wikis, a pasta e qual é a padrão. `--json` entrega a lista |
| `nix wiki add NOME CAMINHO` | Cadastra outra wiki. O limite é 100 |
| `nix wiki rename ANTIGO NOVO` | Troca o nome no cadastro. Não move a pasta nem o índice |
| `nix wiki remove NOME` | Tira a wiki do cadastro. Recusa a padrão e a última. A pasta de notas permanece |
| `nix wiki default NOME` | Escolhe a wiki usada quando o comando ou a ferramenta omite o nome |
| `nix wiki path NOME CAMINHO` | Aponta a wiki para outra pasta |
| `nix wiki set NOME CAMPO VALOR` | Grava um ajuste daquela wiki: `include`, `exclude`, `follow_symlinks`, `default_new_note_folder`, `default_frontmatter` ou `longterm_folder`. Listas e objetos entram como JSON |
| `nix config list` | Lista os campos globais, o valor que vale e a origem (padrão, banco ou ambiente). `--json` entrega a lista |
| `nix config get CAMPO` | Mostra o valor de um campo, no formato `secao.chave` |
| `nix config set CAMPO VALOR` | Grava o campo no `settings.db`. Uma variável `NIX_SECAO__CAMPO` continua ganhando do banco |
| `nix config unset CAMPO` | Apaga o valor gravado e volta ao padrão |
| `nix config history` | Lista as alterações recentes. `--limit N` muda a quantidade |
| `nix config undo [ID]` | Restaura o valor anterior. Sem id, desfaz a última |
| `nix brain enable --wiki NOME` | Liga o Mega Brain e escolhe a wiki das páginas de sessão. O estado fica gravado |
| `nix brain status` | Mostra se o Mega Brain está ligado, qual é a wiki e o estado dos hooks deste projeto |
| `nix brain hooks install` | Instala os hooks de captura. No terminal, pergunta o cliente e se o alcance é a conta ou só o repositório. Há prévia e confirmação. `--scope project\|global`, `--agent NOME`, `--all`, `--dry-run` e `--yes` dispensam as perguntas |
| `nix brain hooks remove --scope ESCOPO` | Tira os hooks da Nix daquele escopo. `--agent` escolhe o cliente |
| `nix brain hooks status` | Mostra, por agente, se o arquivo e o consentimento estão alinhados |
| `nix brain handoff create --text "..."` | Abre o handoff do projeto: onde a sessão parou. Só pode haver um aberto |
| `nix brain handoff list` | Lista os handoffs do projeto, do mais recente ao mais antigo |
| `nix brain handoff accept --agent NOME` | Reivindica o handoff aberto uma única vez e mostra o texto |
| `nix brain handoff cancel` | Cancela o handoff aberto |
| `nix brain profile list` | Lista as frases ativas do perfil |
| `nix brain profile rebuild` | Reaprende o perfil a partir dos pedidos gravados, sem modelo de linguagem |
| `nix brain profile apply` | Regrava na wiki as páginas das entradas ativas |
| `nix brain profile review` | Mostra assuntos que ainda não apareceram em projetos suficientes |
| `nix brain profile forget CAMINHO` | Esquece uma entrada. Ela não volta na próxima passada |

`nix hook`, `nix banner` e `nix brain work` existem para o processo interno. Não fazem parte do uso no terminal.

## Casos de uso

- **Abrir a interface.** Depois de instalar, execute `nix`. Se o comando não existir, feche o terminal, abra outro e tente de novo. `nix ui` abre a mesma interface quando a wiki já está cadastrada.
- **Cadastrar a primeira wiki.** `nix init` grava a pasta e o modelo. A instalação não faz mais essa pergunta.
- **Achar uma ideia no editor.** Com o MCP da Nix ligado, peça ao agente para buscar nas notas. Ele usa `search_notes` no índice da wiki.
- **Registrar uma nota sem sair do editor.** Peça ao agente para criar ou atualizar a nota. A escrita passa pelas ferramentas do MCP e o índice daquela nota é atualizado na hora.
- **Trazer para o índice o que você editou fora do Nix.** Rode `nix sync`. `--dry-run` mostra o que mudaria. `--full` reconstrói o índice, e é obrigatório depois de trocar o modelo de embedding.
- **Usar mais de uma wiki.** `nix wiki add Trabalho C:/Notas/Trabalho` cadastra a segunda. `nix wiki default Trabalho` passa a usá-la quando o nome é omitido. A busca pode pedir uma, várias ou todas.
- **Descobrir por que o editor não conecta.** `nix doctor` confere o comando, a configuração e o índice.
- **Guardar memória entre agentes.** `nix brain enable --wiki Default` liga o Mega Brain. `nix brain hooks install --scope global --all` faz Cursor, VS Code, Claude Code e Codex chamarem o Nix a cada evento da sessão. O VS Code não tem arquivo global: a captura dele fica parcial.
- **Continuar no Codex o que estava fazendo no Claude.** Os dois clientes precisam ter o MCP da Nix, o Mega Brain ligado e a mesma pasta do projeto. No Claude, peça para deixar registrado onde a sessão parou: ele chama `brain_handoff_create`. Abra o Codex e diga para continuar o que estava fazendo no Claude: ele chama `brain_handoff_accept` com o agente `codex` e, se precisar do resto, `brain_query` ou `brain_read_page`. Sem o MCP, o mesmo texto pode ser aberto e reivindicado no terminal com `nix brain handoff create` e `nix brain handoff accept --agent codex`. O hook, sozinho, só entrega no início da sessão um briefing com os últimos pedidos.
- **Deixar um recado para o outro agente.** Com o Mega Brain ligado, `brain_message_send` coloca uma mensagem na fila do projeto. O outro agente pega com `brain_message_pop`, uma única vez.
- **Ler o que o Mega Brain já guardou.** `brain_query` busca na wiki do Mega Brain e nas observações. `brain_recent_pages` lista as páginas de sessão. `brain_read_page` lê uma página pelo caminho. O texto encontrado é histórico.
- **Reaprender o perfil.** `nix brain profile rebuild` relê os pedidos gravados. `nix brain profile list` mostra as frases. `nix brain profile forget CAMINHO` esquece uma. `nix brain profile apply` regrava as páginas na wiki.
- **Corrigir uma configuração.** `nix config history` mostra a alteração. `nix config undo` volta o valor anterior.

### Servidor

No terminal, `nix` sem subcomando abre a interface. O cliente MCP inicia o mesmo comando sem terminal e recebe o servidor stdio. `nix --version` imprime a versão e termina.

### Primeira configuração

`nix init` grava a primeira wiki e o modelo de embedding no `settings.db`. A instalação não faz mais esse passo.

- `--wiki CAMINHO` informa a pasta. Sem isso, o terminal pergunta.
- `--name NOME` batiza a primeira wiki. Sem a opção, o nome é `Default`. Vale só na criação. A seguinte entra com `nix wiki add`.
- `--embedding-model NOME` escolhe o modelo (`lulu` ou `spitz`). Sem a opção, o terminal pergunta na criação.
- `--force` regrava a configuração do zero, sem alterar as notas.

### Wikis

De 1 a 100 wikis na mesma instalação. Omitir a wiki no `sync` e no `status` usa a padrão.

- `nix wiki list` mostra nome, pasta e qual é a padrão. `--json` entrega a mesma lista em JSON.
- `nix wiki add NOME CAMINHO` cadastra outra. Um nome no formato `AAAAMMDDTHHMMSS` é recusado.
- `nix wiki rename ANTIGO NOVO` troca o nome. O índice e os backups ficam onde estão. Se a busca ficar vazia, rode `nix sync --full --wiki NOVO`.
- `nix wiki default NOME` escolhe a padrão. Remover a padrão é recusado até outra ocupar o lugar. A última wiki não sai.
- `nix wiki remove NOME` tira o cadastro. A pasta das notas permanece. A wiki das páginas do Mega Brain também não sai enquanto ele estiver ligado.
- `nix wiki path NOME CAMINHO` aponta o mesmo nome para outra pasta.
- `nix wiki set NOME CAMPO VALOR` grava um ajuste daquela wiki: `include`, `exclude`, `follow_symlinks`, `default_new_note_folder`, `default_frontmatter` ou `longterm_folder`. Listas e objetos entram como JSON. Não mexe na configuração global.

Renomear, remover, `path` e `set` esperam se aquela wiki estiver sincronizando.

Nas ferramentas MCP, omitir `wiki` usa a padrão. Busca, listas, status e sync aceitam um nome, uma lista ou `"*"` (todas). Escrita aceita um nome só.

### Configuração global

Os campos ficam no `settings.db` da instalação (`NIX_HOME`; no checkout por Python, a pasta do clone). `nix config set secao.chave valor` grava um campo. Listas e objetos entram como JSON.

- `nix config list` mostra os campos. `--json` muda o formato.
- `nix config get secao.chave` lê um.
- `nix config unset secao.chave` volta o campo ao padrão.
- `nix config history` mostra as alterações. `--limit N` corta a lista (padrão 20).
- `nix config undo` desfaz a última. `nix config undo ID` desfaz uma entrada do histórico.

Para o Mega Brain: `nix brain enable --wiki NOME`. Reinicie o cliente MCP em seguida para as ferramentas `brain_*` aparecerem.

Uma variável `NIX_SECAO__CAMPO` ganha do banco naquele campo e o trava no `nix config` e na interface. O cadastro das wikis não usa essa variável.

### Índice

Editar notas fora do Nix não atualiza o índice. Rode `nix sync` quando quiser alinhar.

- Sem `--wiki` e sem `--all`, vale a wiki padrão.
- `--wiki NOME` pode repetir. `--all` percorre todas, em sequência. Não combine os dois.
- `--full` reconstrói o índice inteiro. Use depois de trocar o modelo (`nix config set index.embedding_model spitz`).
- `--dry-run` só mostra o que mudaria.
- `--json` entrega o relatório em JSON. O mesmo vale para `nix status` e `nix doctor`.

`nix status` mostra notas, chunks, o último sync e se a wiki está à frente do índice. `nix doctor` confere ambiente, configuração, o comando que o MCP deve chamar e o índice de cada wiki. Comece por ele quando o editor não conecta.

### Interface

`nix ui` abre o navegador em `127.0.0.1` com status, sync, diagnóstico, busca, Mega Brain (painel, caixa de entrada e perfil), conexão dos clientes, tráfego MCP, backups, wikis e configuração. Exige o `nix init`. Encerra com Ctrl+C ou pelo botão Encerrar. `--no-browser` só imprime a URL. `--port N` fixa a porta.

### Mega Brain

O passo a passo está em [Mega Brain](#mega-brain).

- `nix brain enable --wiki NOME` liga e escolhe a wiki. `status` mostra o estado.
- `nix brain hooks install --scope project|global` pede os agentes. `remove` e `status` usam o mesmo `--scope`.
- `nix brain handoff create --text "..."` abre o handoff. `list`, `accept --agent NOME` e `cancel` completam o ciclo.
- `nix brain profile rebuild` reaprende. `list`, `review`, `forget CAMINHO` e `apply` consultam e regravam.
- `nix run AGENTE` encaminha os argumentos seguintes ao executável. `--no-autowire` não mexe em hook nem MCP. `--project PASTA` escolhe o repositório.

## Ferramentas MCP

O agente não executa `nix` no terminal. Você pede em linguagem normal e ele chama uma ferramenta. As de wiki ficam sempre disponíveis. As `brain_*` só entram no MCP com o Mega Brain ligado; reinicie o cliente depois de `nix brain enable`. A definição está em `src/nix/core/tools/registry.py`. Notas da wiki padrão aparecem como recurso `nix://note/{+rel_path}`; uma wiki nomeada, como `nix://wiki/{name}/note/{+rel_path}`. Os nomes atuais de lista e de qualidade são `list_wikis` e `wiki_insights`.

| No terminal | O que você diz ao agente | Ferramenta |
| --- | --- | --- |
| `nix sync` | Sincroniza o índice, ou traz o que mudou fora do Nix | `sync_index` |
| `nix status` | O índice está atrasado? | `index_status` |
| `nix wiki list` | Quais wikis estão cadastradas? | `list_wikis` |
| `nix brain status` | Como está o Mega Brain neste projeto? | `brain_status` |
| `nix brain handoff create` | Registra onde paramos | `brain_handoff_create` |
| `nix brain handoff list` | Tem handoff aberto? | `brain_handoff_list` |
| `nix brain handoff accept` | Continua o que eu estava fazendo no outro agente | `brain_handoff_accept` |
| `nix brain handoff cancel` | Cancela o handoff | `brain_handoff_cancel` |

`nix`, `nix init`, `nix doctor`, `nix ui`, `nix run`, `nix config`, o restante de `nix wiki`, `nix brain enable`, `nix brain hooks` e `nix brain profile` ficam no terminal. O hook dispara sozinho a cada evento da sessão.

Estas ferramentas não têm comando equivalente. Você as estimula pela frase:

| O que você diz | Ferramenta |
| --- | --- |
| Procura nas notas | `search_notes` |
| Abre a nota, o outline ou um trecho | `read_note`, `get_note_outline`, `read_note_lines` |
| Lista as notas ou as tags | `list_notes`, `list_all_tags` |
| O que aponta para esta nota | `get_linked_notes` |
| Cria, acrescenta ou atualiza a nota, o frontmatter ou as tags | `create_note`, `append_to_note`, `update_note`, `update_frontmatter`, `manage_tags` |
| Move a nota ou o anexo | `move_note`, `move_file` |
| Apaga a nota | `delete_note` (exige confirmação) |
| Notas órfãs, duplicatas ou sugestão de links | `wiki_insights` |
| Lembra que… | `remember` |
| O que o Mega Brain guardou sobre… | `brain_query` |
| Lê a página da sessão, ou lista as recentes | `brain_read_page`, `brain_recent_pages` |
| Me dá o briefing | `brain_briefing` |
| O que aconteceu na sessão | `brain_read_session_observations` |
| Anota uma regra, decisão ou perfil | `brain_write_page`, `brain_patch_page`, `brain_delete_page` |
| Essa página foi útil | `brain_feedback` |
| Deixa um recado, lista, pega ou cancela | `brain_message_send`, `brain_message_list`, `brain_message_pop`, `brain_message_cancel` |

### Referência

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
| `index_status` | Contagens, último sync e defasagem, por wiki |
| `wiki_insights` | Órfãs, duplicatas, sugestão de links ou resumo |
| `remember` | Grava fato duradouro em `longterm_folder` da wiki |
| `list_wikis` | Nome, caminho, padrão e se o índice daquela wiki está desatualizado |
| `brain_query` | Busca na wiki do Mega Brain e nas observações da sessão. O texto é histórico |
| `brain_status` | Wiki, sessões e sessões ainda abertas neste projeto |
| `brain_briefing` | Perfil, handoff oferecido, resumo e mensagens. Não consome o handoff |
| `brain_read_page` | Lê uma página da wiki do Mega Brain pelo caminho relativo |
| `brain_recent_pages` | Lista as páginas de sessão já gravadas, da mais recente para a mais antiga |
| `brain_write_page` | Cria ou substitui uma página curada ou de perfil |
| `brain_patch_page` | Troca um trecho literal de uma página curada ou de perfil |
| `brain_delete_page` | Apaga uma página curada ou de perfil. Exige `confirm=true` |
| `brain_feedback` | Registra se uma página foi útil. Não altera a página |
| `brain_read_session_observations` | Lê as observações brutas de uma sessão. O texto é histórico |
| `brain_handoff_create` | Abre o handoff do projeto. Só pode haver um aberto |
| `brain_handoff_list` | Lista os handoffs do projeto |
| `brain_handoff_accept` | Reivindica o handoff aberto uma única vez |
| `brain_handoff_cancel` | Cancela o handoff aberto |
| `brain_message_send` | Envia uma mensagem para a fila do projeto |
| `brain_message_list` | Lista as mensagens, pendentes e já entregues |
| `brain_message_pop` | Entrega a próxima mensagem pendente uma única vez |
| `brain_message_cancel` | Cancela uma mensagem que ainda está pendente |

## Configuração

Fica em `settings.db`, na pasta do Nix (`NIX_HOME`; no checkout de desenvolvimento, a pasta do repositório). Caminhos relativos resolvem contra essa pasta. Variáveis `NIX_SECAO__CAMPO` ganham do banco nos campos globais (ex.: `NIX_INDEX__EMBEDDING_MODEL`) e o campo correspondente fica travado no `nix config` e na interface. O cadastro das wikis não usa essa variável: nome, pasta, padrão e ajustes (`include`, `exclude`, pastas) ficam no `nix wiki`. `nix wiki set NOME CAMPO VALOR` grava um ajuste; listas e objetos entram como JSON. `nix wiki path NOME CAMINHO` troca a pasta. `nix init` grava a primeira wiki e o modelo. `nix config set secao.chave valor` altera um campo global; listas e objetos entram como JSON. `nix config undo` restaura o valor anterior.

`nix ui` abre as mesmas operações no navegador, sem precisar de um LLM:

- **Operação:** status (o bloco Para começar fica até a wiki escolhida ter sido sincronizada e o editor ter chamado uma ferramenta; o aviso de índice desatualizado só aparece depois dessa sincronização), sincronização com prévia e progresso (os botões ficam desligados até o job terminar, também se a página for recarregada) e diagnóstico.
- **Wiki (somente leitura):** busca em uma, em várias ou em todas, notas (com outline e trechos), tags e insights. A página de insights explica órfãs, duplicadas, sugestões de link e o resumo. O seletor "Wiki ativo", na faixa acima do conteúdo, usa `?wiki=`; sem ele, vale o padrão.
- **Mega Brain:** painel, caixa de entrada e perfil. Os links de uma página de perfil ou de sessão abrem a wiki configurada no Mega Brain.
- **Integração:** trechos prontos para conectar Cursor, VS Code, Claude Code e Codex; tráfego MCP, com as chamadas que os clientes fazem, gravadas em `.nix/traffic.db`.
- **Manutenção:** backups das escritas (comparação e download) e a restauração de um backup, a única escrita na wiki feita pela interface, com confirmação; tela Wikis; formulário de configuração e histórico.

O comando exige o `nix init`, escuta só em `127.0.0.1` e encerra com Ctrl+C ou pelo botão Encerrar. `--no-browser` só imprime a URL; `--port` fixa a porta.

| Chave | Padrão | Função |
| --- | --- | --- |
| wiki (cadastro) | nome `Default` no `nix init` | Pasta de cada wiki, via `nix wiki`. De 1 a 100, um padrão |
| `exclude` da wiki | `.trash/**`, `Templates/**`, `Privado/**` | Pastas ignoradas daquela wiki. Mude com `nix wiki set NOME exclude VALOR` |
| `default_new_note_folder` | `Inbox` | Destino de notas sem pasta no caminho |
| `longterm_folder` | `Nix/Memória` | Destino da ferramenta `remember` |
| `index.data_dir` | `.nix/data` | Base do índice; cada wiki usa `.nix/data/<nome>` |
| `logging.file` | `.nix/logs/nix.log` | Logs; consultas só entram se `log_prompts` estiver ligado |
| `brain.enabled` | desligado | Liga a captura e as ferramentas `brain_*`. Exige reiniciar o cliente MCP |

## Publicar uma versão

Uma release no GitHub é criada automaticamente quando uma tag `vX.Y.Z` chega no remoto. O workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) confere a versão, roda `ruff` e `mypy`, compila `nix` e `nix-hook` por plataforma (Windows amd64, Linux amd64, Linux arm64, macOS arm64) e publica os arquivos com `checksums.txt` em [Releases](https://github.com/paulocesaaars/nix/releases).

1. Atualize `[project].version` em `pyproject.toml` (ex.: `1.2.3`). A tag **precisa** bater com esse valor — senão o job falha.
2. Faça o commit e o push na branch principal.
3. Crie e envie a tag (o `v` no prefixo é obrigatório):

```bash
git tag v1.2.3
git push origin v1.2.3
```

4. Acompanhe o workflow **Release** em Actions. Em caso de sucesso, a release traz `nix` e `nix-hook` por plataforma, um `.mcpb` por plataforma, o `checksums.txt` e o `server.json`. O mesmo job publica a ficha no [MCP Registry](https://github.com/modelcontextprotocol/registry). O zip de código-fonte da tag traz só o que instala e usa o Nix; skills de desenvolvimento, documentação e testes ficam de fora.

O guia em `site/` é publicado à parte, em [paulocesaaars.github.io/nix](https://paulocesaaars.github.io/nix/), quando um push na `main` altera essa pasta.

Para republicar os artefatos de uma tag que já existe, dispare o workflow à mão: Actions → Release → Run workflow, e informe a tag (ex.: `v1.2.3`).

## Documentação

- [PRD.md](docs/PRD.md) — produto, requisitos e regras de negócio
- [TDD.md](docs/TDD.md) — especificações técnicas: componentes, indexação, recuperação e MCP stdio
