# HU-12 — Busca em todos os vaults

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-12
Funcionalidade: Busca em todos os vaults

  @HU-12.1
  Cenário: Buscar em todos
    Dado vários vaults indexados
    Quando `search_notes` recebe `vault` igual a `"*"`
    Então os trechos vêm do conjunto, cada um com o vault de origem

  @HU-12.2
  Cenário: Um vault falha na busca
    Dado que um dos vaults falha
    Quando a busca termina
    Então os trechos dos outros continuam na resposta
    E a falha vem à parte, com a ação corretiva

  @HU-12.3
  Cenário: Limite do list_notes por vault
    Dado `list_notes` com um limite e mais de um vault
    Quando a ferramenta responde
    Então o limite vale em cada vault e a resposta junta as listas

  @HU-12.4
  Cenário: Tags somadas entre vaults
    Dado `list_all_tags` com um limite e tags em mais de um vault
    Quando a ferramenta responde
    Então as contagens são somadas
    E o limite vale só na lista já somada
```
