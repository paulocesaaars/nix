# HU-03 — Sincronizar mudanças feitas fora do Nix

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-03
Funcionalidade: Sincronizar mudanças feitas fora do Nix

  @HU-03.1
  Cenário: Reprocessar só o que mudou
    Dado que editei 3 notas e apaguei 1 fora do Nix
    Quando executo `nix sync` ou `sync_index`
    Então apenas essas 4 notas são reprocessadas
    E a nota apagada é removida do índice

  @HU-03.2
  Cenário: Nada mudou
    Dado que nada mudou na wiki
    Quando executo a sincronização
    Então nenhuma nota é reprocessada
    E isso é informado

  @HU-03.3
  Cenário: Avisar índice desatualizado sem vetorizar
    Dado que a wiki mudou e eu não sincronizei
    Quando chamo `index_status`
    Então recebo aviso de índice desatualizado
    E nenhuma vetorização automática acontece
```
