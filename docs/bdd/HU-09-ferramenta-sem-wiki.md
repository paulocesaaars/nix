# HU-09 — Ferramenta sem wiki

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-09
Funcionalidade: Ferramenta sem wiki

  @HU-09.1
  Cenário: Usar a wiki padrão
    Dado mais de uma wiki e uma padrão
    Quando uma ferramenta é chamada sem `wiki`
    Então a operação usa a padrão

  @HU-09.2
  Cenário: Listar as wikis
    Dado wikis cadastradas
    Quando o agente chama `list_wikis`
    Então recebe nome, caminho, qual é a padrão e se o índice de cada wiki está desatualizado
```
