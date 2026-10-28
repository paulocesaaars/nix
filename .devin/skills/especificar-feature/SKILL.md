---
name: especificar-feature
description: >-
  Gera a especificação de uma funcionalidade antes da implementação:
  entrevista o usuário até ter contexto suficiente, pede decisão nos pontos
  críticos e entrega uma especificação alinhada ao AGENTS.md, ao PRD.md, ao
  TDD.md e, se houver, ao DESIGN.md. Não implementa. Use quando o usuário pedir para
  especificar, detalhar, escrever a spec, levantar requisitos ou desenhar uma
  funcionalidade nova.
---

# Especificar Funcionalidade

Produz a especificação de uma funcionalidade. Toda a saída é em
**português (Brasil)**. O objetivo é **especificar**, não implementar.

## Regras

- Siga todas as premissas do `AGENTS.md`. Em conflito, vale o `AGENTS.md`.
- **Não** edite, crie nem apague código. A especificação é o único artefato.
- Não invente requisitos. Para ambiguidade ou contradição, pergunte. Se a
  ambiguidade for irrelevante, registre a suposição em uma linha.
- Decisões que mudam escopo, regra de negócio, arquitetura, dados, segurança,
  experiência do usuário ou desvio do documento de design do projeto
  (`DESIGN.md`, se houver) são do usuário. Pergunte;
  não decida por ele.
- Use a ferramenta de perguntas estruturadas (`AskQuestion` ou equivalente)
  quando houver opções discretas. Marque a recomendada com "(Recomendado)"
  como primeira opção.

## Fluxo

```
Progresso:
- [ ] 1. Perguntar sobre o modelo
- [ ] 2. Ler a documentação
- [ ] 3. Entrevistar até ter contexto
- [ ] 4. Especificar e pedir decisões críticas
- [ ] 5. Entregar a especificação
- [ ] 6. Oferecer o plano
```

### 1. Perguntar sobre o modelo

Antes de qualquer outra ação, pergunte se o usuário quer trocar o modelo para
esta especificação:

- **Manter o modelo atual**
- **Trocar o modelo**

Se ele quiser trocar, oriente-o a selecionar o novo modelo e a repetir o
pedido. Pare e aguarde. O agente não troca o modelo sozinho.

### 2. Ler a documentação

Leia o `AGENTS.md` e o que for relevante ao pedido:

| Documento | Quando |
|-----------|--------|
| `PRD.md` | Sempre: escopo, regras de negócio, roadmap |
| `HARNESS.md` | Sempre, se existir: regras do projeto que prevalecem sobre o `AGENTS.md` |
| `TDD.md` | Arquitetura, camadas, dependências, configuração, segurança |
| `DESIGN.md` (vazio = sem estilo definido) | Qualquer parte visível ao usuário |

Leia também o código que a funcionalidade toca, para ancorar a especificação
no que já existe. Se a funcionalidade já existir ou contradizer o `PRD.md`,
avise o usuário antes de seguir.

### 3. Entrevistar até ter contexto

Se o pedido for simples demais ou vago, entreviste o usuário antes de
especificar. Faça poucas perguntas por rodada (até 4), da mais importante para
a menos, e repita até cobrir:

- **Problema:** qual dor resolve e para quem.
- **Resultado esperado:** como o usuário sabe que funcionou.
- **Escopo:** o que entra e o que fica de fora.
- **Fluxo:** entrada, passos e saída do ponto de vista do usuário.
- **Interfaces:** por onde a capacidade é exposta (CLI, API, interface etc.).
- **Restrições:** dados, desempenho, segurança, compatibilidade.

Não pergunte o que o código ou a documentação já respondem. Pare de entrevistar
quando der para especificar sem inventar.

### 4. Especificar e pedir decisões críticas

Monte a especificação com o modelo abaixo. Ao encontrar um ponto crítico ou
importante sem resposta, pare e pergunte. Apresente as alternativas com
impactos e uma recomendação. Registre cada decisão na seção **Decisões**.

Se o projeto usa BDD (existe `BDD.md`), especifique também os **cenários BDD**: leia o índice `BDD.md` e os
arquivos de `bdd/` que a funcionalidade toca, e sugira, em Gherkin português, os cenários novos e os que mudam por causa da
funcionalidade. Cada cenário novo recebe o próximo ID livre da história
(por exemplo `@US-03.4`), no arquivo daquele caso de uso, ou de uma história nova (arquivo novo
em `bdd/` e linha nova no índice); o que não dá para automatizar leva
`@manual`. Cenários existentes só mudam com decisão explícita do usuário.

### 5. Entregar a especificação

Depois de entregar, se o projeto usa BDD, pergunte se pode adicionar os
cenários sugeridos a `bdd/` (e ao índice `BDD.md`, se o caso de uso for novo). Só grave com a
aprovação do usuário.

Apresente a especificação no chat. Para salvá-la em arquivo, pergunte antes o
caminho e o nome. Não grave sem autorização.

### 6. Oferecer o plano

Ao terminar, pergunte se o usuário quer gerar um plano de implementação a
partir da especificação.

- **Se sim:** o plano sai do **modo de planejamento nativo do agente** em uso,
  com a especificação como insumo.
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

## Modelo da especificação

Omita as seções que não se aplicam.

```markdown
# Especificação — <nome da funcionalidade>

## Contexto
<problema, quem é afetado e por que agora>

## Objetivo
<resultado esperado, em uma ou duas frases>

## Escopo
- **Inclui:** <...>
- **Fora de escopo:** <...>

## Requisitos funcionais
1. <o sistema deve ...>

## Regras de negócio
- <regra, com referência ao PRD.md quando houver>

## Fluxo do usuário
1. <passo>

## Interfaces
<comandos, endpoints, parâmetros, saídas e erros, com a ação corretiva de
cada erro. Uma única definição da capacidade, reutilizada pelas interfaces>

## Interface visual
<só se houver interface: telas e componentes com os tokens do documento de
design do projeto (`DESIGN.md`, se houver). Qualquer desvio aparece aqui
com a autorização do usuário>

## Impacto técnico
<módulos afetados, camadas, dependências, configuração e dados, segundo o
TDD.md>

## Requisitos não funcionais
<desempenho, segurança, compatibilidade, observabilidade>

## Critérios de aceitação
- [ ] <verificável pelo usuário>

## Cenários BDD sugeridos
<só se o projeto usa BDD: cenários em Gherkin para `bdd/`, indicando o arquivo, com IDs e `@manual` quando não
der para automatizar; marque "novo" ou "altera @HU-xx.y">

## Decisões
| Ponto | Decisão | Motivo |
|-------|---------|--------|

## Suposições
- <suposição registrada em uma linha>

## Riscos e questões em aberto
- <...>
```
