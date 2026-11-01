# HU-12 — Busca em todas as wikis

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-12
Funcionalidade: Busca em todas as wikis

  @HU-12.1
  Cenário: Buscar em todas
    Dado várias wikis indexadas
    Quando `search_notes` recebe `wiki` igual a `"*"`
    Então os trechos vêm do conjunto, cada um com a wiki de origem

  @HU-12.2
  Cenário: Uma wiki falha na busca
    Dado que uma das wikis falha
    Quando a busca termina
    Então os trechos das outras continuam na resposta
    E a falha vem à parte, com a ação corretiva

  @HU-12.3
  Cenário: Limite do list_notes por wiki
    Dado `list_notes` com um limite e mais de uma wiki
    Quando a ferramenta responde
    Então o limite vale em cada wiki e a resposta junta as listas

  @HU-12.4
  Cenário: Tags somadas entre wikis
    Dado `list_all_tags` com um limite e tags em mais de uma wiki
    Quando a ferramenta responde
    Então as contagens são somadas
    E o limite vale só na lista já somada
```
