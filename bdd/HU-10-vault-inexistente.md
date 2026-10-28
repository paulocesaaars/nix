# HU-10 — Vault inexistente

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-10
Funcionalidade: Vault inexistente

  @HU-10.1
  Cenário: Nome não cadastrado
    Dado um nome de vault que não está cadastrado
    Quando uma ferramenta, um recurso ou um comando pede esse vault
    Então o erro lista os vaults existentes e diz qual é o padrão

  @HU-10.2
  Cenário: Nome sem diferenciar maiúsculas
    Dado o vault cadastrado como `Default`
    Quando informo `default`
    Então o vault encontrado é o `Default`
```
