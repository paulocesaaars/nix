# BDD — Nix, critérios de aceite

Índice dos casos de uso. Os critérios de aceite de cada um ficam em
[`bdd/`](./bdd), em Gherkin (português), um arquivo por caso de uso. As
histórias e o porquê de cada uma ficam no [PRD.md](./PRD.md), com o mesmo ID.

## Convenções

- Cada `Funcionalidade` leva o ID da história (`@HU-03`). Cada `Cenário` leva
  um ID estável (`@HU-03.2`) que nunca é reaproveitado.
- O teste que cobre um cenário carrega o mesmo ID: `@pytest.mark.bdd("HU-03.2")`.
  `python scripts/check_bdd.py` lista os cenários sem teste.
- `@manual`: cenário de funcionalidade que depende de editor ou navegador.
  Vira checklist conferido à mão antes da release.
- O índice lista só funcionalidades do produto.
- Todo arquivo de `bdd/` aparece neste índice, e toda linha do índice aponta
  para um arquivo existente.

## Casos de uso

| ID | Caso de uso | Cenários |
|----|-------------|----------|
| HU-01 | Primeira configuração | [`bdd/HU-01-primeira-configuracao.md`](./bdd/HU-01-primeira-configuracao.md) |
| HU-02 | Indexar uma wiki existente | [`bdd/HU-02-indexar-wiki.md`](./bdd/HU-02-indexar-wiki.md) |
| HU-03 | Sincronizar mudanças feitas fora do Nix | [`bdd/HU-03-sincronizar-mudancas.md`](./bdd/HU-03-sincronizar-mudancas.md) |
| HU-05 | Registrar conhecimento pelo editor | [`bdd/HU-05-registrar-conhecimento.md`](./bdd/HU-05-registrar-conhecimento.md) |
| HU-06 | Usar o Nix dentro do editor | [`bdd/HU-06-usar-no-editor.md`](./bdd/HU-06-usar-no-editor.md) |
| HU-08 | Configurar e operar pela interface | [`bdd/HU-08-operar-pela-interface.md`](./bdd/HU-08-operar-pela-interface.md) |
| HU-09 | Ferramenta sem wiki | [`bdd/HU-09-ferramenta-sem-wiki.md`](./bdd/HU-09-ferramenta-sem-wiki.md) |
| HU-10 | Wiki inexistente | [`bdd/HU-10-wiki-inexistente.md`](./bdd/HU-10-wiki-inexistente.md) |
| HU-11 | Escrita recebendo lista | [`bdd/HU-11-escrita-com-lista.md`](./bdd/HU-11-escrita-com-lista.md) |
| HU-12 | Busca em todas as wikis | [`bdd/HU-12-busca-em-todos.md`](./bdd/HU-12-busca-em-todos.md) |
| HU-13 | Remover a padrão | [`bdd/HU-13-remover-padrao.md`](./bdd/HU-13-remover-padrao.md) |
| HU-14 | Botões desligados durante o sync | [`bdd/HU-14-botoes-durante-sync.md`](./bdd/HU-14-botoes-durante-sync.md) |
| HU-16 | Wiki genérica | [`bdd/HU-16-wiki-generica.md`](./bdd/HU-16-wiki-generica.md) |
| HU-17 | Capturar sessões no Mega Brain | [`bdd/HU-17-capturar-sessoes.md`](./bdd/HU-17-capturar-sessoes.md) |
| HU-18 | Briefing e handoff | [`bdd/HU-18-briefing-e-handoff.md`](./bdd/HU-18-briefing-e-handoff.md) |
| HU-19 | Perfil entre projetos | [`bdd/HU-19-perfil-entre-projetos.md`](./bdd/HU-19-perfil-entre-projetos.md) |
| HU-20 | Mensagens entre agentes | [`bdd/HU-20-mensagens-entre-agentes.md`](./bdd/HU-20-mensagens-entre-agentes.md) |
| HU-21 | Contagem de tokens | [`bdd/HU-21-tokens.md`](./bdd/HU-21-tokens.md) |
| HU-22 | Painel do Mega Brain | [`bdd/HU-22-painel-mega-brain.md`](./bdd/HU-22-painel-mega-brain.md) |
| HU-23 | Cota de wikis | [`bdd/HU-23-cota-de-wikis.md`](./bdd/HU-23-cota-de-wikis.md) |
