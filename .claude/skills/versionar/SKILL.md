---
name: versionar
description: >-
  Commita todas as mudanças pendentes em commits separados por assunto e
  funcionalidade, sobe a versão do software em um commit próprio e envia a
  branch ao remoto, sem criar tag nem publicar release. Ao final, oferece atualizar a documentação do projeto e
  abrir o pull request. No início, roda os testes. Sem suíte, avisa que não
  foi possível validar o funcionamento e segue. Use
  quando o usuário pedir esse fluxo completo. Um pedido apenas de commit não
  autoriza subir versão nem enviar a branch; pergunte antes de executar essas etapas.
---

# Gerar Commits

Transforma o working tree atual em commits coesos e envia a branch ao remoto.
Sobe a versão do software em um commit próprio, mas **não** cria tag e **não**
publica release. Explicações
ao usuário e mensagens de commit em **português (Brasil)**.

Nada aqui é específico de um projeto: branch, checagens e padrão de mensagens
são **descobertos** no repositório (passo 1). Se algo não puder ser descoberto,
pergunte em vez de supor.

Se o usuário pedir apenas commit, execute somente os commits autorizados;
não altere versão nem faça push sem pedido ou confirmação. Quando outra skill
oferecer este fluxo, explicite que ele inclui versão e envio antes de aceitá-lo.

## Fluxo

```
Progresso:
- [ ] 1. Descobrir o contexto do repositório
- [ ] 2. Pré-checagens
- [ ] 3. Inventariar mudanças
- [ ] 4. Agrupar por assunto
- [ ] 5. Definir a versão
- [ ] 6. Confirmar o plano com o usuário
- [ ] 7. Commitar os grupos e a versão
- [ ] 8. Enviar e relatar
- [ ] 9. Oferecer atualizar a documentação
- [ ] 10. Oferecer abrir o PR
```

### 1. Descobrir o contexto

| Dado | Onde descobrir |
|------|----------------|
| Branch atual e remoto | `git branch --show-current`; `git rev-parse --abbrev-ref @{u}` (vazio se não houver upstream) |
| Host do remoto | `git remote get-url origin`: `github.com` → GitHub (`gh`); outro host (GitLab, Azure DevOps, Bitbucket…) → o CLI do host, se instalado (`glab`, `az repos`), senão os passos manuais do passo 10 |
| Checagens obrigatórias | Passos de lint e tipos do pipeline de CI do projeto (ex.: `.github/workflows/`, `.gitlab-ci.yml`, `azure-pipelines.yml`); complemente com a documentação técnica (`TDD.md` ou equivalente) |
| Padrão de mensagens | `git log --format=%s -30`: tipos e escopos usados |
| Arquivos locais e segredos | `.gitignore` e a seção de configuração/segurança da documentação técnica |

### 2. Pré-checagens

A primeira ação é rodar os testes. Descubra o comando (CI, Makefile, manifesto
ou script) e execute-o.

- Suíte passando: siga.
- Suíte falhando: mostre os erros e pare. Não commite com teste quebrado.
- Projeto sem testes (nenhum comando, nenhum arquivo de teste, ou o runner
  não coletou nenhum): alerte que o projeto não possui testes e que não foi
  possível validar o funcionamento. Não pare por isso.

```bash
git fetch origin
git status -sb                     # não pode estar atrás do remoto
```

- Atrás do remoto, com merge/rebase em andamento ou conflito: pare e informe a
  ação corretiva. Não faça `pull`, `rebase` nem `reset` por conta própria.
- Rode localmente as checagens descobertas (lint, tipos). Se falharem, mostre
  os erros e pare — não commite com checagem quebrada.
- Se o projeto tem `BDD.md` preenchido (índice) com a pasta `bdd/` e um verificador de
  cobertura (procure em scripts, Makefile, manifesto ou CI), rode-o: ID inexistente é erro e para;
  cenário sem teste é aviso e entra no relatório.

### 3. Inventariar mudanças

```bash
git status --porcelain --untracked-files=all
git diff --stat
git diff
```

- Leia o diff completo de cada arquivo e os arquivos novos por inteiro.
- **Nunca commitar:** caches, artefatos de build, bancos locais, segredos e
  configuração local (`.env*`, chaves, tokens, arquivos que a documentação
  técnica declare como locais). Se algum aparecer como rastreável, avise e
  sugira ajustar o `.gitignore`.
- Commits já existentes e ainda não enviados ficam como estão; não os reescreva.

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
- A mudança de versão não entra nos grupos: ela vira o último commit (passo 5).
- Ordem dos commits: dependências antes de dependentes (núcleo → adaptadores →
  build/CI → docs), para que cada commit faça sentido sozinho.

#### Formato da mensagem

