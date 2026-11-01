# HU-21 — Contagem de tokens

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-21
Funcionalidade: Contagem de tokens

  @HU-21.1
  Cenário: Contar uma resposta repetida uma vez
    Dado o mesmo id de resposta lido em dois eventos
    Quando abro o uso da sessão
    Então a resposta conta uma vez

  @HU-21.2
  Cenário: Mostrar uso desconhecido
    Dado um agente que não grava uso de tokens
    Quando abro o uso da sessão
    Então o uso aparece como desconhecido

  @HU-21.3
  Cenário: Somar o uso de cada IA no projeto
    Dado um projeto com duas IAs e usos em mais de um modelo
    Quando abro a aba Tokens desse projeto
    Então vejo uma linha por IA, com entrada e saída
    E vejo um total que soma essas linhas
    E não vejo o total de outro projeto

  @HU-21.4
  Cenário: Deixar o uso desconhecido fora do total
    Dado um projeto sem número de tokens
    Quando abro a aba Tokens
    Então o uso aparece como desconhecido
    E não aparece um total zero
```
