---
name: implementar-sdd
description: >-
  Conduz o desenvolvimento de uma funcionalidade pelo fluxo inteiro:
  especificar, planejar no modo de planejamento, implementar, criar os testes
  do BDD, revisar o código, commitar, atualizar a documentação e, no fim,
  commitar a documentação ou publicar a release. Para em cada aprovação que as
  skills da etapa já exigem, e também quando a revisão encontra achado crítico
  ou alto. Use quando o usuário pedir para desenvolver, implementar ou
  construir uma funcionalidade, feature ou fluxo de desenvolvimento, ou quando
  chamar implementar-sdd. Não use para dúvida, exploração, opinião ou pedido
  de uma etapa só.
---

# Implementar SDD

Conduz uma funcionalidade da especificação até a documentação commitada, com a
opção de publicar a release no fim. Explicações ao usuário em **português
(Brasil)**.

Cada etapa é uma skill que já existe. Leia o `SKILL.md` dela e siga-o. Não
reinterprete nem encurte as regras dela. Esta skill só define a ordem, o que
pula e onde o fluxo para.

## Quando começar

Comece quando o usuário pedir para desenvolver, implementar ou construir uma
funcionalidade.

Não comece em dúvida, exploração, opinião ou pedido de uma etapa só
(`especificar-feature`, `criar-testes`, `revisar-codigo`, `commitar`,
`atualizar-docs`, `publicar-release`). Nesses casos, siga só a skill pedida.

Se o usuário entregar a especificação pronta ou pedir para retomar de uma
etapa, comece nela. Não refaça etapa já concluída nesta conversa.

## Regras

- Siga o `AGENTS.md`. Em conflito, vale o `HARNESS.md`, se existir.
- Uma etapa termina antes da próxima. Não antecipe commit, documentação nem
  release.
- O plano aprovado autoriza só o que está nele. Fora isso, peça confirmação.
- Localize cada skill pelo nome nas pastas do repositório (`.claude/skills`,
  `.agents/skills`) e, se faltar, nas skills globais. Leia um
  único `SKILL.md`: as cópias são iguais. Skill ausente: pare e diga qual.
- Use a ferramenta de perguntas estruturadas quando houver opções discretas.
  Marque a recomendada com "(Recomendado)" como primeira opção.

## Fluxo

```
Progresso:
- [ ] 1. Especificar
- [ ] 2. Planejar
- [ ] 3. Implementar
- [ ] 4. Criar os testes
- [ ] 5. Revisar
- [ ] 6. Commitar o código
- [ ] 7. Atualizar a documentação
- [ ] 8. Commitar a documentação ou publicar a release
```

### 1. Especificar

Siga `especificar-feature` por inteiro, inclusive a pergunta sobre o modelo e
as decisões críticas. Não implemente nesta etapa.

### 2. Planejar

Siga o passo final de `especificar-feature`: o plano e feito com o modo de
planejamento nativo do agente, com a especificação como insumo. Não escreva o
plano no chat no lugar desse modo. Se o agente não entrar no modo sozinho,
pare e peça ao usuário para ativá-lo.

Implemente só depois que o usuário aprovar o plano. Se ele não quiser o plano,
encerre.

### 3. Implementar

No modo de implementação, entregue o plano aprovado: código de produção e o
que o plano lista, menos arquivos de teste.

Não crie nem altere teste. A skill `criar-testes` faz isso na etapa seguinte.
Não commite. Não amplie o escopo. Ambiguidade no plano: pergunte antes de
codar.

### 4. Criar os testes

Siga `criar-testes` por inteiro, inclusive a confirmação do plano. No passo em
que ela apenas sugere a revisão, não pare e não a execute: a revisão é a
etapa 5.

Se não houver cenário sem teste, siga para a revisão.

Teste falhando porque o produto não cumpre o cenário bloqueia o resto do
fluxo. Pergunte se corrige o produto agora.

- **Corrigir:** volte à etapa 3 só nessa lacuna, sem mudar cenário nem
  asserção. Rode de novo os testes que falharam. Só siga se passarem.
- **Não corrigir:** pare. O teste fica como `criar-testes` deixou.

### 5. Revisar

Siga `revisar-codigo`. O escopo é o que este fluxo mudou (`git diff`), mais os
testes criados na etapa 4. Não edite nada na revisão.

Achado **crítico** ou **alto**: pare. Mostre o relatório e não commite. Só
continue quando o usuário pedir explicitamente para corrigir. Aplique só o que
ele aceitar, depois revise de novo os arquivos tocados. Repita até não restar
crítico nem alto.

Achado **médio** ou **baixo**: registre no relatório e siga. Eles continuam
visíveis na confirmação dos commits.

### 6. Commitar o código

Siga `commitar` nos passos 1 a 8: checagens, commits por assunto, subida de
versão e envio da branch. A confirmação do plano de commits continua valendo.

Pule os passos 9 e 10. Não ofereça atualizar a documentação nem abrir pull
request: a documentação é a etapa 7, e este fluxo não abre pull request.

Checagem ou teste falhou: pare. Não siga com a documentação.

### 7. Atualizar a documentação

Siga `atualizar-docs` por inteiro.

### 8. Commitar a documentação ou publicar a release

Se a etapa 7 alterou arquivos, pergunte:

- **Commitar a documentação e encerrar** (Recomendado)
- **Commitar a documentação e publicar a release**

O commit da documentação segue os passos 3 a 8 de `commitar`, só com esses
arquivos, sem subir a versão de novo.

Se a etapa 7 não alterou nada, pergunte só:

- **Encerrar** (Recomendado)
- **Publicar a release**

Publicar segue `publicar-release` por inteiro, depois do commit da
documentação, com a árvore limpa. A confirmação do plano da release continua
valendo. Não crie a tag no lugar dessa skill.

## Em caso de falha

Pare na etapa que falhou. Não pule para a próxima. Diga o que ficou feito, o
que não foi enviado e a ação corretiva. Não desfaça commit sem o usuário pedir.
