# HU-10 — Wiki inexistente

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-10
Funcionalidade: Wiki inexistente

  @HU-10.1
  Cenário: Nome não cadastrado
    Dado um nome de wiki que não está cadastrado
    Quando uma ferramenta, um recurso ou um comando pede essa wiki
    Então o erro lista as wikis existentes e diz qual é a padrão

  @HU-10.2
  Cenário: Nome sem diferenciar maiúsculas
    Dado a wiki cadastrada como `Default`
    Quando informo `default`
    Então a wiki encontrada é a `Default`
```
