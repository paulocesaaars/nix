# HU-07 — Desinstalar o ambiente

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-07 @manual
Funcionalidade: Desinstalar o ambiente

  @HU-07.1
  Cenário: Desinstalar preservando o vault
    Dado uma instalação concluída
    Quando executo `uninstall.bat`, `.\uninstall.ps1` ou `sh uninstall.sh` e confirmo
    Então `NIX_HOME` e `{NIX_HOME}/bin` saem do PATH do usuário
    E o binário, `.nix/` e `settings.db` são apagados
    E o vault permanece intacto

  @HU-07.2
  Cenário: Manter os dados
    Dado `--keep-data`
    Quando desinstalo
    Então o PATH é desfeito e o binário some
    E `settings.db` e `.nix/` permanecem

  @HU-07.3
  Cenário: Desinstalar sem terminal interativo
    Dado `--yes` ou `-y`
    Quando não há terminal interativo
    Então a confirmação é dispensada e a desinstalação segue

  @HU-07.4
  Cenário: Preservar outra instalação
    Dado que `NIX_HOME` aponta para outra pasta
    Quando desinstalo esta cópia
    Então a variável e o bloco de shell da outra instalação não são removidos

  @HU-07.5
  Cenário: Comando some do PATH
    Dado que a desinstalação concluiu
    Quando abro um novo terminal
    Então o comando `nix` deste projeto não é encontrado no PATH
```
