---
name: atualizar-docs
description: >-
  Atualiza PRD.md, TDD.md e README.md com tudo que foi implementado desde a
  última revisão desses documentos, comparando o código atual com o que está
  documentado. Use quando o usuário pedir para atualizar, sincronizar ou revisar
  a documentação, o PRD, o TDD ou o README após mudanças no código.
---

# Atualizar Documentação

Mantém `PRD.md`, `TDD.md` e `README.md` fiéis ao código. Edita **apenas** esses
três arquivos e o marcador `last-reviewed-commit` — nunca código, testes ou
configuração. Todo o texto escrito é em **português (Brasil)**.

Se o repositório usar outros nomes para os documentos de produto, técnico e de
uso, aplique o fluxo a eles.

## Papel de cada documento

Cada fato mora em **um** documento; os outros apontam para ele.

| Documento | Conteúdo | Não deve conter |
|-----------|----------|-----------------|
| `PRD.md` | O quê e por quê: requisitos (RF), histórias (os critérios de aceite ficam no `BDD.md` e em `bdd/`, quando o projeto usa BDD), regras de negócio, roadmap, riscos, fora de escopo | Nomes de módulos, detalhes de implementação |
| `TDD.md` | Como: stack, componentes, estrutura de pastas, modelo de dados, pipelines, interfaces, configuração, segurança, desempenho, decisões | Justificativa de produto, passo a passo de uso |
| `README.md` | Uso: instalação, primeiros passos, comandos, interfaces expostas, configuração, publicação | Arquitetura interna, requisitos formais |

Os documentos descrevem o **estado atual**, não um changelog. Reescreva o trecho
desatualizado em vez de acrescentar "agora também faz X".

## Fluxo

```
Progresso:
- [ ] 1. Definir a base da última revisão
- [ ] 2. Levantar o que mudou no código
- [ ] 3. Confrontar mudanças com cada documento
- [ ] 4. Editar os documentos
- [ ] 5. Verificar consistência
- [ ] 6. Gravar a base revisada
- [ ] 7. Relatar
```

### 1. Definir a base

A base fica gravada no marcador `.agents/last-reviewed-commit` (uma linha com
o hash completo; o `HARNESS.md` pode indicar outro caminho). Ordem de escolha:

1. Commit, tag ou data indicados pelo usuário.
2. O hash do marcador, se existir e for ancestral de `HEAD`. Um hash que não é
   ancestral (marcador copiado de outro repositório, histórico reescrito) é
   ignorado.
3. Senão, o último commit que alterou algum dos três documentos.

```bash
MARK=.agents/last-reviewed-commit
BASE=$(cat "$MARK" 2>/dev/null)
if [ -z "$BASE" ] || ! git merge-base --is-ancestor "$BASE" HEAD 2>/dev/null; then
  BASE=$(git log -1 --format=%H -- PRD.md TDD.md README.md)
fi
git log --oneline "$BASE"..HEAD
```

Se `BASE` for igual a `HEAD` e não houver mudanças não commitadas fora dos
documentos, informe que a documentação já está em dia e encerre.

- Se `PRD.md`, `TDD.md` ou `README.md` tiverem alterações não commitadas, elas
  são edições em andamento do usuário: **preserve-as** e trabalhe sobre elas.

### 2. Levantar o que mudou

```bash
git diff --stat "$BASE"..HEAD -- . ':!*.md'
git diff "$BASE"..HEAD -- . ':!*.md'
git status --porcelain
```

- Inclua mudanças não commitadas e arquivos não rastreados (`git diff`,
  `git status`). Ignore caches, artefatos de build e tudo que o `.gitignore`
  exclui.
- Leia os arquivos novos ou muito alterados por inteiro; o diff sozinho não
  mostra o contrato público.
- Confira a versão no manifesto do projeto (`pyproject.toml`, `package.json`,
  `*.csproj`, `Cargo.toml` ou equivalente) e as tags
  (`git tag --sort=-v:refname`).

Classifique cada mudança relevante:

- **Capacidade** nova, alterada ou removida (comando, endpoint, ferramenta,
  tela, recurso exposto).
- **Contrato**: parâmetros, retornos, erros, chaves de configuração, padrões.
- **Estrutura**: módulos, camadas, dependências, modelo de dados.
- **Operação**: instalação, publicação, plataformas, requisitos.
- **Interna** sem efeito visível: geralmente não vai para nenhum documento, exceto
  se mudar arquitetura ou decisão registrada no `TDD.md`.

### 3. Confrontar com os documentos

Para cada mudança, decida o documento dono (tabela acima) e procure o trecho
afetado com `rg` ou `git grep`. Pontos que costumam ficar defasados:

- **PRD.md**: cabeçalho (status, data, versão), tabela de requisitos (inclusive
  prioridade e se já está entregue), histórias (critérios de aceite só se o
  projeto não usa BDD), regras de negócio, roadmap (mover itens de "Próximo" para "Entregue"; contagens de
  capacidades), riscos.
- **TDD.md**: stack e versões de dependências, árvore da estrutura do projeto,
  componentes, modelo de dados, pipelines, interfaces, exemplos de
  configuração, segurança, desempenho, decisões arquiteturais, evolução.
- **README.md**: instalação, primeiros passos, comandos e flags, lista de
  capacidades expostas, configuração, publicação.

Valide também o inverso: algo documentado que **não existe mais** no código deve
ser removido ou corrigido.

Se o projeto usa BDD (`BDD.md` e `bdd/`), não copie critérios de aceite para os
documentos. Se uma mudança altera comportamento sem cenário correspondente,
registre em **Pendências** e sugira o cenário; não grave em `bdd/`.

### 4. Editar

- Toda afirmação nova deve ser verificada no código (nome exato de comando,
  flag, chave de configuração, valor padrão). Não documente o que não está
  implementado.
- Mantenha estilo, tom, numeração (RF-NN, seções) e formatação de cada documento.
  Novos requisitos recebem o próximo número livre; não renumere os existentes.
- Atualize a data do cabeçalho do `PRD.md` para hoje e o status se a versão
  entregue mudou.
- Se uma mudança for ambígua ou contradizer o PRD (comportamento diferente do
  requisito), **não decida sozinho**: registre no relatório e pergunte se o
  código ou o documento está certo.

### 5. Verificar consistência

- Mesma contagem e mesmos nomes de capacidades e comandos nos três documentos.
- Mesmas chaves e padrões de configuração entre `TDD.md` e `README.md`.
- Links relativos entre documentos continuam válidos.
- Nenhum fato duplicado em detalhe em mais de um documento.

### 6. Gravar a base revisada

Grave o `HEAD` atual no marcador, sobrescrevendo o valor anterior:

```bash
mkdir -p .agents
git rev-parse HEAD > .agents/last-reviewed-commit
```

Mudanças não commitadas que entraram nesta revisão aparecerão de novo no
próximo diff, depois de commitadas. Confirme rapidamente que já estão
documentadas e siga em frente.

### 7. Relatar

```markdown
# Documentação atualizada — <BASE curto>..<HEAD curto>

## Mudanças no código consideradas
- <mudança> → <documento(s) atualizado(s)>

## Alterações por documento
- **PRD.md:** <seções alteradas>
- **TDD.md:** <seções alteradas>
- **README.md:** <seções alteradas>

## Pendências
- <divergência código × PRD, ambiguidade ou decisão que cabe ao usuário>
```

Omita "Pendências" se não houver nenhuma.
