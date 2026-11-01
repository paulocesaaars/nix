# HU-13 — Remover a padrão

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-13
Funcionalidade: Sempre existe uma wiki padrão

  @HU-13.1
  Cenário: Recusar remover a padrão
    Dado duas ou mais wikis
    Quando tento remover a padrão
    Então a operação é recusada até eu escolher outra com `nix wiki default`

  @HU-13.2
  Cenário: Recusar remover a única wiki
    Dado uma única wiki
    Quando tento removê-la
    Então a operação é recusada

  @HU-13.3
  Cenário: Renomear preserva índice e backups
    Dado uma wiki cadastrada
    Quando executo `nix wiki rename ANTIGO NOVO`
    Então o índice e os backups permanecem na pasta do nome anterior
    E a CLI pede `nix sync --full --wiki NOVO` se a busca ficar vazia

  @HU-13.4
  Cenário: Bloquear alterações durante a sincronização
    Dado uma sincronização daquela wiki em andamento
    Quando tento renomear, remover, trocar a pasta ou gravar um ajuste
    Então a operação é recusada e pede para esperar o término
```
