---
name: publicar-release
description: >-
  Gera uma release do projeto: commita todas as mudanças pendentes em commits
  separados por assunto e funcionalidade, sobe a versão no manifesto, cria o
  commit e a tag vX.Y.Z e envia ao remoto para disparar o workflow de
  publicação. Use quando o usuário pedir para gerar, criar, cortar ou publicar
  uma release, versão ou tag, ou para commitar tudo agrupado por assunto.
---

# Gerar Release

Transforma o working tree atual em commits coesos, sobe a versão e publica a tag
que dispara o workflow de release do repositório. Explicações ao usuário em
**português (Brasil)**; mensagens de commit e de tag em **inglês**.

Nada aqui é específico de um projeto: branch, checagens, arquivo de versão e
workflow são **descobertos** no repositório (passo 1). Se algo não puder ser
descoberto, pergunte em vez de supor.

## Fluxo

```
Progresso:
- [ ] 1. Descobrir o contexto do repositório
- [ ] 2. Pré-checagens
- [ ] 3. Oferecer atualizar a documentação
- [ ] 4. Inventariar mudanças
- [ ] 5. Agrupar por assunto
- [ ] 6. Definir a versão
- [ ] 7. Confirmar o plano com o usuário
- [ ] 8. Commitar os grupos
- [ ] 9. Commit de release e tag
- [ ] 10. Enviar e relatar
- [ ] 11. Oferecer acompanhar a publicação
```

### 1. Descobrir o contexto

| Dado | Onde descobrir |
|------|----------------|
| Nome do projeto | Manifesto (`[project].name`, `"name"`, `<AssemblyName>`…) ou nome do repositório |
| Arquivo de versão | Manifesto que declara a versão (`pyproject.toml`, `package.json`, `*.csproj`/`Directory.Build.props`, `Cargo.toml`…). Se houver mais de um, o que o workflow de release valida |
| Host do remoto | `git remote get-url origin`: `github.com` → GitHub (`gh`); outro host → o CLI do host, se instalado (`glab`, `az pipelines`), senão peça ao usuário onde acompanhar o pipeline |
| Pipeline de release | Arquivo do CI disparado por `push` de tag (GitHub: `.github/workflows/` com `tags: ['v*']`; GitLab: `.gitlab-ci.yml`; Azure DevOps: `azure-pipelines.yml`) |
| Checagens obrigatórias | Passos de lint, tipos, build e validação de versão desse workflow; complemente com a documentação técnica (`TDD.md` ou equivalente) |
| Padrão de mensagens | `git log --format=%s -30`: commits de release anteriores e escopos usados |
| Arquivos locais e segredos | `.gitignore` e a seção de configuração/segurança da documentação técnica |

### 2. Pré-checagens

```bash
git branch --show-current
git fetch origin --tags
git status -sb                     # não pode estar atrás do remoto
git tag --sort=-v:refname | head -1
```

- Atrás do remoto, com merge/rebase em andamento ou conflito: pare e informe a
  ação corretiva. Não faça `pull`, `rebase` nem
  `reset` por conta própria.
- Rode localmente as checagens que o workflow de release roda antes de compilar
  (lint, tipos, validações) e os testes do projeto (ex.: `pytest`). Se falharem,
  mostre os erros e pare — release não sai com checagem ou teste quebrado.
  "Nenhum teste coletado" não é falha.
- Se existir `BDD.md` (índice) com a pasta `bdd/`, rode o verificador de cobertura do
  projeto (procure em scripts, Makefile, manifesto ou CI). ID inexistente para a release. Mostre ao
  usuário os cenários sem teste e o checklist dos cenários `@manual`, e peça
  que confirme o checklist antes de seguir.

### 3. Oferecer atualizar a documentação

Pergunte se o usuário quer atualizar a documentação do projeto antes da
release, para que ela entre nos commits e na tag. Se não, siga para o passo 4.

Se sim:

1. Procure uma skill de atualização de documentação, priorizando as do
   repositório e depois as globais (ex.: `atualizar-docs`). Se
   encontrar, leia o `SKILL.md` e siga-o.
2. Se não encontrar, siga o `AGENTS.md`: use a tabela de documentação de
   referência para saber qual documento cobre cada assunto, compare com o
   código e atualize só o que mudou, sem duplicar regras entre documentos, em
   português (Brasil).
