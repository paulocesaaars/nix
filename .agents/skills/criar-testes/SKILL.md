---
name: criar-testes
description: >-
  Cria os testes que ainda não existem para os cenários de aceite do BDD
  (índice BDD.md e pasta bdd/). Descobre a marcação, a pasta de testes, o
  runner e o verificador do repositório. Não altera cenários, testes já
  existentes nem o comportamento esperado. Ao final, sugere a skill de
  revisão de código; se ela não existir, revisa os testes seguindo o
  AGENTS.md. Use quando o usuário pedir para criar, gerar ou completar os
  testes do BDD, cobrir cenários sem teste, ou fechar a lacuna entre bdd/ e
  a suíte.
---

# Criar Testes do BDD

Escreve apenas os testes que faltam para os cenários automatizáveis de `bdd/`.
Explicações ao usuário em **português (Brasil)**.

Nada aqui é específico de um projeto: índice, formato do ID, marcação no teste,
pasta da suíte, runner e verificador são **descobertos** no repositório
(passo 1). Se algo não puder ser descoberto, pergunte em vez de supor.

## Regras

- Siga o `AGENTS.md`. Em conflito, vale o `HARNESS.md`, se existir.
- Crie e altere **apenas** arquivos de teste. Não edite `bdd/`, `BDD.md`,
  código de produção, documentação nem configuração.
- A exceção de configuração é o registro do marcador, e só quando a suíte exige
  marcador declarado e ele ainda não existe: mostre a linha e grave **depois**
  da confirmação do plano.
- **Nunca** altere um cenário, um passo ou o resultado esperado para o teste
  passar. **Nunca** afrouxe uma asserção com o mesmo fim.
- **Nunca** contorne o verificador nem o runner (filtro que ignora falha,
  teste pulado, marcador removido).
- Cenário com `@manual` (no cenário ou herdado da funcionalidade) não ganha
  teste. Entra no relatório como checklist.
- Teste que já cita o ID não é reescrito. Se ele não verifica o resultado do
  cenário, registre no relatório e deixe para a revisão.
- Um cenário, um teste, o mesmo ID. Não reaproveite ID e não cubra dois
  cenários com um teste só.
- Não acrescente dependência. Se o cenário só fecha com uma ferramenta que o
  projeto não tem, pare nesse cenário e pergunte.
- Mostre o plano e **aguarde confirmação** antes de gravar.

## Fluxo

```
Progresso:
- [ ] 1. Descobrir o contexto
- [ ] 2. Listar os cenários sem teste
- [ ] 3. Confirmar o plano com o usuário
- [ ] 4. Escrever os testes
- [ ] 5. Validar
- [ ] 6. Relatar
- [ ] 7. Sugerir a revisão de código
```

### 1. Descobrir o contexto

Leia o `AGENTS.md`, o `HARNESS.md` se existir, e o `TDD.md` (ou o documento
técnico equivalente) no que disser respeito a testes, camadas e à interface
que cada cenário exercita.

| Dado | Onde descobrir |
|------|----------------|
| Índice e cenários | `BDD.md` na raiz e os arquivos de `bdd/`. Sem `BDD.md`, pare: o projeto não usa este BDD |
| ID, `@manual` e marcação no teste | Seção de convenções do `BDD.md`; na falta dela, o `AGENTS.md`. Confirme com um teste que já cita um ID |
| Verificador de cobertura | Comando citado no `BDD.md`, no CI, no Makefile, no manifesto ou em `scripts/` |
| Runner, pasta e marcadores | Manifesto, Makefile, CI e a documentação técnica |
| Onde o teste novo mora | Testes do mesmo caso de uso; senão, a árvore de testes do documento técnico |
| Arranjo reutilizável | Arquivo de setup da suíte e os testes vizinhos (fixtures, helpers, doubles) |

Pare sem gravar nada quando:

- não existe `BDD.md`;
- o índice e a pasta `bdd/` divergem, ou há ID de cenário repetido — o
  verificador costuma apontar isso; peça a correção e não invente o índice;
- a convenção de marcação não aparece no `BDD.md` nem num teste existente.

### 2. Listar os cenários sem teste

Prefira a lista do verificador do projeto, no modo que **avisa** cenário sem
teste (sem o modo estrito, que falha justamente por essa lacuna).

Sem verificador, monte a lista você mesmo:

1. Em cada arquivo de `bdd/`, leia as tags. O ID do cenário é o da linha do
   cenário (`Cenário` / `Scenario` / `Esquema do Cenário`), não o da
   funcionalidade. O formato exato é o que o `BDD.md` descreve.
2. `@manual` na funcionalidade vale para todos os cenários dela; no cenário,
   vale só para ele.
3. Procure cada ID na suíte, fora de `bdd/` e do `BDD.md`. ID citado num teste
   conta como coberto. Citação só em documentação não conta.

Aplique o recorte do usuário (IDs, arquivo de `bdd/`, caso de uso). ID pedido
que não existe no `bdd/` entra no plano como "não encontrado", sem teste
inventado.

