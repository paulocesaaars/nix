---
name: especificar-projeto
description: >-
  Guia o usuário, em conversa consultiva, pelo Spec-Driven Development do
  projeto. No início pergunta se é um monorepo ou um projeto dentro de um
  maior; nesse caso, pede a especificação em alto nível ou os links dos
  repositórios e monta o contexto com o Octocode. Escreve o PRD, pergunta
  se a stack será definida por ele ou proposta a partir do PRD, preenche o
  TDD e oferece uma revisão cruzada. O DESIGN.md só entra se houver
  frontend no escopo. Depois pergunta se o usuário quer gerar os requisitos
  de negócio no BDD.md, para uma geração de testes futura, e no final se
  quer o plano no modo de planejamento do agente. Não implementa. Use quando o usuário pedir para
  especificar o projeto, conduzir o SDD, escrever o PRD, o TDD ou o design,
  definir a stack, ou situar um repositório num monorepo ou num projeto maior.
---

# Especificar Projeto

Conduz a especificação do projeto, uma etapa por vez, em tom consultivo:
pergunta pouco, explica o porquê e não despeja um questionário. Roda **uma
vez**, depois de `iniciar-projeto`. Se `PRD.md` e `TDD.md` já tiverem
conteúdo, diga que o projeto já foi especificado e só continue se o usuário
pedir para refazer. Explicações
ao usuário em **português (Brasil)**. Não implementa código.

## Regras

- Siga o `AGENTS.md`. Em conflito, vale o `HARNESS.md`, se existir.
- Não antecipe a etapa seguinte. Não escreva o TDD durante o PRD, nem o
  design durante a revisão.
- Até 3 perguntas por rodada, da mais importante para a menos. Não pergunte
  o que o usuário ou um documento já respondeu.
- Não invente requisito de produto. Se uma lacuna for irrelevante, registre
  a suposição em uma linha e siga. Se mudar escopo, público ou regra, pergunte.
- Use a ferramenta de perguntas estruturadas quando houver opções discretas.
- Grave na raiz, no arquivo que o projeto já usa. Se não houver, crie
  `PRD.md` e `TDD.md`. Crie o `DESIGN.md` só na etapa de design. Um
  `design.md` já existente é o arquivo de design: use-o, não crie outro.
- Arquivo ausente ou vazio: mostre o texto e grave ao fim da etapa.
- Arquivo com conteúdo: mostre o que muda e grave só com confirmação.
  Não apague decisão anterior que esta conversa não revisou.
- Sem frontend no escopo, a etapa de design não existe: não a sugira, não
  pergunte estilo e não crie `DESIGN.md`.

## Fluxo

```
Progresso:
- [ ] 0. Onde o projeto se encaixa
- [ ] 1. PRD
- [ ] 2. TDD e stack
- [ ] 3. Revisão e validação
- [ ] 4. DESIGN.md — só com frontend no escopo
- [ ] 5. Requisitos de negócio no BDD.md
- [ ] 6. Oferecer o plano
```

### 0. Onde o projeto se encaixa

Antes do objetivo e do problema, pergunte:

- **Monorepo** — este repositório é o projeto inteiro
- **Projeto dentro de um maior** — este repositório é uma parte

**Monorepo.** Siga para o PRD. A especificação cobre este repositório.

**Projeto dentro de um maior.** Peça uma das duas:

- a especificação em alto nível do projeto maior;
- os links dos repositórios dos projetos.

Com a especificação em alto nível, use-a como limite: o PRD deste
repositório só cobre o que cabe nele. Não reescreva o projeto maior.

Com os links, gere essa especificação pelo **Octocode** antes de entrevistar.
Para cada repositório, leia o README e os documentos de especificação que
existirem e confirme no código só o que eles não disserem. Repositório
GitHub entra pela busca e leitura remotas do Octocode; caminho local, pela
busca local. Escreva em alto nível o objetivo, as fronteiras entre os
repositórios e o que cabe neste. Mostre e peça confirmação. Sem Octocode
disponível, pare e diga o que falta. Não invente a especificação a partir
do link.

