---
name: implementar-sdd
description: >-
  Conduz uma funcionalidade: especifica, planeja, implementa e então pergunta
  se gera os testes do BDD, se revisa o código e se commita. Não atualiza a
  documentação nem publica a release; isso é um fluxo separado. No início, roda os
  testes: sem suíte, avisa e segue; se falharem, pergunta se a correção entra
  na especificação atual. Use quando o usuário pedir para desenvolver,
  implementar ou construir uma funcionalidade, feature ou fluxo de
  desenvolvimento, ou quando chamar implementar-sdd. Não use para dúvida,
  exploração, opinião ou pedido de uma etapa só.
---

# Implementar SDD

Conduz uma funcionalidade da especificação até o código. Testes do BDD, revisão
e commit são opcionais e vêm depois da implementação. Documentação, guardrails
e release ficam em um fluxo separado, fora desta skill. Explicações ao usuário em
**português (Brasil)**.

Cada etapa é uma skill que já existe. Leia o `SKILL.md` dela e siga-o. Não
reinterprete nem encurte as regras dela. Esta skill só define a ordem, o que
pula e onde o fluxo para.

## Quando começar

Comece quando o usuário pedir para desenvolver, implementar ou construir uma
funcionalidade.

Não comece em dúvida, exploração, opinião ou pedido de uma etapa só
(`especificar-feature`, `criar-testes`, `revisar-codigo`, `versionar`,
`atualizar-docs`, `publicar-release`). Nesses casos, siga só a skill pedida.

Se o usuário entregar a especificação pronta ou pedir para retomar de uma
etapa, comece nela. Não refaça etapa já concluída nesta conversa.

## Regras

- Siga o `AGENTS.md`. Em conflito, vale o `HARNESS.md`, se existir.
- Uma etapa termina antes da próxima. Não antecipe commit, documentação,
  guardrails nem release. A publicação é outro pedido.
- O plano aprovado autoriza só o que está nele. Fora isso, peça confirmação.
- Localize cada skill pelo nome nas pastas do repositório (`.claude/skills`,
  `.agents/skills`) e, se faltar, nas skills globais. Leia um
  único `SKILL.md`: as cópias são iguais. Skill ausente: pare e diga qual.
- Use a ferramenta de perguntas estruturadas quando houver opções discretas.
  Marque a recomendada com "(Recomendado)" como primeira opção.

## Fluxo

```
Progresso:
- [ ] 0. Rodar os testes
- [ ] 1. Especificar
- [ ] 2. Planejar
- [ ] 3. Implementar
- [ ] 4. Gerar os testes do BDD — se o usuário quiser
- [ ] 5. Revisar — se o usuário quiser
- [ ] 6. Commitar — se o usuário quiser
```

### 0. Rodar os testes

Antes de qualquer etapa, descubra o comando de teste do projeto (CI, Makefile,
manifesto ou script) e rode-o. Registre o resultado: a etapa 1 não roda a
suíte de novo.

- Suíte passando: siga.
- Projeto sem testes (nenhum comando, nenhum arquivo de teste, ou o runner
  não coletou nenhum): alerte que o projeto não possui testes e que não foi
  possível validar o funcionamento. Não pare por isso.
- Suíte falhando: mostre o erro e pergunte:
  - **Adicionar a correção na especificação atual**
  - **Seguir sem adicionar**

  Não pare nas duas respostas. Não altere código nem teste para a suíte
  passar. Se o usuário aceitar, a especificação desta funcionalidade inclui a
  correção: o que falhou e o comportamento esperado. Se o esperado não estiver
  claro na falha, pergunte antes de escrever. Se a especificação ainda não
  existir, a etapa 1 a escreve com essa correção. Se ele recusar, a
  especificação não cobre essa falha.

### 1. Especificar

Siga `especificar-feature` por inteiro, inclusive a pergunta sobre o modelo,
as decisões críticas e a correção aceita na etapa 0. A etapa 0 desta skill já
rodou os testes: `especificar-feature` não os repete. Não implemente nesta
etapa.

### 2. Planejar

Siga o passo final de `especificar-feature`: o plano sai do modo de
planejamento nativo do agente, com a especificação como insumo. Não escreva o
plano no chat no lugar desse modo. Se o agente não entrar no modo sozinho,
pare e peça ao usuário para ativá-lo.

Implemente só depois que o usuário aprovar o plano. Se ele não quiser o plano,
encerre.

### 3. Implementar

No modo de implementação, entregue o plano aprovado: código de produção e o
que o plano lista, menos arquivos de teste.

Não crie nem altere teste. Isso é a etapa 4, e só se o usuário quiser.
Não commite. Não amplie o escopo. Ambiguidade no plano: pergunte antes de
codar.

### 4. Gerar os testes do BDD

Se `BDD.md` estiver preenchido e houver cenários em `bdd/`, sugira gerar
os testes que faltam e pergunte se o usuário quer gerá-los. Se estiverem
vazios ou ausentes, informe que não há cenários e siga para a etapa 5.

- **Gerar os testes**
- **Pular**

**Pular.** Vá para a etapa 5. Não crie teste.

**Gerar.** Siga `criar-testes` por inteiro, inclusive a confirmação do plano.
No passo em que ela apenas sugere a revisão, não pare e não a execute: a
revisão é a etapa 5, e também é opcional.

Se não houver cenário sem teste, diga isso e vá para a etapa 5.

Teste falhando porque o produto não cumpre o cenário: pergunte se corrige o
produto agora.

- **Corrigir:** volte à etapa 3 só nessa lacuna, sem mudar cenário nem
  asserção. Rode de novo os testes que falharam. Só siga se passarem.
- **Não corrigir:** pare. O teste fica como `criar-testes` deixou.

### 5. Revisar

Pergunte se o usuário quer revisar o código desta funcionalidade.

- **Revisar**
- **Pular**

**Pular.** Vá para a etapa 6.

**Revisar.** Siga `revisar-codigo`. O escopo é o que este fluxo mudou
(`git diff`), mais os testes criados na etapa 4, se houve. Não edite nada na
revisão.

Achado **crítico** ou **alto**: pare. Mostre o relatório e não commite. Só
continue quando o usuário pedir explicitamente para corrigir. Aplique só o que
ele aceitar, depois revise de novo os arquivos tocados. Repita até não restar
crítico nem alto.

Achado **médio** ou **baixo**: registre no relatório e siga. Eles continuam
visíveis se a etapa 6 for confirmada.

### 6. Commitar

Pergunte se o usuário quer preparar commits por assunto, subir a versão e
enviar a branch. Se ele pedir apenas commit, não suba a versão nem envie
sem autorização específica.

- **Commitar**
- **Pular**

**Pular.** Encerre. Não atualize documentação, não gere guardrails e não
publique release.

**Commitar.** Siga `versionar` nos passos 1 a 8: checagens, commits por
assunto, subida de versão e envio da branch. A confirmação do plano de
commits continua valendo.

Pule os passos 9 e 10. Não ofereça atualizar a documentação nem abrir pull
request: documentação e release são outro pedido.

Checagem ou teste falhou: pare.

Ao terminar, não comece a publicação. Se o usuário pedir, a ordem é
`gerar-guardrails` (uma vez, e só se o projeto tiver testes), `atualizar-docs`
e, no fim, `versionar` ou `publicar-release`.

## Em caso de falha

Pare na etapa que falhou. Não pule para a próxima. Diga o que ficou feito, o
que não foi enviado e a ação corretiva. Não desfaça commit sem o usuário pedir.
