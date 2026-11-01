# HU-05 — Registrar conhecimento pelo editor

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-05
Funcionalidade: Registrar conhecimento pelo editor

  @HU-05.1
  Cenário: Nota criada já é pesquisável
    Dado que peço a criação de uma nota
    Quando ela é gravada na wiki
    Então ela já retorna em buscas logo após a operação, sem sincronização manual

  @HU-05.2
  Cenário: Sobrescrever exige confirmação
    Dado que a nota já existe
    Quando peço para sobrescrever
    Então a ferramenta exige `confirm=true`

  @HU-05.3
  Cenário: Recusar escrita fora da wiki
    Dado que peço para gravar fora da wiki
    Quando a operação é tentada
    Então ela é rejeitada
```
