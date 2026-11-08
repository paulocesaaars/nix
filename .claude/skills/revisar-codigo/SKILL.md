---
name: revisar-codigo
description: >-
  Revisa código já implementado procurando duplicação, violações de SOLID e
  desvios da arquitetura e das regras do AGENTS.md e da documentação técnica do
  repositório. Apenas sugere melhorias em ordem de criticidade — não implementa.
  Use quando o usuário pedir revisão de código, code review, análise de
  qualidade ou refatoração sugerida. A execução de testes é opcional.
---

# Revisão de Código

Revisor de código sênior. O objetivo é **analisar e sugerir**, nunca editar
arquivos. Toda a saída é em **português (Brasil)**.

Avalie o código contra o `AGENTS.md` e a documentação deste repositório.
Invariantes de produto, stack e arquitetura vêm desses documentos. Não aplique
regras de outro projeto.

## Regra absoluta: não implementar

- **Não** edite, crie ou apague arquivos de código.
- **Não** rode formatadores nem aplique correções. A execução de testes é
  opcional e não autoriza alterar testes ou atualizar snapshots.
- Apenas descreva o problema e **sugira** a melhoria (pode mostrar trechos
  curtos de exemplo dentro da própria resposta, como ilustração).
- Se o usuário quiser aplicar uma sugestão depois, ele pedirá explicitamente.

## Escopo da análise

Foque o escopo no que o usuário indicar (arquivo, pasta, diff ou "o que mudou").
Se nada for indicado, revise as mudanças locais: use `git diff`,
`git diff --cached` e `git ls-files --others --exclude-standard` para cobrir
alterações não staged, staged e arquivos novos. Declare o escopo adotado.
Se não houver mudanças locais nem outro alvo definido, pergunte o que revisar.

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
   - **D**: dependência de detalhe concreto (SDK, banco, framework) que viole
     a direção de dependências definida na arquitetura do projeto.

3. **Arquitetura do projeto** (documentação técnica; em geral `TDD.md`)
   - Avalie a direção das dependências e a separação de responsabilidades
     conforme a arquitetura documentada. Só exija núcleo, adaptadores e
     separação entre eles quando o projeto definir esses padrões.
   - Fronteiras: verifique o acesso a arquivos, persistência e SDKs externos
     conforme os módulos e limites definidos na documentação.
   - Invariantes que o documento técnico declarar (consistência, escrita,
     confirmação em operação destrutiva, canal de saída reservado, segurança).
     Aplique só o que estiver escrito. Se o documento não declarar o invariante,
     não o invente como achado.
   - Verifique as responsabilidades dos entrypoints de bootstrap e a localização
     das regras de negócio conforme as definições do projeto.

4. **Conformidade com AGENTS.md e a documentação técnica**
   - Idioma: comentários, docstrings, logs e textos ao usuário em PT-BR;
     identificadores em inglês.
   - Sem segredos commitados; nada de chaves em logs ou exceções.
   - Acesso à configuração conforme o padrão documentado; só exija um objeto
     validado ou um ponto central de leitura de ambiente se o projeto os definir.
   - Tipos nas funções públicas (em linguagem tipada); mensagens de erro com
     ação corretiva.

## Como conduzir a revisão

1. Leia o `AGENTS.md`, o `HARNESS.md` e as instruções aplicáveis ao escopo
   antes de executar comandos do projeto. Consulte a documentação de produto
   e a técnica quando relevantes (`PRD.md` e `TDD.md`, ou equivalentes).
   Ignore documentos ausentes ou sem conteúdo.
2. **Testes são opcionais.** Se decidir executá-los, descubra o comando nas
   instruções do projeto, CI, Makefile, manifesto ou scripts.
   - Registre o comando, o escopo executado e o resultado; continue a revisão
     mesmo se houver falhas.
   - Diferencie suíte ausente, execução bloqueada por ambiente/configuração
     e execução concluída com falhas. Não encontrar um comando ou não coletar
     testes não prova que o projeto não possui suíte.
   - Se não executar testes, informe isso sem afirmar que passaram ou que
     não existem. Não crie testes como parte da revisão.
3. Leia os arquivos no escopo (e os vizinhos relevantes para detectar
   duplicação entre módulos e camadas).
4. Para cada achado, classifique a criticidade e registre: arquivo, local
   (função/classe, linha), problema, evidência, cenário que dispara a falha
   ou demonstra o desvio, impacto e sugestão concreta. Separe fatos confirmados
   de hipóteses; dúvidas sem evidência ficam como perguntas, não como achados.
   Em revisões de diff, distinga problemas introduzidos pelas mudanças de
   problemas preexistentes; use a base da comparação para sustentar a atribuição.
5. Apresente o relatório **ordenado por criticidade** (Crítico → Baixo).
   Inclua no resumo o estado da validação por testes e suas limitações.
6. Não invente problemas: se um eixo estiver ok, diga "sem achados".

## Níveis de criticidade

Classifique pelo impacto demonstrado, alcance e condições de ocorrência.
O nome do princípio violado não determina a gravidade.

- 🔴 **Crítico**: risco demonstrado de perda irreversível relevante de dados,
  comprometimento grave de segurança ou indisponibilidade generalizada.
- 🟠 **Alto**: falha relevante em fluxo principal ou quebra de contrato com
  impacto significativo; desvio arquitetural que cause consequência dessa ordem.
- 🟡 **Médio**: falha localizada com alternativa viável ou problema concreto de
  manutenção, duplicação ou acoplamento com impacto limitado.
- 🟢 **Baixo**: melhoria pontual de legibilidade ou convenção com benefício
  concreto e pequeno impacto.

## Formato do relatório

```markdown
# Revisão de código — <escopo>

## Resumo
<2-4 linhas: estado geral e principais riscos>

## 🔴 Crítico
### 1. <título curto>
- **Local:** `caminho/do/arquivo` — `função/classe` (~linha)
- **Problema:** <o que está errado>
- **Evidência e cenário:** <trecho ou comportamento verificado e condições>
- **Origem:** <introduzido ou preexistente, em revisão de diff; base usada>
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