[Conventional Commits](https://www.conventionalcommits.org/): o tipo e o escopo no
formato padrão (`feat`, `fix`…) e o resumo e o corpo em **português (Brasil)**,
com o verbo no infinitivo (ex.: adicionar, corrigir, remover):

```
<tipo>(<escopo>): <resumo em até 72 caracteres, sem ponto final>

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
nível (ex.: `core`, `cli`, `api`, `config`), ou `install`, `agents`.
Reaproveite os escopos já usados no histórico.

### 5. Definir a versão

Descubra **todos** os locais que carregam a versão do software:

- o manifesto que o workflow de release valida (`pyproject.toml`, `package.json`,
  `*.csproj`/`Directory.Build.props`, `Cargo.toml`…);
- outras ocorrências escritas à mão: `git grep -n "<versão atual>"` em docs,
  instaladores, specs, protótipos e exemplos. Ignore histórico (changelog, notas
  de tag) e arquivos gerados (lockfiles: regenere com a ferramenta do projeto).

A versão da release (manifesto = tag `vX.Y.Z`) é a **fonte da verdade**: todo
outro local a espelha, nunca o contrário.

Escolha a nova versão. Conventional Commits são indícios, não uma regra completa
do SemVer: avalie o contrato público e a compatibilidade, inclusive que em
versões 0.y.z a API pode mudar. Não classifique uma mudança só pelo tipo do commit.


- Use a versão pedida pelo usuário; senão aplique SemVer sobre a última tag
  (`git tag --sort=-v:refname | head -1`): **major** para quebra de contrato,
  **minor** se algum grupo for `feat`, **patch** nos demais casos.
- Se o manifesto já declara uma versão maior que a última tag (subida anterior
  ainda não publicada), reutilize-a; não suba de novo.
- Sem commits novos desde a última tag, não há versão a subir: informe e pule.

### 6. Confirmar o plano

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
## Commits em <branch> → <remoto/branch> (versão A.B.C → X.Y.Z)

1. `feat(core): ...` — arquivo_a, arquivo_b
2. `fix(cli): ...` — arquivo_c
3. `docs: ...` — PRD.md, TDD.md
4. `chore(release): subir versão para X.Y.Z` — <locais da versão>

### Fora dos commits
- <arquivos ignorados e motivo>
```

### 7. Commitar os grupos e a versão

Para cada grupo, na ordem do plano:

```bash
git add -- <arquivos do grupo>      # nunca git add -A / git add .
git diff --cached --stat            # confira que só o grupo está no stage
git commit -F /tmp/msg.txt          # mensagem com corpo, escrita em arquivo
```

- Não use `--no-verify` nem `--amend`. Se um hook falhar, corrija a causa e crie
  o commit de novo.
- Por último, troque a versão em todos os locais do passo 5 e rode a validação
  de versão do repositório, se houver (script do projeto ou o passo do workflow
  de release).
  Commit só com esses arquivos: `chore(release): subir versão para X.Y.Z`.
- Ao final, `git status --porcelain` deve listar só o que foi excluído de propósito.

### 8. Enviar e relatar

```bash
git push origin <branch>            # sem upstream: git push -u origin <branch>
```

**Não** crie tag, **não** crie release no host e **não** dispare pipeline de
publicação. Se o push for rejeitado, mostre o erro e a ação corretiva; não use
`--force`.

Relate ao usuário:

```markdown
# Commits enviados

- **Branch:** <branch> → <remoto/branch>
- **Commits:** <n> (<lista de assuntos com hash curto>)
- **Versão:** A.B.C → X.Y.Z (sem tag; a release publica)
- **Testes:** <n passaram | nenhum teste> · **BDD:** <x/y cenários com teste>
- **Fora dos commits:** <arquivos e motivo, se houver>
```

### 9. Oferecer atualizar a documentação

Depois do relatório, pergunte se o usuário quer atualizar a documentação do
projeto. Se não, encerre.

Se sim:

1. Procure uma skill de atualização de documentação, priorizando as do
   repositório e depois as globais (ex.: `atualizar-docs`). Se
   encontrar, leia o `SKILL.md` e siga-o.
2. Se não encontrar, siga o `AGENTS.md`: use a tabela de documentação de
   referência para saber qual documento cobre cada assunto, compare com o que
   foi commitado e atualize só o que mudou, sem duplicar regras entre
   documentos, em português (Brasil).
3. Ao terminar, pergunte se deve commitar as mudanças de documentação. Se sim,
   repita os passos 3 a 8 só com esses arquivos, sem subir a versão de novo.

### 10. Oferecer abrir o PR

Por último, pergunte se o usuário quer que você abra o pull request da branch.
Se não, encerre.

Se sim:

1. Se a branch atual for a branch padrão
   (no GitHub: `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`;
   em outro host: `git symbolic-ref --short refs/remotes/origin/HEAD`), não há
   PR a abrir: informe e encerre.
2. Se já houver PR aberto para a branch (no GitHub: `gh pr view --json url,state`; em outro host, o comando
   equivalente do CLI), mostre
   o link e encerre.
3. Monte título e corpo a partir dos commits da branch
   (`git log --format='%s%n%b' origin/<branch padrão>..HEAD`), seguindo o padrão
   de idioma e formato dos PRs anteriores (no GitHub: `gh pr list --state merged --limit 5`).
   Sem padrão, use o título no formato Conventional Commits, em português, e o corpo com um
   resumo e a lista de mudanças.
4. Crie o PR contra a branch padrão. No GitHub:

```bash
gh pr create --base <branch padrão> --head <branch> --title "<título>" --body-file /tmp/pr.md
```

   Em outro host, use o comando equivalente do CLI (`glab mr create`,
   `az repos pr create`), se estiver instalado.

Relate o link do PR. Se o CLI do host estiver indisponível ou sem autenticação,
ou se o host não tiver um CLI conhecido, informe, entregue o título e o corpo
prontos e diga como abrir o PR pela tela do host.

## Em caso de falha

- Falha antes do push: nada saiu da máquina. Explique o estado e a correção;
  não desfaça commits sem pedir.
- Push rejeitado: mostre a saída do `git push` e a ação corretiva (por exemplo,
  integrar o remoto). Não faça `pull`, `rebase` nem `--force` sem autorização.
