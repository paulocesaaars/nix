# HU-15 — Continuar a partir de uma sessão

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-15
Funcionalidade: Continuar a partir de uma sessão

  @HU-15.1
  Cenário: Descartar evento sem captura pedida
    Dado um projeto sem hooks da Nix para aquele agente
    Quando chega um evento de sessão desse agente
    Então o banco de sessões não ganha essa sessão

  @HU-15.2
  Cenário: Gravar evento com captura pedida
    Dado um projeto com hooks da Nix para aquele agente
    Quando chega um evento de sessão desse agente
    Então a sessão fica gravada nesse projeto

  @HU-15.3
  Cenário: Entregar o handoff uma única vez
    Dado uma sessão gravada com um pedido
    Quando dois agentes pedem o handoff com aceitação
    Então só o primeiro recebe o texto
    E o texto trata o conteúdo como histórico
    E o segundo fica sem handoff

  @HU-15.4
  Cenário: Marcar ferramenta já executada
    Dado uma sessão com uma ferramenta já chamada
    Quando leio essa sessão
    Então a ferramenta aparece como já executada
    E a resposta diz que o conteúdo é histórico

  @HU-15.5
  Cenário: Esconder sessões na busca comum
    Dado sessões ligadas e uma nota na pasta de sessões
    Quando busco sem filtro de pasta
    Então a nota de sessão não entra no resultado

  @HU-15.6
  Cenário: Incluir sessões quando a pasta é pedida
    Dado sessões ligadas e uma nota na pasta de sessões
    Quando busco com a pasta de sessões
    Então a nota de sessão entra no resultado

  @HU-15.7
  Cenário: Esconder ferramentas com sessões desligadas
    Dado `sessions.enabled` desligado
    Quando o cliente lista as ferramentas
    Então `list_sessions` não está entre elas
    E uma chamada a `list_sessions` explica como ligar

  @HU-15.8
  Cenário: Instalar e remover só a skill da Nix
    Dado um repositório com uma skill que não é da Nix
    Quando executo `nix skills install --agent cursor --yes`
    Então a pasta `.agents/skills/sessoes-nix` recebe a skill e a marca da Nix
    Quando executo `nix skills remove --agent cursor`
    Então a skill da Nix sai
    E a skill que não é da Nix permanece

  @HU-15.9 @manual
  Cenário: O editor chama o hook
    Dado os hooks instalados no editor
    Quando uma sessão começa e outra termina
    Então o início recebe o handoff no formato daquele editor
    E o fim pede a nota da sessão sem o editor esperar
```
