---
name: publicar-release
description: >-
  Publica uma release do projeto: confere que não há mudanças pendentes de
  commit, que a versão do manifesto é nova e que as checagens passam, cria a tag
  vX.Y.Z e a envia ao remoto para disparar o pipeline de publicação. Não faz
  commit nem sobe a versão: isso é da skill de commits. No início, roda os
  testes. Sem suíte, avisa que não foi possível validar o funcionamento e
  segue. Use quando o usuário
  pedir para gerar, criar, cortar ou publicar uma release, versão ou tag.
---

# Publicar Release

Cria e envia a tag que dispara o pipeline de release do repositório. **Não faz
commit e não altera arquivos**: as mudanças e a subida de versão já precisam
estar commitadas (skill `versionar`, ou o equivalente do projeto). Explicações ao
usuário e notas da tag em **português (Brasil)**.

Nada aqui é específico de um projeto: branch, checagens, arquivo de versão e
pipeline são **descobertos** no repositório (passo 1). Se algo não puder ser
descoberto, pergunte em vez de supor.

## Regras

- **Não** edite, crie nem apague arquivos do projeto, e **não** crie commits.
- **Não** publique se houver mudanças pendentes de commit (passo 2). Pare e
  mande o usuário commitar primeiro.
- A versão da release é a que o manifesto já declara. Esta skill não a altera.

## Fluxo

```
Progresso:
- [ ] 1. Descobrir o contexto do repositório
- [ ] 2. Pré-checagens (inclui a condição de não haver pendências)
- [ ] 3. Levantar o que entra na release
- [ ] 4. Conferir a versão
- [ ] 5. Confirmar o plano com o usuário
- [ ] 6. Criar a tag
- [ ] 7. Enviar e relatar
- [ ] 8. Oferecer acompanhar a publicação
```

### 1. Descobrir o contexto

| Dado | Onde descobrir |
|------|----------------|
| Nome do projeto | Manifesto (`[project].name`, `"name"`, `<AssemblyName>`…) ou nome do repositório |
| Arquivo de versão | Manifesto que declara a versão (`pyproject.toml`, `package.json`, `*.csproj`/`Directory.Build.props`, `Cargo.toml`…). Se houver mais de um, o que o workflow de release valida |
| Host do remoto | `git remote get-url origin`: `github.com` → GitHub (`gh`); outro host → o CLI do host, se instalado (`glab`, `az pipelines`), senão peça ao usuário onde acompanhar o pipeline |
| Pipeline de release | Arquivo do CI disparado por `push` de tag (GitHub: `.github/workflows/` com `tags: ['v*']`; GitLab: `.gitlab-ci.yml`; Azure DevOps: `azure-pipelines.yml`) |
| Checagens obrigatórias | Passos de lint, tipos, build e validação de versão desse pipeline; complemente com a documentação técnica (`TDD.md` ou equivalente) |
| Branch padrão | GitHub: `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`; outro host: `git symbolic-ref --short refs/remotes/origin/HEAD` |

### 2. Pré-checagens

A primeira ação é rodar os testes. Descubra o comando (CI, Makefile, manifesto
ou script) e execute-o.

- Suíte passando: siga.
- Suíte falhando: mostre os erros e pare. Release não sai com teste quebrado.
- Projeto sem testes (nenhum comando, nenhum arquivo de teste, ou o runner
  não coletou nenhum): alerte que o projeto não possui testes e que não foi
  possível validar o funcionamento. Não pare por isso.

```bash
git branch --show-current
git fetch origin --tags
git status -sb                         # estado do working tree e do remoto
git status --porcelain --untracked-files=all
git tag --sort=-v:refname | head -1
```

#### Condição: nenhuma pendência de commit

`git status --porcelain --untracked-files=all` precisa sair **vazio**. Qualquer
linha é uma pendência: arquivo modificado, no stage ou novo e não ignorado.

- Com pendência, **não publique**. Liste os arquivos, explique que a release só
  sai de um working tree limpo e peça ao usuário para rodar a skill `versionar`
  (ou o equivalente do projeto). Encerre; não ofereça commitar por aqui.
- Arquivos que o `.gitignore` já exclui não contam.
- Commits **locais ainda não enviados** não bloqueiam: eles vão ao remoto junto
  com a tag e aparecem no plano (passo 5).

Demais verificações:

- Atrás do remoto, com merge/rebase em andamento ou conflito: pare e informe a
  ação corretiva. Não faça `pull`, `rebase` nem `reset` por conta própria.
- Rode localmente as checagens que o pipeline de release roda antes de compilar
  (lint, tipos, validações). Se falharem, mostre os erros e pare — release não
  sai com checagem quebrada.
- Se `BDD.md` estiver preenchido e houver cenários em `bdd/`, rode o verificador de
  cobertura do projeto (procure em scripts, Makefile, manifesto ou CI). Um ID inexistente bloqueia a release. Mostre ao usuário os cenários sem teste e o
  checklist dos cenários `@manual`, e peça que confirme o checklist antes de
  seguir.
- Se a documentação estiver defasada, avise e sugira rodar a skill de
  atualização de documentação e depois `versionar`. Isso não bloqueia a release
  por si só.

### 3. Levantar o que entra na release

```bash
git log --oneline "$(git describe --tags --abbrev=0)"..HEAD  # se existir tag anterior
git log origin/<branch>..HEAD --oneline      # commits locais ainda não enviados
```

