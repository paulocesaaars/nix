# HU-02 — Indexar uma wiki existente

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-02
Funcionalidade: Indexar uma wiki existente

  @HU-02.1
  Cenário: Indexar todas as notas
    Dado uma wiki com N notas em Markdown
    Quando executo `nix sync`
    Então todas as notas não ignoradas são vetorizadas
    E um resumo com contagens e tempo é exibido

  @HU-02.2
  Cenário: Mostrar progresso
    Dado uma sincronização longa
    Quando a sincronização roda
    Então vejo progresso incremental

  @HU-02.3
  Cenário: Nota com encoding inválido
    Dado que uma nota tem encoding inválido
    Quando a sincronização roda
    Então ela é reportada como erro ao final
    E as demais notas são indexadas normalmente
```
