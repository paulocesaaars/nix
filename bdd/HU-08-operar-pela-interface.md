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
```
