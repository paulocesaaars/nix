# HU-11 — Escrita recebendo lista

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-11
Funcionalidade: Escrita recebendo lista

  @HU-11.1
  Cenário: Recusar escrita em várias wikis
    Dado `create_note` ou outra ferramenta de escrita com `wiki` em lista ou `"*"`
    Quando a chamada chega
    Então ela é recusada e pede um único nome, ou omitir para usar a padrão

  @HU-11.2
  Cenário: Escrever numa única wiki
    Dado a mesma escrita com um nome só
    Quando a chamada chega
    Então o arquivo fica só naquela wiki
```