Não pergunte de novo, no PRD, o que essa especificação já respondeu.

### 1. PRD

Comece pelo projeto, não pela solução. Na primeira rodada, pergunte só:

- qual é o objetivo principal;
- qual problema resolve e para quem.

Se ainda não der para escrever o PRD sem inventar, continue em rodadas curtas
até cobrir resultado esperado, o que entra, o que fica de fora e como o
usuário percebe que funcionou. Pare assim que der para redigir.

Mostre o PRD e grave.

```markdown
# PRD — <nome do projeto>

## Problema
<quem sofre, com o quê>

## Objetivo
<resultado principal, em uma ou duas frases>

## Para quem
<quem usa>

## Escopo
- **Inclui:** <...>
- **Fora de escopo:** <...>

## Requisitos
1. <o produto deve ...>

## Regras de negócio
- <regra>

## Como saber que funcionou
- <sinal observável>

## Riscos
- <...>

## Suposições
- <uma linha, só se houver>

## No projeto maior
<só se este repositório for uma parte: o que o projeto maior faz e o que fica neste repositório>
```

Omita a seção que não tiver conteúdo.

### 2. TDD e stack

Só comece com o PRD já gravado nesta conversa ou já existente no repositório.
Se o PRD não existir, volte à etapa 1.

Antes de sugerir tecnologia ou escrever o TDD, pergunte, sem pular:

- **Definir a stack manualmente**
- **Propor a stack a partir do PRD**

Não marque uma das duas como recomendada: a escolha é do usuário.

**Manual.** Pergunte a stack em rodadas curtas (linguagem, interface, dados,
onde roda). Não complete o que ele não disse com uma escolha sua. Se faltar
uma peça sem a qual o TDD não fecha, pergunte só essa peça.

**Proposta.** Proponha uma stack enxuta justificada pelo PRD: problema,
público, escopo e restrições. Para cada escolha, uma frase de porquê. Não
acrescente ferramenta que o PRD não pede. Mostre a proposta e grave-a no TDD
como a stack escolhida por essa opção.

Em seguida preencha o TDD com a stack da opção escolhida. Arquitetura,
componentes, dados, interfaces, configuração e segurança ficam aqui. Motivo
de produto fica no PRD.

```markdown
# TDD — <nome do projeto>

## Stack
| Camada | Escolha | Por quê |
|--------|---------|---------|
| <...> | <...> | <ligado ao PRD, ou "definido pelo usuário"> |

## Arquitetura
<como as partes se relacionam>

## Componentes
- <responsabilidade>

## Dados
<o que se guarda e o que não se guarda>

## Interfaces
<por onde o produto se expõe>

## Configuração e segurança
<só o que a stack e o PRD exigem>

## Decisões técnicas
| Decisão | Alternativa afastada | Motivo |
|---------|----------------------|--------|
```

### 3. Revisão e validação

Com PRD e TDD preenchidos, decida se há frontend no escopo: tela, página,
aplicação web ou mobile, ou outra interface visual para uma pessoa. API,
CLI, biblioteca, job ou serviço sem interface não contam.

**Sem frontend.** Não mencione design. Pergunte só se o usuário quer
revisar e validar. Depois da revisão, ou se ele não quiser revisar, vá
para a etapa 5 sem falar de design.

**Com frontend.** Pergunte:

- **Revisar e validar** os dois documentos
- **Seguir para o design**

**Revisar.** Entregue um resumo cruzado, não uma segunda cópia dos arquivos.
Para cada objetivo ou requisito do PRD, diga como o TDD o atende. Depois
destaque, em lista curta, os **pontos críticos e as decisões técnicas** que
dependem da aprovação do usuário: escopo, stack, dados, segurança e qualquer
ponto em que o TDD restringe o que o PRD promete.

Espere. Se ele ajustar, atualize o arquivo dono daquele fato e mostre de
novo só o que mudou no cruzamento. Com ponto crítico ainda em aberto, não
avance. Sem frontend, vá para a etapa 5 sem falar de design.

