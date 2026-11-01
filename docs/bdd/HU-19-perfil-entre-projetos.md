# HU-19 — Perfil entre projetos

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-19
Funcionalidade: Perfil entre projetos

  @HU-19.1
  Cenário: Aprender preferência repetida em dois projetos
    Dado o pedido "sempre use pnpm" em dois projetos
    Quando a passada do perfil roda
    Então o perfil ganha a entrada sobre pnpm com a evidência dos dois projetos

  @HU-19.2
  Cenário: Não recriar entrada esquecida
    Dado a entrada sobre pnpm no perfil
    Quando executo `nix brain profile forget tools/pnpm.md` e a passada roda de novo
    Então a entrada não volta
```
