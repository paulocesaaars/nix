# HU-04 — Instalar o ambiente

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-04 @manual
Funcionalidade: Instalar o ambiente

  @HU-04.1
  Cenário: Instalar numa plataforma suportada
    Dado um Windows amd64, Linux (amd64 ou arm64) ou macOS Apple Silicon sem Python no PATH
    Quando executo `install.bat`, `.\install.ps1` ou `sh install.sh`
    Então o binário da plataforma é baixado e o SHA-256 confere
    E `NIX_HOME` aponta para a pasta da instalação
    E `{NIX_HOME}/bin` entra no PATH do usuário
    E `nix init` pergunta o vault se ainda não houver `settings.db`
    E a mensagem de configuração concluída é exibida

  @HU-04.2
  Cenário: Comando disponível em novo terminal
    Dado que a instalação concluiu
    Quando abro um novo terminal em qualquer diretório
    Então `nix sync` e os demais subcomandos são encontrados no PATH

  @HU-04.3
  Cenário: Outro nix no PATH
    Dado que já existe outro `nix` no PATH (NixOS/Nixpkgs)
    Quando o instalador registra o comando
    Então um aviso é emitido
    E este projeto passa a ter prioridade no PATH

  @HU-04.4
  Cenário: Repassar o vault ao init
    Dado `--vault CAMINHO` no instalador
    Quando ele chega no `init`
    Então o argumento é repassado e o prompt do vault é pulado

  @HU-04.5
  Cenário: Reinstalar preservando a configuração
    Dado que `NIX_HOME` já aponta para uma pasta com `settings.db`
    Quando rodo o instalador de novo
    Então essa pasta é preservada
    E o binário em `{NIX_HOME}/bin` é substituído
    E o `init` não é repetido

  @HU-04.6
  Cenário: Recusar arquitetura sem binário
    Dado Windows arm64 ou macOS Intel
    Quando executo o instalador
    Então ele recusa a arquitetura e diz qual binário existe
```
