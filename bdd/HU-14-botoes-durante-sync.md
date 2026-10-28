# HU-14 — Botões desligados durante o sync

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-14
Funcionalidade: Botões desligados durante a sincronização

  @HU-14.1
  Cenário: Desligar controles ao iniciar
    Dado que inicio a sincronização na interface
    Quando o pedido é aceito
    Então prévia, incremental, reindexação completa e a opção de todos os vaults ficam desligados até o job terminar

  @HU-14.2
  Cenário: Controles continuam desligados ao recarregar
    Dado o job ainda em andamento
    Quando recarrego a página de sincronizar
    Então esses controles continuam desligados

  @HU-14.3
  Cenário: Controles voltam ao terminar
    Dado que o job terminou
    Quando a página mostra o resultado
    Então os controles voltam a funcionar

  @HU-14.4
  Cenário: Pedido durante um job em andamento
    Dado um job já em andamento
    Quando peço outro ou uma prévia
    Então a interface pede para esperar
    E o progresso continua na tela
    E a prévia não varre o vault
```
