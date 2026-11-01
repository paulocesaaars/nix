# HU-22 — Painel do Mega Brain

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-22
Funcionalidade: Painel do Mega Brain

  @HU-22.1
  Cenário: Filtrar projetos pelo nome
    Dado três projetos com sessões
    Quando digito parte do nome de um no filtro
    Então só esse cartão fica visível

  @HU-22.2 @manual
  Cenário: Navegar pelas abas do projeto
    Dado um projeto com sessões e tokens
    Quando abro o projeto e troco de aba
    Então só a seção escolhida aparece
    E a URL guarda a aba
```