Se não houver cenário sem teste no recorte, relate a cobertura e encerre no
passo 6. Não crie teste vazio.

### 3. Confirmar o plano

Mostre e aguarde confirmação:

```markdown
## Testes que faltam

- **<ID>** <título do cenário> → `<caminho do arquivo>` (arquivo novo | junto dos testes deste caso de uso)
- **Fora:** <n> já cobertos · @manual: <IDs> · não encontrados: <IDs>
- **Risco:** <cenário cujo código ainda não cumpre o resultado; o teste vai falhar>
```

Um cenário por linha. Se o usuário já tiver limitado o recorte, a lista segue
esse recorte. Não grave antes do sim.

### 4. Escrever os testes

Para cada cenário confirmado, leia o Gherkin inteiro e o código que o passo
de ação aciona. Siga o estilo dos testes vizinhos (nomes, fixtures, doubles,
isolamento). Não introduza um segundo estilo.

O teste:

- carrega o ID na marcação que o projeto já usa;
- tem o nome em inglês, descrevendo o comportamento;
- reusa fixture e helper existentes; não copia arranjo;
- exercita a interface que o cenário nomeia (comando, rota, ferramenta, tela).
  Essa interface é quem chama a definição única da capacidade — o teste não
  reimplementa a regra nem atravessa uma camada que o cenário não cita;
- transforma cada resultado (`Então` / `Then` e os `E` / `And` que completam
  o resultado) numa asserção. Arranjo é o `Dado` / `Given`; ação é o
  `Quando` / `When`;
- não depende de rede, relógio real, segredo ou estado fora do teste, salvo
  se a suíte já faz isso do mesmo jeito;
- em linguagem tipada, deixa helper novo com tipos nas funções públicas.

Não teste detalhe interno que o cenário não pede. Não crie abstração nova se
um teste vizinho já resolve.

Se, no meio da escrita, ficar claro que o cenário não dá para automatizar
(instalador, editor, gesto físico), pare nesse ID, explique e pergunte se ele
deve levar `@manual`. Não marque e não grave em `bdd/` sem aprovação. Não
entregue um teste que não verifica o resultado.

Se o código não cumpre o cenário, escreva o teste com o resultado que o
cenário pede. Não mude produção para fazê-lo passar: isso fica no relatório
do passo 6.

### 5. Validar

1. Rode só os testes novos, com o runner descoberto no passo 1.
2. Rode o verificador no modo que o CI usa. Sem essa informação, rode o modo
   estrito depois de gravar, para a lacuna que você deveria ter fechado falhar
   o comando se ainda existir.
3. Rode a checagem estática do projeto (lint e tipos) nos arquivos tocados,
   se o repositório tiver esses comandos.
4. Falha de arranjo (API, fixture, import): corrija **o teste** e rode de novo.
5. Falha porque o produto não cumpre o cenário: pare. Deixe o teste falhando,
   não altere produção, cenário nem asserção.

### 6. Relatar

```markdown
# Testes do BDD

- **Criados:** <n> — <ID> → `<arquivo>`
- **Já cobertos (não mexidos):** <n>
- **Manuais:** <checklist ID + título>
- **Produto não cumpre o cenário:** <ID, asserção que falha, o que o cenário exige>
- **Verificador:** <comando e resultado>
- **Fora desta skill:** <teste existente que não verifica o resultado>
```

Omita a linha que não se aplicar.

### 7. Sugerir a revisão de código

Depois do relatório, sugira revisar os arquivos de teste criados ou alterados.

1. Procure uma skill de revisão de código, priorizando as do repositório e
   depois as globais (nome comum: `revisar-codigo`). Se encontrar, **não a
   execute**. Entregue o pedido pronto, com esses arquivos no escopo. Só a
   execute se o usuário pedir na hora — aí leia o `SKILL.md` e siga-o.
2. Se não encontrar, revise você mesmo esses arquivos seguindo o `AGENTS.md`
   (o modelo do agente) e, se existir, o `HARNESS.md`. Não edite nada nessa
   revisão. Eixos:
   - arranjo ou capacidade duplicados, em vez de reusar o que a suíte e o
     núcleo já têm;
   - teste que reimplementa regra de negócio ou que ignora a interface que o
     cenário nomeia;
   - teste que não verifica cada resultado do cenário, ou que afrouxa o
     esperado;
   - idioma, tipos e o restante do que o `AGENTS.md` exige dos testes;
   - teste para cenário `@manual`, ou ID que não está em `bdd/`.

   Para cada achado: arquivo, local, problema, impacto e sugestão. Ordene do
   mais grave ao mais leve. Eixo limpo: diga que não há achado.

## Em caso de falha

- Falha antes da confirmação: nada foi gravado. Explique o que faltou descobrir.
- Verificador ou runner ausente e sem equivalente no manifesto ou no CI:
  pergunte o comando. Não invente uma suíte paralela.
- Teste falhando porque o produto não cumpre o cenário: o teste fica; a
  correção do produto é outro pedido.
