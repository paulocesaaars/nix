---
name: iniciar-projeto
description: >-
  Inicia um projeto instalando as instruções de agente: cria ou atualiza o
  AGENTS.md e o CLAUDE.md a partir do modelo padrão, para que Claude Code,
  Cursor e Copilot sigam as mesmas regras, e confere se o GitHub CLI e os MCPs
  Context7 e Octocode estão instalados e configurados, instalando ou sugerindo o
  que faltar. Use quando o usuário pedir para iniciar, começar ou configurar um
  projeto, ou para gerar, instalar ou atualizar o AGENTS.md, o CLAUDE.md ou as
  instruções de agente do repositório.
---

# Iniciar Projeto

Inicia o projeto instalando as instruções de agente padronizadas. Roda **uma
vez**, depois que as skills já estiverem instaladas no projeto e antes de
`especificar-projeto`. Se o `AGENTS.md` já for o modelo e os documentos de
referência já existirem, diga que o projeto já foi iniciado e não refaça.
Explicações ao usuário
em **português (Brasil)**. Edita **apenas** `AGENTS.md`, `CLAUDE.md` e `HARNESS.md` e cria, se faltarem, os
documentos de referência (`PRD.md`, `TDD.md`, `DESIGN.md`, `BDD.md` e a pasta
`bdd/`), todos
na raiz do repositório. Também confere e, com a confirmação do usuário, instala
as ferramentas de apoio da máquina (passo 6).

O modelo fica em [`assets/AGENTS.template.md`](assets/AGENTS.template.md), na
pasta desta skill. Ele é a fonte do conteúdo: copie-o byte a byte, sem
reescrever, resumir ou adaptar ao projeto. Produto, stack e arquitetura ficam
na documentação do projeto, nunca no `AGENTS.md`.

| Arquivo | Quem lê | Conteúdo |
|---------|---------|----------|
| `AGENTS.md` | Cursor, Copilot e outros | O modelo |
| `CLAUDE.md` | Claude Code | A linha `@AGENTS.md`, que importa o `AGENTS.md` |
| `HARNESS.md` | Todos, via `AGENTS.md` | As regras do projeto, que complementam o modelo. Criado vazio; o conteúdo é do projeto |

## Fluxo

```
Progresso:
- [ ] 1. Localizar a raiz e o modelo
- [ ] 2. AGENTS.md
- [ ] 3. CLAUDE.md
- [ ] 4. HARNESS.md
- [ ] 5. Documentos de referência
- [ ] 6. Ferramentas de apoio
- [ ] 7. Relatar
```

### 1. Localizar a raiz e o modelo

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

O modelo é `assets/AGENTS.template.md` relativo ao diretório deste `SKILL.md`.
Se não existir, pare e peça para reinstalar a skill
pela origem de onde ela veio.

### 2. AGENTS.md

| Situação | Ação |
|----------|------|
| Não existe | Copie o modelo para `$ROOT/AGENTS.md` |
| Idêntico ao modelo | Nada a fazer |
| Diferente do modelo | Mostre o diff (`git diff --no-index "$ROOT/AGENTS.md" <modelo>`) e pergunte: **substituir pelo modelo**, **mesclar** ou **manter** |

Ao mesclar: parta do modelo e preserve só os acréscimos do projeto que não
contradizem o modelo nem duplicam o que ele já diz. Conteúdo de produto, stack
ou arquitetura não entra; sugira movê-lo para a documentação do projeto.

### 3. CLAUDE.md

| Situação | Ação |
|----------|------|
| Não existe | Crie `$ROOT/CLAUDE.md` com a única linha `@AGENTS.md` |
| Já contém a linha `@AGENTS.md` | Nada a fazer |
| Existe sem a importação | Insira `@AGENTS.md` na primeira linha e preserve o resto. Se o resto repetir regras do `AGENTS.md`, aponte as duplicações e pergunte se pode removê-las |

### 4. HARNESS.md

O `AGENTS.md` (modelo) é igual em todo projeto e importa o `HARNESS.md`
por instrução textual de leitura. As regras próprias do projeto vivem só nele;
`@HARNESS.md` só é importação automática onde o agente oferecer esse recurso.

| Situação | Ação |
|----------|------|
| Não existe | Crie o arquivo vazio na raiz |
| Existe | **Nunca** altere nem sobrescreva: o conteúdo é do projeto |

Se o `AGENTS.md` do projeto tiver regras próprias que não estão no modelo
(passo 2, "mesclar"), sugira movê-las para o `HARNESS.md` em vez de
mantê-las no `AGENTS.md`, e só mova com a confirmação do usuário.

### 5. Documentos de referência

O modelo aponta para `PRD.md` (produto), `TDD.md` (técnico), `DESIGN.md`
(estilo visual) e `BDD.md` (índice dos casos de uso; os critérios de aceite em Gherkin ficam na pasta
`bdd/`, um arquivo por caso de uso), aceitando nomes equivalentes.

| Situação | Ação |
|----------|------|
| Não existe nem um equivalente | Crie o arquivo **vazio** na raiz (para o BDD, o `BDD.md` vazio e a pasta `bdd/` com um `.gitkeep`) |
| Existe (ou há um equivalente) | **Nunca** altere nem sobrescreva: o conteúdo é do projeto |

