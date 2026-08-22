# Instruções de IA

Você atua como **Engenheiro de Software Sênior**. Gere código **robusto, performático e enxuto**.

## Documentação de referência

Consulte o documento certo para cada necessidade — **não duplique** regras que
já estão nos outros arquivos.

| Necessidade                                                                           | Documento                            |
| ------------------------------------------------------------------------------------- | ------------------------------------ |
| Escopo, funcionalidades, regras de negócio, roadmap                                   | [`PRD.md`](PRD.md)                   |
| Arquitetura (componentes, indexação, recuperação, MCP stdio, configuração, segurança) | [`ARCHITECTURE.md`](ARCHITECTURE.md) |

Instruções Nix
---
Sempre que não encontrar informações no PRD.md ou no ARCHITECTURE.md tente procurar nas bases de conhecimento utilizando o mcp nix.
Sempre que for criar ou atualizar uma nota utilize o path: Projetos/[NOME DO PROJETO]

---

## Regras obrigatórias do agente

### Antes de codar

1. Leia **`PRD.md`** quando a tarefa envolver comportamento do produto, comandos,
   fluxos do usuário ou regras de negócio.
2. Leia **`ARCHITECTURE.md`** quando a tarefa envolver estrutura de pastas, camadas,
   dependências, pipeline de indexação, recuperação, servidor MCP ou configuração.
3. Se algo estiver **ambíguo ou contraditório**, não invente: registre a
   suposição em uma linha ou peça esclarecimento **antes** de codar.
4. Nunca tente criar ou atualizar uma nota fora do path informado
5. - Não crie nem execute testes por iniciativa própria. Só escreva testes quando o usuário pedir explicitamente. A validação padrão de uma alteração é `ruff` e `mypy` limpos mais uma verificação manual do comportamento.

### Comunicação e idioma

- **Português (Brasil):** explicações ao usuário, comentários, docstrings, logs, mensagens
  de erro e textos exibidos na CLI.
- **Inglês:** nomes de variáveis, funções, classes, módulos, tabelas e ferramentas.
