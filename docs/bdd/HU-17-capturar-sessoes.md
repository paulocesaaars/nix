# HU-17 — Capturar sessões no Mega Brain

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-17
Funcionalidade: Capturar sessões no Mega Brain

  @HU-17.1
  Cenário: Capturar com hook global
    Dado o Mega Brain ligado e o hook global do agente instalado
    E um repositório sem instalação local
    Quando chega um evento de sessão desse repositório
    Então a sessão fica gravada nesse projeto

  @HU-17.2
  Cenário: Respeitar o opt-out do projeto
    Dado o hook global instalado
    E um `.nix.toml` com `[capture] enabled = false`
    Quando chega um evento de sessão desse repositório
    Então nada é gravado

  @HU-17.3
  Cenário: Descartar caminho excluído
    Dado `[capture] exclude = ["segredos/**"]` no `.nix.toml`
    Quando chega uma ferramenta que leu "segredos/chave.txt"
    Então esse evento não é gravado

  @HU-17.4
  Cenário: Gravar a página no fim da sessão
    Dado uma sessão com dois pedidos
    Quando chega o `session-end` e o trabalho em segundo plano termina
    Então a wiki do Mega Brain ganha a página em `projects/<projeto>/sessions/`
    E `brain_query` encontra essa página

  @HU-17.5
  Cenário: Explicar o instalador antes de gravar
    Dado o Mega Brain ligado
    Quando rodo `nix brain hooks install` e ainda não confirmo
    Então vejo a escolha entre um, alguns ou os quatro clientes
    E vejo a escolha entre a conta inteira e só o repositório
    E nenhum arquivo de hook é gravado

  @HU-17.6
  Cenário: Instalar nos quatro clientes confirmados
    Dado `--all` e `--scope project` confirmados
    Quando o plano é aplicado
    Então os quatro clientes com formato confirmado são instalados
    E Gemini, OpenCode, Kimi, Kiro, Grok, Antigravity, Devin CLI e Devin Desktop não são oferecidos

  @HU-17.7
  Cenário: Não inventar arquivo sem formato confirmado
    Dado um cliente dos quatro cujo formato de hook não está confirmado
    Quando peço para instalá-lo
    Então a captura fica parcial
    E nenhum arquivo de hook é gravado
    E a mensagem explica isso
```
