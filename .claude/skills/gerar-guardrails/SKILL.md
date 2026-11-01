---
name: gerar-guardrails
description: >-
  Gera a proteção do repositório no GitHub para que os testes sempre passem
  antes de entrar na branch principal e antes de publicar uma release: o
  workflow de CI do pull request, o portão de testes no workflow de release e a
  regra (ruleset) que bloqueia o merge e o push direto sem o CI verde.
  Descobre a stack e os comandos de teste, lint e tipos do repositório. Use
  quando o usuário pedir guardrails, proteção da main, CI de pull request,
  exigir teste verde para merge ou release, ou garantir que os testes sempre
  passem. Roda uma vez. Sem suíte de testes, avisa e não gera nada.
---

# Gerar Guardrails

Cria proteção **no servidor**, sujeita às permissões e exceções configuradas: um CI que roda em
todo pull request para a branch principal e uma regra do GitHub que só deixa o
merge acontecer com o CI verde. Explicações ao usuário em **português (Brasil)**.

Hook de git roda na máquina de cada pessoa e se pula com `--no-verify`; o CI e a
regra da branch não. Nada aqui é específico de um projeto: stack, comandos e
nomes são **descobertos** no repositório (passo 1). Se algo não puder ser
descoberto, pergunte em vez de supor.

**Host de código.** Confira `git remote get-url origin`. No **GitHub**, siga o
fluxo abaixo. Em outro host (GitLab, Azure DevOps, Bitbucket…) a estratégia é a
mesma — um pipeline que roda em todo pull request e uma regra da branch que
exige o pipeline verde —, mas esta skill só gera arquivos para o GitHub: nos
demais, entregue ao usuário o plano (passos 1 a 3), o comando de teste
descoberto e o pedido pronto para quem administra o repositório, e não rode
nada no host.

## Regras

- Crie e altere **apenas** arquivos em `.github/workflows/`. Não toque em código
  nem em testes.
- Mostre o plano (passo 3) e **aguarde confirmação** antes de gravar e antes de
  qualquer chamada que mude configuração do repositório no GitHub.
- Mostre o comando `gh` exato antes de rodá-lo. Nunca use `--force`.
- **Nunca** sobrescreva um workflow existente sem mostrar o diff e perguntar.
- Não desligue nem afrouxe regras que já existam. Se houver uma regra na branch,
  mostre-a e pergunte se quer ajustá-la.

## Fluxo

```
Progresso:
- [ ] 1. Descobrir o contexto
- [ ] 2. Conferir workflows e regras existentes
- [ ] 3. Confirmar o plano com o usuário
- [ ] 4. Gerar o workflow de CI do pull request
- [ ] 5. Ligar o portão de testes à release
- [ ] 6. Publicar o workflow antes de proteger a branch
- [ ] 7. Criar a regra de proteção
- [ ] 8. Validar
- [ ] 9. Relatar
```

### 1. Descobrir o contexto

| Dado | Onde descobrir |
|------|----------------|
| Repositório e branch principal | `gh repo view --json nameWithOwner,defaultBranchRef,isPrivate,viewerPermission` |
| Stack, versão e dependências | Manifesto e lockfile: `pyproject.toml` e `requirements*.txt`, `package.json`, `Cargo.toml`, `go.mod`, `*.csproj`, `pom.xml`/`build.gradle` |
| Comandos de lint, tipos e teste | Os passos que o workflow de release já roda; `pyproject.toml`/`package.json`/`Makefile`; a documentação técnica (`TDD.md` ou equivalente) |
| Teste rápido contra completo | Marcadores/filtros da stack (ex.: `pytest -m "not slow"`). No CI vale o completo |
| Checagem extra de cobertura | Verificador do projeto, se existir (procure em scripts, Makefile, manifesto ou CI) |
| Sistemas operacionais | Onde o produto roda (instaladores, caminhos, binários por plataforma). Se roda em mais de um, pergunte se o CI deve testar neles |
| Workflow de release | Arquivo em `.github/workflows/` disparado por `push` de tags |

**Pré-requisito desta skill: uma suíte de testes existente.** Antes do resto, procure comando de teste
(CI, Makefile, manifesto ou script) e arquivo de teste. Se não houver nenhum,
alerte que o projeto não possui testes, que não foi possível validar o
funcionamento e que esta skill depende de uma suíte. Encerre. Não gere
workflow nem regra.