**Seguir.** Vá para a etapa 4. As decisões da etapa 2 permanecem como estão.
Se nesta hora o escopo não tiver frontend, não ofereça este caminho: vá
para a etapa 5 sem falar de design.

### 4. DESIGN.md

Não entre aqui sem frontend no escopo. Se não houver, vá para a etapa 5
sem sugerir esta.

Peça o estilo visual ou uma referência. A referência pode ser uma descrição,
um arquivo ou uma página. [getdesign.md](https://getdesign.md) é um exemplo
de catálogo: cada item é um `DESIGN.md` de um produto real, com cores, tipo,
espaçamento e componentes. Se o usuário indicar uma URL ou um arquivo, leia
antes de escrever.

O `DESIGN.md` gerado é orientado pelo PRD e pelo TDD, não pela referência.

- Adote da referência só o que combina com o público, o tom, a plataforma e
  as restrições já escritas.
- O que contradizer o PRD ou o TDD fica de fora. Diga o que ficou de fora e
  por quê.
- Não prescreva recurso visual que a interface escolhida no TDD não comporta.
- Sem referência, proponha um estilo a partir do PRD e confirme com o
  usuário antes de gravar.

Grave o `DESIGN.md` com cores, tipografia, espaçamento, componentes e o
raciocínio de cada escolha. Cada escolha aponta para o trecho do PRD ou do
TDD que a sustenta.

Siga para a etapa 5.

### 5. Requisitos de negócio no BDD.md

Pergunte se o usuário quer gerar os requisitos de negócio para preencher o
`BDD.md`:

- **Gerar os requisitos de negócio**
- **Não gerar agora**

**Não gerar.** Vá para a etapa 6. Não crie cenário nem teste.

**Gerar.** Extraia os requisitos de negócio do PRD. Não invente regra que
não esteja nele nem no que o usuário acabou de decidir. O TDD só informa
por onde o produto se expõe; o cenário descreve o comportamento de negócio,
não a implementação.

Mostre o rascunho e grave só com a confirmação. Se o `BDD.md` ou `bdd/` já
tiverem conteúdo, mostre o que entra e não apague cenário existente sem
confirmação.

O `BDD.md` é o índice. Cada caso de uso ganha um arquivo em `bdd/`, em
Gherkin e em português. ID estável (`@US-01.1`). O que não dá para
automatizar leva `@manual`. Não escreva testes agora: estes cenários ficam
prontos para uma geração de testes futura.

```markdown
# BDD

Índice dos casos de uso. Os cenários em `bdd/` são a fonte da geração de
testes futura. Cenário com `@manual` não vira teste automático.

| ID | Caso de uso | Arquivo |
|----|-------------|---------|
| US-01 | <nome> | [bdd/us-01.md](bdd/us-01.md) |
```

```gherkin
# language: pt
Funcionalidade: <caso de uso>

  @US-01.1
  Cenário: <requisito de negócio observável>
    Dado <contexto>
    Quando <ação>
    Então <resultado>
```

Siga para a etapa 6.

### 6. Oferecer o plano

Ao terminar, pergunte se o usuário quer gerar um plano de implementação a
partir do PRD, do TDD e, se existirem, do `DESIGN.md` e do `BDD.md`.

- **Se sim:** o plano sai do **modo de planejamento nativo do agente** em uso,
  com esses documentos como insumo.
  - **Agente que entra no modo sozinho:** entre no modo de planejamento.
  - **Agente que não entra no modo sozinho:** **não** escreva o plano. Pare,
    informe o comando do agente e entregue a especificação pronta para colar
    depois dele.

  Cada agente tem o seu jeito de entrar no modo de planejamento (em geral
  chamado *Plan mode*, ou um comando `/plan`). Se não souber como ativá-lo no
  agente em uso, consulte a documentação dele ou peça ao usuário para ativar.

  **Não** use skill para gerar o plano, nem esta nem outra. Escrever o plano
  no chat também não substitui o modo de planejamento.
- **Se não:** encerre. Não implemente nada.
