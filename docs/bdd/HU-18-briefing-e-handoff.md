# HU-18 — Briefing e handoff

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-18
Funcionalidade: Briefing e handoff

  @HU-18.1
  Cenário: Oferecer o handoff sem consumir
    Dado um handoff aberto no projeto
    Quando uma sessão começa
    Então o briefing mostra o handoff
    E o handoff continua aberto

  @HU-18.2
  Cenário: Reivindicar o handoff uma única vez
    Dado um handoff aberto no projeto
    Quando dois agentes chamam `brain_handoff_accept`
    Então só o primeiro recebe o texto
    E o segundo é informado de quem já reivindicou

  @HU-18.3
  Cenário: Avisar sessão interrompida
    Dado a sessão mais nova do projeto sem `session-end` e sem handoff
    Quando outra sessão começa
    Então o briefing traz o aviso com o id dessa sessão

  @HU-18.4 @manual
  Cenário: Retomar com outro agente pelo nix run
    Dado uma sessão do Claude Code interrompida no projeto
    Quando executo `nix run codex`
    Então o Codex recebe `NIX_PREVIOUS_SESSION_HISTORY`
    E o arquivo some quando o Codex termina
```