Condições para seguir:

- `viewerPermission` precisa ser `ADMIN` para criar a regra da branch. Sem isso,
  gere os workflows e entregue o pedido de proteção pronto (passo 7) para quem for
  administrador.
- Em repositório **privado**, regras de branch exigem um plano do GitHub que as
  inclua (Pro, Team ou Enterprise). Se a chamada recusar, informe e deixe o
  workflow pronto.

### 2. Conferir workflows e regras existentes

```bash
ls .github/workflows
gh api repos/{owner}/{repo}/rulesets
gh api repos/{owner}/{repo}/branches/<principal>/protection   # 404 = sem proteção clássica
```

| Situação | Ação |
|----------|------|
| Já existe CI de pull request que roda os testes e a branch já exige esse CI verde | Os guardrails já foram gerados. Diga isso e encerre. Esta skill roda uma vez |
| Já existe CI de pull request | Não crie outro. Mostre o que falta (testes? tipos? cobertura?) e proponha só o acréscimo |
| Já existe ruleset ou proteção clássica na branch | Mostre as regras e pergunte se quer **acrescentar** a exigência do CI ou deixar como está |
| Nada | Siga o fluxo completo |

### 3. Confirmar o plano

Antes de gravar, mostre e aguarde confirmação:

```markdown
## Guardrails em <dono/repositório> (branch <principal>)

- **CI do pull request:** `.github/workflows/ci.yml` — job `ci`
  (<lint> · <tipos> · <testes> · <checagem extra>) em <sistemas>
- **Release:** <o ci.yml é reaproveitado pelo workflow de release | passo de testes
  acrescentado ao job `check`>, antes do build
- **Regra da branch:** ruleset "Guardrails <principal>" — PR obrigatório,
  <n> aprovação(ões), check `ci` verde, sem push direto, sem force push
- **Regra das tags de release:** <sim | não> (impede apagar ou mover tags `v*`)
- **Requer admin:** <você é admin | peça ao admin com o texto do passo 7>
```

Pergunte também: quantas aprovações exigir (padrão **1**; `0` se trabalha só), e se
quem é admin pode contornar a regra (padrão **não**, para valer para todos).

### 4. Gerar o workflow de CI do pull request

Crie `.github/workflows/ci.yml`. O job tem um **nome fixo e estável** (`ci`): é
esse nome que a regra da branch exige. Reaproveite as versões das ações que o
repositório já usa nos outros workflows.

```yaml
name: CI

on:
  pull_request:
    branches: [<principal>]
  workflow_call:        # a release reaproveita este mesmo CI

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    name: ci
    runs-on: {{SISTEMA}}
    steps:
      - uses: actions/checkout@v4

      {{SETUP_DA_STACK_COM_CACHE}}

      - name: Instalar dependências
        run: {{INSTALAR}}

      - name: Lint
        run: {{LINT}}

      - name: Tipos
        run: {{TIPOS}}

      - name: Testes
        run: {{TESTES}}

      - name: Cobertura dos critérios de aceite
        run: {{CHECAGEM_EXTRA}}
```

- Remova os passos que o projeto não tem (sem tipos, sem checagem extra).
- **Nenhum teste coletado** deve falhar o job: não mascare o código de saída
  do runner. Só aceite exceção explícita do usuário e documente a limitação.
- **Vários sistemas:** troque `runs-on` por `strategy.matrix.os` e mantenha o
  `name: ci` no job; a regra passa a exigir `ci (<sistema>)` para cada um. Ajuste
  o nome exigido no passo 7.
- A checagem de cobertura entra como passo comum. Se o projeto ainda trata
  cenário sem teste como aviso, não use `--strict`.

### 5. Ligar o portão de testes à release

Se houver workflow de release e o usuário quiser protegê-lo, exija testes
verdes antes de publicar. Sem workflow, pule esta etapa; não crie release.
Prefira **uma definição só**:
reaproveitar o `ci.yml` pelo `workflow_call`.

No workflow de release, acrescente um job e faça o build depender dele:

```yaml
jobs:
  tests:
    uses: ./.github/workflows/ci.yml

  build:
    needs: [check, tests]   # mantenha os `needs` que já existiam
```

Mostre o diff e aguarde confirmação. Se o `check` da release já roda lint e tipos,
o `ci.yml` os repete: aceite a repetição (barata) ou, se o usuário preferir,
remova esses passos do `check` e deixe só a validação de versão. Se o workflow de
release não puder chamar outro (por exemplo, usa `workflow_dispatch` com tag
específica), acrescente os passos de teste direto ao job `check`.

### 6. Publicar o workflow antes de proteger a branch

Uma regra que exige um check que **nunca rodou** deixa todo pull request travado
em "Expected — Waiting for status". Por isso, a ordem é:

1. Os workflows entram na branch principal por um pull request normal (a skill
   `versionar` cuida do commit e do push; esta skill não commita nem faz push).
2. O `ci` roda ao menos uma vez e fica verde.
3. **Só então** crie a regra (passo 7).

Se o usuário quiser a regra agora mesmo, avise do risco e só siga com a
confirmação dele.

### 7. Criar a regra de proteção

Monte o ruleset e mostre o JSON e o comando antes de rodar:

```bash
gh api repos/{owner}/{repo}/rulesets --method POST --input - <<'JSON'
{
  "name": "Guardrails <principal>",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request", "parameters": {
        "required_approving_review_count": <n>,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true } },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [ { "context": "ci" } ] } }
  ]
}
JSON
```

- `bypass_actors` vazio: a regra vale para todos, inclusive admins. Se o usuário
  pediu que admins contornem, acrescente o papel `RepositoryRole` de admin.
- Com `0` aprovações, o `pull_request` continua exigindo PR, só não exige revisão.
- **Tags de release** (opcional, se o usuário aceitou): um segundo ruleset com
  `"target": "tag"`, `"ref_name": { "include": ["refs/tags/v*"] }` e as regras
  `deletion` e `non_fast_forward`, para ninguém apagar nem mover uma versão
  publicada.
- **Sem permissão de admin:** não rode. Entregue ao usuário o JSON acima e o
  texto para o administrador: "Criar ruleset na branch `<principal>` exigindo pull
  request, `<n>` aprovação(ões) e o check `ci`, sem push direto".

### 8. Validar

- Valide a sintaxe do workflow: `actionlint` se estiver instalado; senão, confira
  que o YAML carrega com um parser YAML da stack do projeto.
- Rode **localmente** cada comando do job (lint, tipos, testes, checagem extra) e
  mostre o resultado. Se falharem, o repositório é que tem problema: informe, o
  workflow está certo.
- Depois de criada a regra: `gh api repos/{owner}/{repo}/rulesets` e confirme
  `enforcement: active` e o check `ci` na lista.
- O teste real é um pull request: abra um de teste (só com a confirmação do
  usuário) e confira que o merge fica bloqueado com o `ci` vermelho e liberado com
  o `ci` verde.

### 9. Relatar

```markdown
# Guardrails configurados

- **CI do pull request:** .github/workflows/ci.yml → <resultado local dos comandos>
- **Release:** <reaproveita o ci.yml | testes no job check>, antes do build
- **Regra da branch:** <criada e ativa | pendente: falta o admin | pendente: aguardando o primeiro run do ci>
- **Regra das tags:** <criada | não>
- **Não cobre:** quem é admin e foi liberado a contornar; commits que entram sem pull
  request enquanto a regra não estiver ativa
```

## Remover

Se o usuário pedir para desligar a proteção: liste os rulesets
(`gh api repos/{owner}/{repo}/rulesets`), mostre o que será apagado e, com a
confirmação, rode `gh api repos/{owner}/{repo}/rulesets/<id> --method DELETE` só
nos rulesets com o nome "Guardrails". Não apague regras que a skill não criou.

## Em caso de falha

- Falha antes de gravar: nada mudou. Explique o estado e a correção.
- `gh` sem autenticação ou sem o escopo necessário: peça `gh auth login` (ou
  `gh auth refresh -s admin:repo_hook`) e tente de novo; não use token de outra
  fonte.
- Chamada recusada por plano ou permissão: informe o motivo exato e entregue o
  pedido pronto para o administrador (passo 7).
