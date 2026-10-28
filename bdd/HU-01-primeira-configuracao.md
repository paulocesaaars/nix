# HU-01 — Primeira configuração

História no [PRD.md](../PRD.md). Convenções no [BDD.md](../BDD.md).

```gherkin
# language: pt
@HU-01
Funcionalidade: Primeira configuração

  @HU-01.1
  Cenário: Configurar pela primeira vez
    Dado que o Nix nunca foi configurado
    Quando executo `nix init` e informo o vault e o modelo de embedding
    Então `settings.db` é criado na pasta do Nix com o vault `Default`
    E o caminho do vault usa barras `/` no Windows
    E `index.embedding_model` fica gravado

  @HU-01.2
  Cenário: Configurar sem prompt
    Dado `--name NOME`, `--vault CAMINHO` e `--embedding-model MODELO`
    Quando executo `nix init`
    Então não há prompt
    E o primeiro vault usa esse nome e esse caminho

  @HU-01.3
  Cenário: Reexecutar o init sem forçar
    Dado que a configuração já existe
    E não passei `--force` nem `--embedding-model`
    Quando executo `nix init`
    Então só o caminho do vault padrão é atualizado
    E o restante da configuração permanece

  @HU-01.4
  Cenário: Recusar nome quando já há vaults
    Dado que já existem vaults
    Quando executo `nix init --name NOME`
    Então o comando recusa e pede `nix vault add`

  @HU-01.5
  Cenário: Criar a pasta do vault inexistente
    Dado que o caminho informado no prompt ainda não existe
    Quando confirmo a criação
    Então o diretório é criado e gravado no vault

  @HU-01.6
  Cenário: Diagnosticar vault com pasta ausente
    Dado que o caminho de um vault não existe
    Quando valido com `nix doctor`
    Então recebo um erro apontando esse vault e o caminho
```
