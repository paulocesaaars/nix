# HU-06 — Usar o Nix dentro do editor

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-06
Funcionalidade: Usar o Nix dentro do Cursor ou equivalente

  @HU-06.1 @manual
  Cenário: Consultar o vault pelo agente do editor
    Dado o Nix registrado no cliente MCP com `command` apontando para o binário da instalação
    Quando peço ao agente do editor algo sobre minhas notas
    Então ele usa as ferramentas do Nix
    E recebe trechos com caminho e citação

  @HU-06.2 @manual
  Cenário: Comando só pelo nome falha na IDE
    Dado `"command": "nix"` na IDE aberta pelo Dock ou menu
    Quando o cliente tenta iniciar o processo
    Então a conexão falha com `spawn nix ENOENT`

  @HU-06.3 @manual
  Cenário: Caminho absoluto no macOS e no Linux
    Dado macOS ou Linux
    Quando o `command` do MCP é o caminho absoluto da linha `comando nix:` do `nix doctor`
    Então o servidor sobe

  @HU-06.4
  Cenário: Índice atualizado após alteração via MCP
    Dado que peço uma alteração de nota via MCP
    Quando ela é aplicada
    Então o índice é atualizado automaticamente

  @HU-06.5
  Cenário: Escrita destrutiva exige confirmação
    Dado `update_note` em modo replace ou `delete_note`
    Quando o cliente chama a ferramenta
    Então a escrita só ocorre com `confirm=true`
    E a ferramenta declara `destructiveHint`
```