3. As mudanças de documentação entram no inventário do passo 4 e viram o grupo
   `docs` (passo 5).

### 4. Inventariar mudanças

```bash
git status --porcelain --untracked-files=all
git diff --stat
git diff
git log --oneline "$(git describe --tags --abbrev=0)"..HEAD
```

- Leia o diff completo de cada arquivo e os arquivos novos por inteiro.
- **Nunca commitar:** caches, artefatos de build, bancos locais, segredos e
  configuração local (`.env*`, chaves, tokens, arquivos que a documentação
  técnica declare como locais). Se algum aparecer como rastreável, avise e
  sugira ajustar o `.gitignore`.
- Commits já existentes desde a última tag entram na release como estão; não os
  reescreva.

### 5. Agrupar por assunto

Cada grupo vira **um commit** com uma única intenção. Critérios, nesta ordem:

1. **Funcionalidade:** tudo que entrega a mesma capacidade (núcleo + adaptadores
   de entrega + docs dessa capacidade) fica junto.
2. **Assunto técnico:** correções, refatorações, build/CI, instalação, skills e
   instruções de agente, cada um em seu grupo.
3. **Documentação geral** (`PRD.md`, `TDD.md`, `README.md` ou equivalentes) que
   não pertence a uma funcionalidade específica fica em um grupo `docs` próprio.

Regras:

- A unidade padrão é o arquivo. Se um arquivo mistura assuntos claramente
  independentes, separe por hunk sem modo interativo:
  `git diff -- <arq> > /tmp/p.patch`, edite o patch mantendo só os hunks do
  grupo e aplique com `git apply --cached /tmp/p.patch`. Se os hunks forem
  interdependentes, mantenha o arquivo no grupo dominante.
- Cópias da mesma skill em pastas de ferramentas diferentes (`.claude/skills/X`,
  `.agents/skills/X`) vão no mesmo commit.
- Não altere locais de versão nos grupos se a única mudança for a versão — ela
  pertence ao commit de release (passo 9).
- Ordem dos commits: dependências antes de dependentes (núcleo → adaptadores →
  build/CI → docs), para que cada commit faça sentido sozinho.

#### Formato da mensagem

