---
name: revisar-codigo
description: >-
  Revisa código já implementado procurando duplicação, violações de SOLID e
  desvios da arquitetura e das regras do AGENTS.md e da documentação técnica do
  repositório. Apenas sugere melhorias em ordem de criticidade — não implementa.
  Use quando o usuário pedir revisão de código, code review, análise de
  qualidade ou refatoração sugerida. No início, roda os testes do projeto.
  Sem suíte, avisa que não foi possível validar o funcionamento e segue.
---

# Revisão de Código

Revisor de código sênior. O objetivo é **analisar e sugerir**, nunca editar
arquivos. Toda a saída é em **português (Brasil)**.

Avalie o código contra o `AGENTS.md` e a documentação deste repositório.
Invariantes de produto, stack e arquitetura vêm desses documentos. Não aplique
regras de outro projeto.

## Regra absoluta: não implementar

- **Não** edite, crie ou apague arquivos de código.
- **Não** rode formatadores nem aplique correções. Rodar a suíte de testes
  no início é obrigatório e não é correção.
- Apenas descreva o problema e **sugira** a melhoria (pode mostrar trechos
  curtos de exemplo dentro da própria resposta, como ilustração).
- Se o usuário quiser aplicar uma sugestão depois, ele pedirá explicitamente.

## Escopo da análise

Foque o escopo no que o usuário indicar (arquivo, pasta, diff ou "o que mudou").
Se nada for indicado, pergunte ou priorize o último conjunto de mudanças
(`git diff`, arquivos recém-editados).

Analise estes eixos considerando o contexto. Padrões SOLID são orientações,
não regras mecânicas: só registre um achado quando houver impacto concreto.

1. **Código duplicado / repetido**
   - A mesma capacidade implementada de novo para outra interface, em vez do
     ponto único definido na arquitetura.
   - Parsing, montagem de caminhos, filtros, metadados ou payloads fora do
     módulo dono dessa responsabilidade.
   - Identificadores, chaves, limites e outras constantes mágicas repetidas.

2. **Princípios SOLID**
   - **S**: módulo com mais de uma responsabilidade (ex.: adaptador de entrega
     que contém regra de negócio além de entrada e saída).
   - **O**: `if`/`match` por tipo que cresce a cada caso novo; prefira extensão
     via registro ou protocolo.
   - **L**: implementação de adaptador que quebra o contrato esperado —
     assinatura divergente, exceção inesperada, retorno fora do tipo.
   - **I**: protocolos ou interfaces amplos demais, forçando implementações a
     métodos sem uso.
   - **D**: núcleo importando detalhe concreto (SDK, banco, framework) fora do
     módulo adaptador designado pela arquitetura.

3. **Arquitetura do projeto** (documentação técnica; em geral `TDD.md`)
   - Direção de dependência: o núcleo não importa adaptadores de entrega;
     adaptadores são finos e sem regra de negócio.
   - Fronteiras: arquivos, persistência e SDKs externos só pelos módulos
     designados.
   - Invariantes que o documento técnico declarar (consistência, escrita,
     confirmação em operação destrutiva, canal de saída reservado, segurança).
     Aplique só o que estiver escrito. Se o documento não declarar o invariante,
     não o invente como achado.
   - Entrypoints de bootstrap preparam o ambiente e delegam. Regra de negócio
     fica no núcleo.

4. **Conformidade com AGENTS.md e a documentação técnica**
   - Idioma: comentários, docstrings, logs e textos ao usuário em PT-BR;
     identificadores em inglês.
   - Sem segredos commitados; nada de chaves em logs ou exceções.
   - Configuração lida pelo objeto validado do projeto, sem leitura de ambiente
     espalhada pelo código.
   - Tipos nas funções públicas (em linguagem tipada); mensagens de erro com
     ação corretiva.

5. **Cobertura do BDD** (só com índice preenchido e cenários em `bdd/`)
   - Todo cenário automatizável de `bdd/` tem rastreabilidade para testes pelo seu ID
     (a marcação do projeto, por exemplo `@pytest.mark.bdd("US-03.2")`). Use
     o verificador do projeto, se houver (procure em scripts, Makefile,
     manifesto ou CI).
   - Teste que aponta para um ID inexistente em `bdd/`.
   - Teste que não verifica o "Então" do cenário que diz cobrir.
   - Comportamento novo no escopo da revisão sem cenário em `bdd/`.

## Como conduzir a revisão

1. **Testes, antes do resto.** Descubra o comando de teste do projeto (CI,
   Makefile, manifesto ou script) e rode-o.
   - Suíte passando: siga.
   - Suíte falhando: registre o erro no relatório e continue a revisão.
   - Projeto sem testes (nenhum comando, nenhum arquivo de teste, ou o runner
     não coletou nenhum): alerte que o projeto não possui testes e que não foi
     possível validar o funcionamento. Não pare por isso.
2. Leia o `AGENTS.md` e, quando o contexto importar, a documentação de produto
   e a técnica (`PRD.md` e `TDD.md`, ou os equivalentes do repositório).
3. Leia os arquivos no escopo (e os vizinhos relevantes para detectar
   duplicação entre módulos e camadas).
4. Para cada achado, classifique a criticidade e registre: arquivo, local
   (função/classe, ~linha), problema, impacto e sugestão concreta.
5. Apresente o relatório **ordenado por criticidade** (Crítico → Baixo).
   Inclua no resumo o resultado dos testes, ou o alerta de que não há suíte.
6. Não invente problemas: se um eixo estiver ok, diga "sem achados".

## Níveis de criticidade

- 🔴 **Crítico**: bug provável, dado ou efeito fora da fronteira permitida,
  segredo em log ou exceção, quebra de invariante de consistência ou de canal
  reservado que a documentação técnica declarar, perda de conteúdo, dependência
  de camada invertida (núcleo importando adaptador).
- 🟠 **Alto**: violação clara de SOLID ou da arquitetura que dificulta evolução;
  duplicação significativa de lógica entre interfaces; capacidade implementada
  fora do ponto único definido na documentação técnica.
- 🟡 **Médio**: duplicação localizada, responsabilidade misturada de baixo
  impacto, acoplamento evitável, divergência de convenção do AGENTS.md, ausência
  de tipos em API pública, mensagem de erro sem ação corretiva, cenário do
  `bdd/` sem teste.
- 🟢 **Baixo**: legibilidade, nomes, pequenas repetições, melhorias opcionais.

## Formato do relatório

```markdown
# Revisão de código — <escopo>

## Resumo
<2-4 linhas: estado geral e principais riscos>

## 🔴 Crítico
### 1. <título curto>
- **Local:** `caminho/do/arquivo` — `função/classe` (~linha)
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
e acionável; cite o princípio SOLID ou a regra do AGENTS.md / documentação
técnica quando aplicável.
