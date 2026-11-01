# HU-20 — Mensagens entre agentes

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-20
Funcionalidade: Mensagens entre agentes

  @HU-20.1
  Cenário: Entregar a mensagem uma única vez
    Dado uma mensagem na fila do projeto para o Codex
    Quando dois clientes chamam `brain_message_pop`
    Então só o primeiro recebe a mensagem

  @HU-20.2
  Cenário: Avisar mensagem no início da sessão
    Dado uma mensagem na fila do projeto
    Quando uma sessão do agente destinatário começa
    Então o briefing avisa a quantidade de mensagens esperando
```