[Conventional Commits](https://www.conventionalcommits.org/), em inglês, modo imperativo:

```
<type>(<scope>): <summary em até 72 caracteres, sem ponto final>

- <o que mudou e por quê, um item por mudança relevante>
- <...>
```

| Tipo | Uso |
|------|-----|
| `feat` | Capacidade nova ou ampliada visível ao usuário |
| `fix` | Correção de comportamento |
| `refactor` | Mudança interna sem efeito visível |
| `perf` | Desempenho |
| `build` / `ci` | Empacotamento, scripts de build, workflows |
| `docs` | Documentação |
| `chore` | Skills, instruções de agente, config de ferramentas |

O escopo é a área do código afetada: o nome do módulo ou pacote de primeiro
nível (ex.: `core`, `cli`, `api`, `config`), ou `install`, `release`, `agents`.
Reaproveite os escopos já usados no histórico.

### 6. Definir a versão

A versão vive no arquivo de versão descoberto no passo 1; a tag é `v<versão>`.
Use a versão pedida pelo usuário; senão aplique SemVer sobre a última tag. Se o
manifesto já declara uma versão maior que a última tag (por exemplo, subida pela
skill `commitar`), reutilize-a; não suba de novo.

- **major:** quebra de contrato (capacidade, parâmetro, chave de configuração ou
  comando removido/renomeado).
- **minor:** algum `feat`.
- **patch:** só `fix`, `perf`, `refactor`, `build`, `ci`, `docs`, `chore`.

A nova tag não pode existir (`git tag -l vX.Y.Z` vazio, local e remoto).

### 7. Confirmar o plano

#### Verificar a branch

A branch atual é **sensível** quando se chama `main` ou `develop`, ou quando
contém `release` no nome (sem diferenciar maiúsculas). Fora desses casos, siga
para o plano.

Se for sensível, pergunte ao usuário:

- **Subir mesmo assim** na branch atual.
- **Digitar uma branch:** valide com `git check-ref-format --branch <nome>`. Se
  ela existir, `git switch <nome>`; senão, `git switch -c <nome>`.
- **Gerar uma branch:** `git switch -c <nome>`, com um nome bem curto e ligado
  ao que foi implementado: `<tipo>/<1 a 3 palavras>` em inglês e kebab-case,
  até 30 caracteres, com o tipo do grupo principal (ex.: `feat/pr-step`,
  `fix/cli-encoding`). O nome não pode existir local nem remotamente
  (`git ls-remote --heads origin <nome>`).

As mudanças não commitadas acompanham a troca de branch. Se o `git switch`
recusar por conflito, pare e informe; não use `--force`, `stash` nem `reset`
por conta própria.

#### Mostrar o plano

Antes de qualquer `git add`, mostre e **aguarde confirmação** (pule só se o
usuário já tiver pedido para seguir direto):

```markdown
## Release vX.Y.Z (<major|minor|patch>, anterior vA.B.C) em <branch>

### Commits
1. `feat(core): ...` — arquivo_a, arquivo_b
2. `fix(cli): ...` — arquivo_c
3. `docs: ...` — PRD.md, TDD.md

### Fora da release
- <arquivos ignorados e motivo>
```

### 8. Commitar os grupos

Para cada grupo, na ordem do plano:

```bash
git add -- <arquivos do grupo>      # nunca git add -A / git add .
git diff --cached --stat            # confira que só o grupo está no stage
git commit -F /tmp/msg.txt          # mensagem com corpo, escrita em arquivo
```

- Não use `--no-verify` nem `--amend`. Se um hook falhar, corrija a causa e crie
  o commit de novo.
- Ao final, `git status --porcelain` deve listar só o que foi excluído de propósito.

### 9. Commit de release e tag

1. Troque a versão em **todos** os locais que a carregam, não só no manifesto:
   `git grep -n "<versão atual>"` em docs, instaladores, specs, protótipos e
   exemplos (ignore changelog, notas de tag e lockfiles; regenere estes com a
   ferramenta do projeto). A versão da release é a fonte da verdade. Se o
   repositório tiver validação de versão (script chamado pelo workflow de
   release), rode-a.
2. Commit só com os arquivos de versão, seguindo o padrão de release do histórico.
   Sem padrão anterior, use:

```
Release X.Y.Z: <resumo em uma frase do principal ganho da release>.
```

3. Tag anotada com as notas agrupadas a partir dos commits desde a última tag:

```bash
git tag -a vX.Y.Z -F /tmp/tag.txt
```

```
<Nome do projeto> vX.Y.Z

Features
- <summary> (<hash curto>)

Fixes
- <summary> (<hash curto>)

Other
- <summary> (<hash curto>)
```

Omita seções vazias.

### 10. Enviar e relatar

Os comandos de acompanhamento abaixo são do GitHub (`gh`). Em outro host, use o
CLI equivalente, se instalado, ou diga ao usuário onde acompanhar o pipeline.

```bash
git push origin <branch>            # sem upstream: git push -u origin <branch>
git push origin vX.Y.Z
gh run list --workflow <arquivo do workflow> --limit 1   # GitHub
```

Se não houver workflow de release, informe que a tag foi enviada e que nada foi
publicado automaticamente; ofereça criar a release (GitHub: `gh release create`; outro host: o CLI ou a
tela do host).

Relate ao usuário:

```markdown
# Release vX.Y.Z publicada

- **Commits:** <n> (<lista de assuntos>)
- **Tag:** vX.Y.Z → <hash curto>
- **Workflow:** <link do run ou "disparado">
- **Testes:** <n passaram | nenhum teste> · **BDD:** <x/y cenários com teste, checklist manual confirmado>
- **Fora da release:** <arquivos e motivo, se houver>
```

### 11. Oferecer acompanhar a publicação

Se houver workflow de release, pergunte se o usuário quer que você acompanhe a
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

- Falha antes do push: nada saiu da máquina. Explique o estado e a correção;
  não desfaça commits sem pedir.
- Push da tag rejeitado ou pipeline com erro: mostre o log
  (GitHub: `gh run view <id> --log-failed`). Não apague nem recrie tags publicadas sem
  autorização. Se o workflow aceitar `workflow_dispatch` com a tag, ofereça
  republicar por ele (GitHub: `gh workflow run <arquivo> -f tag=vX.Y.Z`).
