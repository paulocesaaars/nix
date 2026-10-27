---
name: gerar-release
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
- [ ] 3. Inventariar mudanças
- [ ] 4. Agrupar por assunto
- [ ] 5. Definir a versão
- [ ] 6. Confirmar o plano com o usuário
- [ ] 7. Commitar os grupos
- [ ] 8. Commit de release e tag
- [ ] 9. Enviar e relatar
```

### 1. Descobrir o contexto

| Dado | Onde descobrir |
|------|----------------|
| Branch de release | `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`; sem `gh`, `git symbolic-ref refs/remotes/origin/HEAD` |
| Nome do projeto | Manifesto (`[project].name`, `"name"`, `<AssemblyName>`…) ou nome do repositório |
| Arquivo de versão | Manifesto que declara a versão (`pyproject.toml`, `package.json`, `*.csproj`/`Directory.Build.props`, `Cargo.toml`…). Se houver mais de um, o que o workflow de release valida |
| Workflow de release | Arquivo em `.github/workflows/` disparado por `push` de tags (`tags: ['v*']`) |
| Checagens obrigatórias | Passos de lint, tipos, build e validação de versão desse workflow; complemente com a documentação técnica (`TDD.md` ou equivalente) |
| Padrão de mensagens | `git log --format=%s -30`: commits de release anteriores e escopos usados |
| Arquivos locais e segredos | `.gitignore` e a seção de configuração/segurança da documentação técnica |

### 2. Pré-checagens

```bash
git branch --show-current          # deve ser a branch de release
git fetch origin --tags
git status -sb                     # não pode estar atrás do remoto
git tag --sort=-v:refname | head -1
```

- Fora da branch de release, atrás do remoto, com merge/rebase em andamento ou
  conflito: pare e informe a ação corretiva. Não faça `pull`, `rebase` nem
  `reset` por conta própria.
- Rode localmente as checagens que o workflow de release roda antes de compilar
  (lint, tipos, validações). Se falharem, mostre os erros e pare — release não
  sai com checagem quebrada.

### 3. Inventariar mudanças

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

### 4. Agrupar por assunto

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
- Não altere o arquivo de versão nos grupos se a única mudança for a versão —
  ela pertence ao commit de release (passo 8).
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

### 5. Definir a versão

A versão vive no arquivo de versão descoberto no passo 1; a tag é `v<versão>`.
Use a versão pedida pelo usuário; senão aplique SemVer sobre a última tag:

- **major:** quebra de contrato (capacidade, parâmetro, chave de configuração ou
  comando removido/renomeado).
- **minor:** algum `feat`.
- **patch:** só `fix`, `perf`, `refactor`, `build`, `ci`, `docs`, `chore`.

A nova tag não pode existir (`git tag -l vX.Y.Z` vazio, local e remoto).

### 6. Confirmar o plano

Antes de qualquer `git add`, mostre e **aguarde confirmação** (pule só se o
usuário já tiver pedido para seguir direto):

```markdown
## Release vX.Y.Z (<major|minor|patch>, anterior vA.B.C)

### Commits
1. `feat(core): ...` — arquivo_a, arquivo_b
2. `fix(cli): ...` — arquivo_c
3. `docs: ...` — PRD.md, TDD.md

### Fora da release
- <arquivos ignorados e motivo>
```

### 7. Commitar os grupos

Para cada grupo, na ordem do plano:

```bash
git add -- <arquivos do grupo>      # nunca git add -A / git add .
git diff --cached --stat            # confira que só o grupo está no stage
git commit -F /tmp/msg.txt          # mensagem com corpo, escrita em arquivo
```

- Não use `--no-verify` nem `--amend`. Se um hook falhar, corrija a causa e crie
  o commit de novo.
- Ao final, `git status --porcelain` deve listar só o que foi excluído de propósito.

### 8. Commit de release e tag

1. Troque a versão no arquivo de versão. Se o repositório tiver validação de
   versão (script chamado pelo workflow de release), rode-a.
2. Commit só com o arquivo de versão, seguindo o padrão de release do histórico.
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

### 9. Enviar e relatar

```bash
git push origin <branch de release>
git push origin vX.Y.Z
gh run list --workflow <arquivo do workflow> --limit 1
```

Se não houver workflow de release, informe que a tag foi enviada e que nada foi
publicado automaticamente; ofereça criar a release com `gh release create`.

Relate ao usuário:

```markdown
# Release vX.Y.Z publicada

- **Commits:** <n> (<lista de assuntos>)
- **Tag:** vX.Y.Z → <hash curto>
- **Workflow:** <link do run ou "disparado">
- **Fora da release:** <arquivos e motivo, se houver>
```

## Em caso de falha

- Falha antes do push: nada saiu da máquina. Explique o estado e a correção;
  não desfaça commits sem pedir.
- Push da tag rejeitado ou workflow com erro: mostre o log
  (`gh run view <id> --log-failed`). Não apague nem recrie tags publicadas sem
  autorização. Se o workflow aceitar `workflow_dispatch` com a tag, ofereça
  republicar por ele (`gh workflow run <arquivo> -f tag=vX.Y.Z`).
