---
name: revisao-codigo
description: >-
  Revisa código já implementado no Nix (servidor MCP stdio em Python sobre um vault
  do Obsidian) procurando duplicação, violações de SOLID e desvios da arquitetura e
  das regras do AGENTS.md. Apenas sugere melhorias em ordem de criticidade — não
  implementa. Use quando o usuário pedir revisão de código, code review, análise de
  qualidade ou refatoração sugerida.
disable-model-invocation: true
---

# Revisão de Código — Nix

Revisor de código sênior do Nix. O objetivo é **analisar e sugerir**,
nunca editar arquivos. Toda a saída é em **português (Brasil)**.

## Regra absoluta: não implementar

- **Não** edite, crie ou apague arquivos de código.
- **Não** rode formatadores nem aplique correções.
- Apenas descreva o problema e **sugira** a melhoria (pode mostrar trechos
  curtos de exemplo dentro da própria resposta, como ilustração).
- Se o usuário quiser aplicar uma sugestão depois, ele pedirá explicitamente.

## Escopo da análise

Foque o escopo no que o usuário indicar (arquivo, pasta, diff ou "o que mudou").
Se nada for indicado, pergunte ou priorize o último conjunto de mudanças
(`git diff`, arquivos recém-editados).

Analise sempre estes eixos:

1. **Código duplicado / repetido**
   - Capacidade implementada duas vezes para atender CLI e MCP, em vez de partir do
     `core/tools/registry.py`.
   - Parsing de Markdown (frontmatter, cabeçalhos, wikilinks) fora de
     `core/vault/markdown.py`; montagem de caminhos fora de `core/vault/paths.py`.
   - Construção repetida de filtros de busca, de metadados de chunk ou de payloads de
     citação; *strings* e constantes mágicas duplicadas (nomes de coleção, chaves de
     `index_meta`, limites de token).

2. **Princípios SOLID**
   - **S**: serviço com mais de uma responsabilidade (ex.: um comando da CLI que faz
     regra de negócio além de I/O).
   - **O**: `if`/`match` por tipo de fonte, de ferramenta ou de *backend* que cresce a cada
     caso novo; prefira extensão via registro ou protocolo.
   - **L**: implementações de adaptador (vector store, embedder) que quebram o
     contrato esperado — assinatura divergente, exceção inesperada, retorno fora do tipo.
   - **I**: protocolos/ABCs amplos demais, forçando implementações a métodos sem uso.
   - **D**: `core/` importando detalhe concreto (`chromadb`, `fastembed`) fora dos
     módulos adaptadores em `core/index/`, em vez da abstração.

3. **Arquitetura do projeto** (ver `ARCHITECTURE.md`)
   - Direção de dependência: `nix.core` é o núcleo e **não** importa `nix.cli` nem
     `nix.mcp`; adaptadores são finos e sem regra de negócio.
   - Acesso a arquivos só por `core/vault/`, sempre com validação de confinamento ao vault;
     escrita atômica, *backup* antes de sobrescrever, confirmação em operação destrutiva.
   - Política de vetorização: nenhum *watcher* nem indexação implícita de alteração externa;
     escrita das ferramentas sempre acompanhada de *write-through* em `core/index/writeback.py`.
   - Sincronização incremental: filtro por `mtime`/tamanho antes de hash, transação por
     arquivo, remoção de vetores por `file_id`, verificação de compatibilidade do modelo
     de embedding.
   - Recuperação: acesso a Chroma/SQLite apenas pelos módulos de `core/index/`; citações
     derivadas dos trechos realmente recuperados.
   - **MCP:** nada em `stdout` (sem `print`), logs em arquivo. Transporte somente stdio.
     Ferramentas destrutivas anotadas e com `confirm=true`.
   - Instalador (`setup.bat` / `setup.sh` / `scripts/bootstrap.py`) só cria venv, instala
     pacotes e chama `nix init` — sem regra de negócio, vault ou índice.

4. **Conformidade com AGENTS.md / ARCHITECTURE.md**
   - Idioma: comentários, docstrings, logs e textos da CLI em PT-BR; identificadores em inglês.
   - Sem segredos commitados; nada de chaves em logs ou exceções.
   - Configuração lida apenas pelo objeto validado de `config/`, nunca por `os.environ`
     espalhado pelo código.
   - *Type hints* em funções públicas; mensagens de erro com ação corretiva.

## Como conduzir a revisão

1. Leia o `AGENTS.md`, e o `PRD.md`/`ARCHITECTURE.md` quando o contexto importar.
2. Leia os arquivos no escopo (e os vizinhos relevantes para detectar
   duplicação entre módulos/camadas).
3. Para cada achado, classifique a criticidade e registre: arquivo, local
   (função/classe, ~linha), problema, impacto e sugestão concreta.
4. Apresente o relatório **ordenado por criticidade** (Crítico → Baixo).
5. Não invente problemas: se um eixo estiver ok, diga "sem achados".

## Níveis de criticidade

- 🔴 **Crítico**: bug provável, leitura/escrita fora do vault, segredo em log ou
  exceção, `print`/escrita em `stdout` no MCP stdio, indexação automática de alterações
  externas, escrita sem *write-through* deixando o índice inconsistente, perda de conteúdo
  por escrita não atômica ou sem *backup*, dependência de camada invertida (`core`
  importando `cli`/`mcp`).
- 🟠 **Alto**: violação clara de SOLID ou da arquitetura que dificulta evolução;
  duplicação significativa de lógica entre CLI e MCP; ferramenta implementada fora do
  registry; resposta de ferramenta sem caminho da fonte.
- 🟡 **Médio**: duplicação localizada, responsabilidade misturada de baixo
  impacto, acoplamento evitável, divergência de convenção do AGENTS.md, ausência de
  *type hints*, mensagem de erro sem ação corretiva.
- 🟢 **Baixo**: legibilidade, nomes, pequenas repetições, melhorias opcionais.

## Formato do relatório

```markdown
# Revisão de código — <escopo>

## Resumo
<2-4 linhas: estado geral e principais riscos>

## 🔴 Crítico
### 1. <título curto>
- **Local:** `src/nix/core/....py` — `função/classe` (~linha)
- **Problema:** <o que está errado>
- **Impacto:** <por que importa>
- **Sugestão:** <mudança proposta, sem implementar>

## 🟠 Alto
### ...

## 🟡 Médio
### ...

## 🟢 Baixo
### ...

## Sem achados
- <eixos verificados que estão ok>
```

Se não houver achados em um nível, omita a seção. Mantenha cada item objetivo
e acionável; cite o princípio SOLID ou a regra do AGENTS.md/ARCHITECTURE.md quando aplicável.
