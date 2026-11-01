# HU-24 — Ficha no MCP Registry

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-24
Funcionalidade: Ficha no MCP Registry

  @HU-24.1
  Cenário: Apontar a ficha para o artefato da release
    Dado a ficha `io.github.paulocesaaars/nix`
    Quando ela é publicada com a tag
    Então o pacote é o MCPB dessa mesma release
    E o transporte é stdio
    E a ficha traz o SHA-256 desse arquivo
```
