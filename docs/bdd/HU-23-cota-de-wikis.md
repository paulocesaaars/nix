# HU-23 — Cota de wikis

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-23
Funcionalidade: Cota de wikis

  @HU-23.1
  Cenário: Aceitar a centésima wiki
    Dado 99 wikis cadastradas
    Quando cadastro mais uma com nome e pasta válidos
    Então a instalação fica com 100 wikis
    E continua com exatamente uma padrão

  @HU-23.2
  Cenário: Recusar a centésima primeira wiki
    Dado 100 wikis cadastradas
    Quando cadastro mais uma
    Então a wiki não é cadastrada
    E a mensagem diz que o teto é 100 e indica `nix wiki remove NOME`
```
