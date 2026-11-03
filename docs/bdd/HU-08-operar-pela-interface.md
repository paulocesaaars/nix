# HU-08 — Configurar e operar pela interface

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-08
Funcionalidade: Configurar e operar pela interface

  @HU-08.1 @manual
  Cenário: Abrir a interface
    Dado que já rodei `nix init`
    Quando executo `nix ui`
    Então o navegador abre numa página local
    E o terminal mostra a URL

  @HU-08.2
  Cenário: Interface sem configuração
    Dado que ainda não configurei
    Quando executo `nix ui`
    Então o comando pede `nix init`
    E não sobe servidor

  @HU-08.3
  Cenário: Salvar um campo válido
    Dado a página de configuração
    Quando salvo um campo válido
    Então o valor passa a valer
    E a origem deixa de ser o padrão

  @HU-08.4
  Cenário: Campo definido por variável de ambiente
    Dado um campo definido por variável de ambiente
    Quando abro a configuração
    Então o campo aparece travado

  @HU-08.5
  Cenário: Desfazer pelo histórico
    Dado uma alteração registrada no histórico
    Quando desfaço essa alteração
    Então o valor anterior volta a valer

  @HU-08.6 @manual
  Cenário: Encerrar a interface
    Dado o botão Encerrar ou Ctrl+C no terminal
    Quando confirmo e não há sincronização
    Então o processo da interface termina

  @HU-08.7 @manual
  Cenário: Encerrar durante uma sincronização
    Dado uma sincronização em andamento
    Quando clico em Encerrar
    Então a página pede para esperar
    E Ctrl+C nesse meio só fecha o índice depois que a sincronização termina

  @HU-08.8
  Cenário: Busca da interface igual à do MCP
    Dado o índice sincronizado
    Quando busco uma pergunta na tela Busca
    Então vejo os mesmos trechos que `search_notes` devolveria, com caminho, linhas e pontuação

  @HU-08.9
  Cenário: Ver o tráfego MCP
    Dado um cliente MCP que chamou ferramentas
    Quando abro Tráfego MCP
    Então vejo cada chamada com cliente, duração e situação
    E os argumentos não aparecem se `logging.log_prompts` estiver desligado

  @HU-08.10
  Cenário: Restaurar um backup
    Dado um backup de uma nota
    Quando marco a confirmação e restauro
    Então a nota volta ao conteúdo do backup
    E o estado anterior ganha backup
    E o índice é atualizado

  @HU-08.11
  Cenário: Mostrar os clientes na ordem de conexão
    Dado o executável do Nix encontrado
    Quando abro Conectar cliente
    Então as abas começam nesta ordem: Cursor, VS Code, Claude Code, Codex
    E em seguida vêm Command Code, Devin (CLI e Desktop), OpenCode, Gemini CLI, Oh My Pi, Pi, OpenClaw, Antigravity CLI, Grok Build CLI, Zero, ZCode, Kimi Code, Kiro CLI, GitHub Copilot CLI, Factory Droid, Meta Muse Code, IBM Bob, Qwen Code, Qoder e Hermes Agent
    E o Codex mostra o bloco `[mcp_servers.nix]` com o caminho absoluto
    E a configuração do Codex fica em `.codex/config.toml` no projeto, com orientação para confiar no projeto
    E o Devin mostra `mcpServers` com `command` apontando para o binário do Nix

  @HU-08.12
  Cenário: Explicar os hooks na página
    Dado a página Conectar cliente
    Quando leio a seção de hooks
    Então vejo a explicação de instalar um, alguns ou todos
    E vejo a explicação de escopo global ou só o repositório
    E o comando mostrado é `nix brain hooks install`

  @HU-08.13
  Cenário: Mostrar o caminho inicial no Status
    Dado que a wiki padrão existe e a selecionada nunca foi sincronizada
    E nenhum editor chamou uma ferramenta
    Quando abro o Status
    Então vejo a wiki padrão como feita, com o nome dela
    E vejo sincronizar como pendente
    E vejo "Pedir uma busca ao editor" como pendente, pedindo para buscar uma nota
    E cada pendência leva à página correspondente
    E não vejo a faixa de índice desatualizado

  @HU-08.14
  Cenário: Esconder o caminho quando a wiki selecionada já andou
    Dado que a wiki selecionada já foi sincronizada
    E o editor já pediu uma busca
    Quando abro o Status
    Então o bloco Para começar não aparece

  @HU-08.15
  Cenário: Trazer o caminho de volta numa wiki sem sync
    Dado que a wiki padrão já foi sincronizada e o editor já pediu uma busca
    E outra wiki nunca foi sincronizada
    Quando abro o Status nessa outra wiki
    Então o bloco volta
    E sincronizar está pendente para ela
    E pedir uma busca ao editor continua feito

  @HU-08.16
  Cenário: Índice desatualizado não desfaz o sync já feito
    Dado que a wiki selecionada já foi sincronizada e depois ficou desatualizada
    E o editor já pediu uma busca
    Quando abro o Status
    Então o bloco Para começar não aparece
    E vejo o aviso de índice desatualizado

  @HU-08.17
  Cenário: Avisar quando a wiki selecionada não é a padrão
    Dado que a wiki selecionada não é a padrão
    E o caminho inicial ainda está pendente
    Quando abro o Status
    Então vejo o nome da selecionada e o nome da padrão acima dos passos

  @HU-08.18
  Cenário: Manter a busca pedida sem o tráfego
    Dado que a marca de busca pedida está gravada
    E o tráfego não tem chamadas
    E a wiki selecionada já foi sincronizada
    Quando abro o Status
    Então o bloco Para começar não aparece

  @HU-08.19
  Cenário: Completar a marca ao abrir o Status com tráfego já gravado
    Dado uma chamada no tráfego
    E a marca de busca pedida ainda é falsa
    Quando abro o Status
    Então a marca fica verdadeira

  @HU-08.20
  Cenário: Gravar a marca na primeira chamada de ferramenta
    Dado que a marca de busca pedida ainda é falsa
    Quando uma chamada de ferramenta termina bem
    Então a marca fica verdadeira
    E uma chamada que termina em erro também grava a marca
    E uma falha ao gravar a marca não derruba a chamada da ferramenta

  @HU-08.21
  Cenário: Manter o caminho quando a busca ainda não foi pedida
    Dado que a wiki selecionada já foi sincronizada
    E a marca de busca pedida está apagada
    E o tráfego não tem chamadas
    Quando abro o Status
    Então o bloco Para começar continua visível
    E sincronizar aparece feito
    E pedir uma busca aparece pendente

  @HU-08.22
  Cenário: Trecho MCP só por comando local
    Dado o executável do Nix encontrado
    Quando abro a aba de um cliente da lista
    Então o trecho traz o caminho desse executável
    E o trecho não traz URL http
```
