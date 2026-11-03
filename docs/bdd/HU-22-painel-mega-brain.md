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
  @HU-22.3
  Cenário: Habilitar e desabilitar com wiki configurada
    Dado uma wiki cadastrada escolhida para o Mega Brain
    Quando salvo a wiki e o estado em Configuração na seção Mega Brain
    Então o estado escolhido é persistido
    E a wiki configurada permanece

  @HU-22.4
  Cenário: Impedir alteração sem wiki configurada
    Dado que o Mega Brain não tem uma wiki cadastrada escolhida
    Quando tento salvar sem escolher uma wiki na Configuração do Mega Brain
    Então a alteração é recusada

  @HU-22.5
  Cenário: Bloquear somente o campo definido por ambiente
    Dado que apenas a wiki ou o estado está definido por variável de ambiente
    Quando abro a Configuração do Mega Brain
    Então somente esse campo está bloqueado
    E consigo salvar o outro campo respeitando o valor do ambiente

  @HU-22.6
  Cenário: Habilitar pela CLI sem gravação parcial
    Dado que o estado está definido por variável de ambiente
    Quando tento habilitar pela CLI com uma wiki cadastrada
    Então o comando recusa a alteração
    E nenhuma parte da configuração é gravada
```
