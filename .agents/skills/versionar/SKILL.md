---
name: versionar
description: >-
  Commita todas as mudanças pendentes em commits separados por assunto e envia para
  a main do remoto. Não sobe versão, cria tags, publica releases ou abre PRs.
  Use quando o usuário pedir esse fluxo de commits e envio para a main.
  Um pedido apenas de commit não autoriza push.
---

# Commitar e enviar para a main

Organize as mudanças pendentes por assunto e envie os commits para a `main`.
Mensagens de commit e explicações em português (Brasil). A autorização para
este fluxo inclui o push na main, sem nova confirmação. Um pedido limitado
a commits deve ser respeitado sem push.

Ao invocar esta skill, o usuário autoriza incluir todas as mudanças pendentes:
adições, alterações, renomeações e exclusões, inclusive mudanças anteriores
à sessão. Não peça confirmação adicional pelo volume de arquivos ou por
exclusões já presentes na árvore de trabalho. Não crie novas exclusões para
limpar o projeto. Respeite um escopo mais restrito quando o usuário o indicar.

Não aumente a versão, crie tags, releases ou pull requests. Não ofereça nem
execute outras skills ao terminar.

## 1. Descobrir o contexto e validar

- Leia o `AGENTS.md`, o `HARNESS.md` e as instruções aplicáveis. Consulte a
  documentação técnica para checagens e segurança; ignore documentos vazios
  ou ausentes.
- Confira branch, remotos, working tree e stage. Use `origin` quando existir;
  se o remoto for ambíguo, pergunte.
- Descubra e execute as checagens de lint e tipos exigidas pelo projeto.
  Se falharem ou não puderem executar, informe e pare.
- Testes e cobertura, inclusive BDD, são opcionais e não condicionam commits
  nem push. Execute-os apenas quando o usuário pedir e relate o resultado,
  sem bloquear o versionamento por falha ou ausência de suíte.
- Se um comando agregado incluir testes, execute lint e tipos separadamente.
- Execute `git fetch <remoto>` e confirme a existência de `<remoto>/main`.
  Se não existir, pare e informe.
- Pare em caso de conflito ou operação Git em andamento. Não use reset,
  stash, rebase ou force push para contornar impedimentos.

## 2. Preparar a main

- Se estiver em outra branch, verifique seus commits exclusivos em relação
  a `<remoto>/main`. Se houver, pare e informe quais seriam incluídos;
  não os publique implicitamente.
- Caso contrário, troque para a main local ou crie sua cópia local rastreando
  `<remoto>/main`, preservando as mudanças pendentes. Se a troca for recusada,
  pare e informe.
- Confirme que a main contém `<remoto>/main`. Se estiver apenas atrás,
  atualize com `git merge --ff-only <remoto>/main`, preservando as mudanças.
  Se houver divergência ou impedimento, pare e informe.
- Se a troca ou atualização alterar o conteúdo validado, repita as checagens.

## 3. Inventariar e agrupar por assunto

Inspecione `git status --porcelain --untracked-files=all`, `git diff`,
`git diff --cached` e os arquivos novos por inteiro.

- Exclua segredos, caches, builds e configurações locais conforme as regras do
  projeto. Não exclua automaticamente arquivos de exemplo versionáveis.
- Inclua todas as demais mudanças pendentes, inclusive exclusões. As exceções
  acima significam deixar arquivos fora dos commits, não apagá-los do disco.
- Cada funcionalidade, correção ou assunto técnico independente vira um commit.
  Documentação específica acompanha a funcionalidade; documentação geral,
  build/CI, refatorações e skills ficam em grupos próprios quando independentes.
- Cópias da mesma skill em ferramentas diferentes ficam no mesmo grupo.
- Separe assuntos independentes no mesmo arquivo por hunks com patch revisado
  e `git apply --cached`. Mantenha mudanças interdependentes juntas.
- Ordene os grupos pelas dependências.
- Preserve commits existentes; não use amend nem reescreva o histórico.
  Confira também os commits locais da main ainda não enviados e inclua-os
  no resumo do envio.

Mostre os grupos e os arquivos excluídos, sem exigir confirmação adicional
quando o fluxo completo já estiver autorizado.

## 4. Commitar

Siga o padrão de mensagens do histórico. Na ausência de padrão, use Conventional
Commits, com tipo e escopo em inglês e resumo em português no infinitivo:

```text
fix(api): corrigir validação da entrada
```

Para cada grupo:

1. Prepare só seus arquivos ou hunks, com caminhos explícitos. Não use
   `git add .` nem `git add -A`.
2. Confira o diff completo do stage. Reorganize conteúdo já staged de outros
   grupos sem alterar o conteúdo dos arquivos.
3. Escreva a mensagem em arquivo temporário e use `git commit -F <arquivo>`.
4. Respeite os hooks. Se falharem, pare e informe; não use `--no-verify`
   nem corrija arquivos fora do escopo autorizado.

Não crie commits vazios. Confira que só restaram mudanças excluídas
intencionalmente. Sem mudanças nem commits pendentes, informe que não há
nada a publicar.

## 5. Enviar e relatar

Confirme que a branch atual é main e execute:

```bash
git push <remoto> main:main
```

Se o push for rejeitado, informe o erro e o estado local. Não contorne
proteções, use force push ou abra PR automaticamente.

Relate o destino, hashes curtos e assuntos dos commits enviados, resultados
das checagens e arquivos excluídos. Em caso de falha, diferencie commits
criados localmente de commits efetivamente publicados.