- Na primeira release, sem tag anterior, use `git log --oneline HEAD` para
  levantar os commits alcançáveis, valide a versão inicial do manifesto e
  apresente o plano como primeira release.
- Com tag anterior e sem commits desde ela, não há o que publicar: informe e encerre.
- Os commits entram na release como estão; não os reescreva.

### 4. Conferir a versão

A versão vive no arquivo de versão do passo 1; a tag é `v<versão>`. Esta skill
**lê** a versão, não a altera.

| Situação | Ação |
|----------|------|
| A versão do manifesto é maior que a última tag | Siga: a tag será `v<versão>` |
| A versão do manifesto é igual à da última tag | Não há versão nova. Peça ao usuário para rodar `versionar`, que sobe a versão em um commit próprio, e encerre |
| O usuário pediu uma versão diferente da do manifesto | Pare e explique: a versão sai do manifesto. Peça para rodar `versionar` com a versão desejada |
| A tag `vX.Y.Z` já existe (`git tag -l`, local e remoto) | Pare: uma tag publicada não se recria |

Confira também a compatibilidade da API pública e a versão conforme SemVer.
Os tipos de Conventional Commits são indícios, não prova de compatibilidade;
considere também as regras de versões `0.y.z` e pré-lançamentos. Como política
usual sobre os commits do passo 3: **major** para quebra de contrato (capacidade, parâmetro, chave de
configuração ou comando removido/renomeado), **minor** se houver `feat`,
**patch** nos demais casos. Se a versão do manifesto for menor do que isso exige,
avise e deixe o usuário decidir se segue ou se volta ao `versionar`.

Se o repositório tiver validação de versão (script chamado pelo pipeline de
release), rode-a com a versão do manifesto.

### 5. Confirmar o plano

#### Verificar a branch

Se a branch atual **não** for a branch padrão do repositório, avise e pergunte se
a release deve sair mesmo assim. Publicar de outra branch é raro e costuma ser
engano.

#### Mostrar o plano

Antes de criar a tag, mostre e **aguarde confirmação** (pule só se o usuário já
tiver pedido para seguir direto):

```markdown
## Release vX.Y.Z (<major|minor|patch>, anterior vA.B.C) em <branch>

- **Commits na release:** <n>
- **Commits locais a enviar junto:** <n | nenhum>
- **Pipeline que será disparado:** <arquivo | nenhum>

### Notas da tag
<prévia do texto do passo 6>
```

### 6. Criar a tag

Tag anotada, com notas dos commits desde a última tag; na primeira release,
use o histórico alcançável levantado no passo 3:

```bash
git tag -a vX.Y.Z -F /tmp/tag.txt
```

```
<Nome do projeto> vX.Y.Z

Novidades
- <resumo do commit> (<hash curto>)

Correções
- <resumo do commit> (<hash curto>)

Outros
- <resumo do commit> (<hash curto>)
```

Agrupe pelo tipo do commit: `feat` em Novidades, `fix` em Correções e os demais
em Outros. Omita seções vazias.

### 7. Enviar e relatar

Os comandos de acompanhamento abaixo são do GitHub (`gh`). Em outro host, use o
CLI equivalente, se instalado, ou diga ao usuário onde acompanhar o pipeline.

```bash
git push origin <branch>            # só se houver commits locais; sem upstream: git push -u origin <branch>
git push origin vX.Y.Z
gh run list --workflow <arquivo do workflow> --limit 1   # GitHub
```

Se não houver pipeline de release, informe que a tag foi enviada e que nada foi
publicado automaticamente; ofereça criar a release (GitHub: `gh release create`;
outro host: o CLI ou a tela do host).

Relate ao usuário:

```markdown
# Tag vX.Y.Z enviada

- **Commits:** <n> (<lista de assuntos>)
- **Tag:** vX.Y.Z → <hash curto>
- **Pipeline:** <link e estado confirmado | não identificado>
- **Release / artefatos:** <publicação confirmada | pendente | não configurada>
- **Testes:** <n passaram | nenhum teste> · **BDD:** <x/y cenários com teste, checklist manual confirmado>
```

### 8. Oferecer acompanhar a publicação

Se houver pipeline de release, pergunte se o usuário quer que você acompanhe a
publicação até o fim. Se não, encerre.

Se sim, no GitHub (em outro host, use o CLI equivalente ou peça ao usuário
para avisar quando o pipeline terminar):

```bash
gh run watch <id do run> --exit-status
gh release view vX.Y.Z              # confirma a release e os artefatos
```

- **Sucesso:** relate a conclusão, o link da release e os artefatos publicados.
- **Falha:** mostre o job e o passo que falharam (`gh run view <id> --log-failed`)
  e siga a seção "Em caso de falha".

## Em caso de falha

- Falha antes do push: nada saiu da máquina. Explique o estado e a correção. Se a
  tag local foi criada e o envio não ocorreu, ofereça apagá-la
  (`git tag -d vX.Y.Z`) só se o usuário pedir.
- Push da tag rejeitado ou pipeline com erro: mostre o log
  (GitHub: `gh run view <id> --log-failed`). Não apague nem recrie tags publicadas sem
  autorização. Se o pipeline aceitar `workflow_dispatch` com a tag, ofereça
  republicar por ele (GitHub: `gh workflow run <arquivo> -f tag=vX.Y.Z`).
