# HU-09 — Ferramenta sem vault

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-09
Funcionalidade: Ferramenta sem vault

  @HU-09.1
  Cenário: Usar o vault padrão
    Dado mais de um vault e um padrão
    Quando uma ferramenta é chamada sem `vault`
    Então a operação usa o padrão

  @HU-09.2
  Cenário: Listar os vaults
    Dado vaults cadastrados
    Quando o agente chama `list_vaults`
    Então recebe nome, caminho, qual é o padrão e se o índice de cada vault está desatualizado
```
