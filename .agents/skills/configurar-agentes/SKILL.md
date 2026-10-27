---
name: configurar-agentes
description: >-
  Cria ou atualiza o AGENTS.md e o CLAUDE.md do projeto a partir do modelo
  padrão de instruções de agente, para que Claude Code, Cursor e Copilot
  sigam as mesmas regras. Use quando o usuário pedir para configurar, gerar,
  instalar ou atualizar o AGENTS.md, o CLAUDE.md ou as instruções de agente do
  repositório.
---

# Configurar Agentes

Instala no projeto as instruções de agente padronizadas. Explicações ao usuário
em **português (Brasil)**. Edita **apenas** `AGENTS.md` e `CLAUDE.md` na raiz do
repositório.

O modelo fica em [`assets/AGENTS.template.md`](assets/AGENTS.template.md), na
pasta desta skill. Ele é a fonte do conteúdo: copie-o byte a byte, sem
reescrever, resumir ou adaptar ao projeto. Produto, stack e arquitetura ficam
na documentação do projeto, nunca no `AGENTS.md`.

| Arquivo | Quem lê | Conteúdo |
|---------|---------|----------|
| `AGENTS.md` | Cursor, Copilot e outros | O modelo |
| `CLAUDE.md` | Claude Code | A linha `@AGENTS.md`, que importa o `AGENTS.md` |

## Fluxo

```
Progresso:
- [ ] 1. Localizar a raiz e o modelo
- [ ] 2. AGENTS.md
- [ ] 3. CLAUDE.md
- [ ] 4. Conferir a documentação de referência
- [ ] 5. Relatar
```

### 1. Localizar a raiz e o modelo

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

O modelo é `assets/AGENTS.template.md` relativo ao diretório deste `SKILL.md`.
Se não existir, pare e peça para reinstalar a skill
(`npx skills add paulocesaaars/skills -s configurar-agentes`).

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

### 4. Conferir a documentação de referência

O modelo aponta para `PRD.md` (produto) e `TDD.md` (técnico), aceitando nomes
equivalentes. Verifique se existem na raiz. Se faltarem, apenas informe no
relatório; não crie esses documentos.

### 5. Relatar

```markdown
# Instruções de agente configuradas

- **AGENTS.md:** <criado | já atualizado | substituído | mesclado | mantido>
- **CLAUDE.md:** <criado | já importava o AGENTS.md | importação adicionada>
- **Documentação de referência:** <encontrada | ausente: PRD.md, TDD.md>
```