Esses documentos nascem em branco e existem sempre. Quem os preenche é o
projeto, não esta skill.

### 6. Ferramentas de apoio

O modelo do `AGENTS.md` manda consultar o **CLI do host de código** (no GitHub, o
`gh`), o **Context7** e o **Octocode**. Confira se estão instalados e configurados nesta máquina. Se
faltar algo, **tente instalar**; se não der, **sugira** ao usuário, explicando
para que serve (tabela abaixo).

| Ferramenta | Para que serve | Sem ela |
|------------|----------------|---------|
| **CLI do host** (GitHub: `gh`) | Pull requests, issues, releases, checks de CI e tags remotas direto do terminal. As skills de commit e de release dependem dele | Nada de abrir PR, acompanhar o CI nem publicar release pelo agente |
| **MCP Context7** | Documentação **atualizada** de bibliotecas, frameworks e APIs, na versão certa | O agente escolhe e usa dependências de memória, com risco de API desatualizada ou inventada |
| **MCP Octocode** | Pesquisa em código, histórico e PRs de repositórios, externos ou locais | O agente não consegue estudar como outro projeto resolve algo nem entender a origem de uma dependência |

Descubra o host com `git remote get-url origin`. Se não for o GitHub, procure o
CLI equivalente (`glab` no GitLab, `az` no Azure DevOps) e trate-o como o `gh`
nos passos abaixo; se não houver um CLI conhecido, apenas informe ao usuário. O
Octocode usa o login do GitHub: fora dele, serve para repositórios públicos e
locais.

#### 6.1 Verificar

```bash
gh --version            # GitHub; em outro host, o CLI dele
gh auth status          # instalado e autenticado são coisas diferentes
node --version          # Context7 e Octocode rodam via npx: Node 18.12 ou mais novo
```

Para os MCPs, use o agente em uso:

| Agente | Como conferir |
|--------|---------------|
| Claude Code | `claude mcp list` |
| Cursor | `.cursor/mcp.json` do projeto e `~/.cursor/mcp.json` |
| VS Code / Copilot | `.vscode/mcp.json` e a configuração de MCP do usuário |
| Outro | O arquivo de MCP que o agente documenta |

Considere **configurado** um servidor cujo nome ou comando contenha `context7`
ou `octocode`. Se o agente não tiver como ser inspecionado, diga isso e peça ao
usuário para confirmar, em vez de supor.

| Situação | Ação |
|----------|------|
| Tudo instalado, configurado e autenticado | Nada a fazer |
| Algo falta ou está sem autenticação | Siga 6.2 |

#### 6.2 Instalar o que faltar

Mostre cada comando antes de rodá-lo. Instale só no escopo do **usuário**; se o
comando exigir `sudo`, administrador ou uma ação interativa, **não force**: vá
para 6.3. Nunca grave token em arquivo do repositório.

- **GitHub CLI.** Windows: `winget install --id GitHub.cli -e`. macOS:
  `brew install gh`. Linux: o gerenciador da distribuição, conforme
  <https://github.com/cli/cli#installation>. Depois, a autenticação é
  interativa: peça ao usuário para rodar `! gh auth login`.
- **Node.js** (se faltar para os MCPs): versão LTS pelo gerenciador do sistema
  (`winget install OpenJS.NodeJS.LTS`, `brew install node`).
- **Context7.** Claude Code:
  `claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp`.
  Outros agentes: acrescente ao arquivo de MCP do agente
  `"context7": { "command": "npx", "args": ["-y", "@upstash/context7-mcp"] }`.
  Uma chave de API é opcional; confira o limite no site do Context7.
- **Octocode.** Claude Code:
  `claude mcp add --scope user octocode -- npx -y octocode-mcp@latest`.
  Outros agentes: o mesmo formato do Context7, com
  `"args": ["-y", "octocode-mcp@latest"]`. A autenticação reaproveita o
  `gh auth login`; sem isso, o Octocode roda com limite de uso menor.

Ao editar o arquivo de MCP de um agente: leia antes, **preserve** os servidores
que já existem, faça uma cópia de segurança ao lado e só grave com a
confirmação do usuário.

Depois de instalar, confira de novo (6.1). Os MCPs só aparecem depois que o
usuário **reinicia o agente**; avise.

#### 6.3 Sugerir quando não for possível

Se não conseguir instalar (sem permissão, sem rede, sem gerenciador de pacotes,
agente sem comando de MCP), pare e sugira ao usuário, para cada item faltante:
o comando exato, **por que a ferramenta importa** (tabela acima) e o que muda
sem ela. Não insista nem tente alternativas arriscadas.

### 7. Relatar

```markdown
# Instruções de agente configuradas

- **AGENTS.md:** <criado | já atualizado | substituído | mesclado | mantido>
- **CLAUDE.md:** <criado | já importava o AGENTS.md | importação adicionada>
- **HARNESS.md:** <criado vazio | já existia, mantido>
- **PRD.md / TDD.md / DESIGN.md / BDD.md e bdd/:** <criados vazios | já existiam, mantidos>
- **CLI do host (`gh`):** <ok e autenticado | instalado agora | instalado, falta `gh auth login` | ausente: sugerido>
- **Context7:** <ok | instalado agora (reinicie o agente) | ausente: sugerido>
- **Octocode:** <ok | instalado agora (reinicie o agente) | ausente: sugerido>
```
