---
name: gerar-skill
description: >-
  Cria uma skill de agente abstrata e reutilizável, independente do projeto
  e das tecnologias. Não grava decisões, caminhos, comandos nem ferramentas
  que só existem no repositório em que a skill está sendo gerada. Ao final,
  lembra de adicionar a skill na main de https://github.com/paulocesaaars/skills
  com um pull request. Use quando o usuário pedir para criar, gerar, escrever
  ou extrair uma skill, um SKILL.md ou uma instrução reutilizável de agente.
---

# Gerar Skill

Produz uma skill de agente que qualquer projeto possa usar. Explicações ao
usuário e o texto da skill em **português (Brasil)**, salvo se o usuário
pedir outro idioma.

A skill gerada descreve um procedimento. Projeto, stack e decisões locais
ficam de fora: quem for usá-la descobre isso no repositório em que ela rodar.

## Regras

- O artefato é a skill. Não implemente a funcionalidade que ela descreve.
- Não copie para a skill nomes de produto, pastas, arquivos, comandos,
  bibliotecas, versões, fluxos ou decisões que só valem no projeto atual.
- Tecnologia só entra se for o assunto da skill em qualquer projeto. Se ela
  apareceu só porque este repositório a usa, não a nomeie.
- O que depender do projeto vira passo de descoberta (ler o documento que
  existir, achar o comando, perguntar). Não vira valor fixo.
- Não invente gatilho, escopo nem nome. Pergunte o que estiver ambíguo.
- Mostre o rascunho e aguarde confirmação antes de gravar.
- Não altere skill já existente sem pedido explícito.

## Fluxo

```
Progresso:
- [ ] 1. Entender o procedimento
- [ ] 2. Separar o reutilizável
- [ ] 3. Redigir e confirmar
- [ ] 4. Gravar
- [ ] 5. Lembrar o pull request
```

### 1. Entender o procedimento

Pergunte só o que faltar, poucas perguntas por vez:

- Qual tarefa a skill executa, do início ao fim.
- Quando o agente deve usá-la (pedidos e palavras que disparam).
- O que ela produz e o que fica fora.
- O que exige confirmação do usuário antes de alterar arquivo, remoto ou regra.

Se o pedido nasceu de um fluxo deste repositório, trate esse fluxo como
exemplo. Extraia o procedimento e descarte o que não serviria em outro
projeto.

### 2. Separar o reutilizável

Antes de escrever, risque do rascunho:

- produto, módulo, pasta e arquivo deste repositório;
- linguagem, framework, biblioteca, serviço e versão usados aqui, quando
  não forem o tema da skill;
- comando, caminho, porta, variável e nome de workflow copiados daqui;
- decisão de arquitetura, estilo ou processo que outro projeto não teria
  por padrão.

No lugar, escreva como descobrir o equivalente no projeto em que a skill
for usada, ou uma pergunta ao usuário.

### 3. Redigir e confirmar

A skill é um diretório `<nome>/SKILL.md`.

- `name`: minúsculas, números e hífens, no máximo 64 caracteres. Verbo ou
  tarefa, sem nome de projeto.
- `description`: terceira pessoa, o que faz e quando usar, com os termos
  que disparam a skill.
- Corpo: regras curtas e um fluxo em passos. O agente já sabe programar;
  grave só o que ele não adivinha.
- Sem tecnologia, caminho ou decisão que falhou no passo 2.

Mostre o texto inteiro e aguarde. Sem confirmação, não grave.

### 4. Gravar

Descubra onde este repositório versiona skills de agente (pastas que já
contêm `SKILL.md` de outras skills). Grave a mesma skill em cada uma
dessas pastas. Se não houver nenhuma, grave em `skills/<nome>/SKILL.md`
na raiz, a menos que o usuário indique outro lugar.

Não registre a skill num lock que aponte uma origem externa: ela ainda
não está no repositório de skills.

### 5. Lembrar o pull request

Ao terminar, lembre o usuário de adicionar a skill na branch `main` de
<https://github.com/paulocesaaars/skills>, gerando um pull request para
esse repositório. O arquivo vai em `skills/<nome>/SKILL.md`. Se o README
desse repositório lista as skills, a linha da skill nova entra no mesmo
pull request.

Pergunte se deve abrir o pull request agora. Se não, encerre.

Se sim:

1. Confira a autenticação no GitHub (`gh auth status`). Sem autenticação,
   pare e diga como entrar.
2. Não envie direto para `main`. Crie uma branch a partir de `main`.
3. Se a conta não puder escrever no repositório, abra o pull request a
   partir de um fork.
4. Inclua só a skill nova e, se existir, a linha no índice do README.
5. Abra o pull request contra `main` e entregue o link.

Não faça push forçado. Não altere outras skills nesse pull request.
