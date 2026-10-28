# HU-13 — Remover o padrão

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-13
Funcionalidade: Sempre existe um vault padrão

  @HU-13.1
  Cenário: Recusar remover o padrão
    Dado dois ou mais vaults
    Quando tento remover o padrão
    Então a operação é recusada até eu escolher outro com `nix vault default`

  @HU-13.2
  Cenário: Recusar remover o único vault
    Dado um único vault
    Quando tento removê-lo
    Então a operação é recusada

  @HU-13.3
  Cenário: Renomear preserva índice e backups
    Dado um vault cadastrado
    Quando executo `nix vault rename ANTIGO NOVO`
    Então o índice e os backups permanecem na pasta do nome anterior
    E a CLI pede `nix sync --full --vault NOVO` se a busca ficar vazia

  @HU-13.4
  Cenário: Bloquear alterações durante a sincronização
    Dado uma sincronização daquele vault em andamento
    Quando tento renomear, remover, trocar a pasta ou gravar um ajuste
    Então a operação é recusada e pede para esperar o término
```
