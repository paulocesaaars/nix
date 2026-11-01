# HU-16 — Wiki genérica

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-16
Funcionalidade: Wiki genérica

  @HU-16.1
  Cenário: Migrar vaults para wikis
    Dado um settings.db com o vault "Default"
    Quando a Nix atualizada abre a configuração
    Então `nix wiki list` mostra a wiki "Default" com a mesma pasta
    E a busca nela devolve as notas já indexadas

  @HU-16.2
  Cenário: Aceitar o nome antigo com aviso
    Dado a wiki "Default" cadastrada
    Quando chamo `search_notes` com o parâmetro `vault`
    Então recebo o resultado da wiki "Default"
    E a resposta avisa para usar o parâmetro `wiki`
```
