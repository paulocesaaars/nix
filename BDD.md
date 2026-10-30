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
| HU-02 | Indexar um vault existente | [`bdd/HU-02-indexar-vault.md`](./bdd/HU-02-indexar-vault.md) |
| HU-03 | Sincronizar mudanças feitas no Obsidian | [`bdd/HU-03-sincronizar-mudancas.md`](./bdd/HU-03-sincronizar-mudancas.md) |
| HU-05 | Registrar conhecimento pelo editor | [`bdd/HU-05-registrar-conhecimento.md`](./bdd/HU-05-registrar-conhecimento.md) |
| HU-06 | Usar o Nix dentro do editor | [`bdd/HU-06-usar-no-editor.md`](./bdd/HU-06-usar-no-editor.md) |
| HU-08 | Configurar e operar pela interface | [`bdd/HU-08-operar-pela-interface.md`](./bdd/HU-08-operar-pela-interface.md) |
| HU-09 | Ferramenta sem vault | [`bdd/HU-09-ferramenta-sem-vault.md`](./bdd/HU-09-ferramenta-sem-vault.md) |
| HU-10 | Vault inexistente | [`bdd/HU-10-vault-inexistente.md`](./bdd/HU-10-vault-inexistente.md) |
| HU-11 | Escrita recebendo lista | [`bdd/HU-11-escrita-com-lista.md`](./bdd/HU-11-escrita-com-lista.md) |
| HU-12 | Busca em todos os vaults | [`bdd/HU-12-busca-em-todos.md`](./bdd/HU-12-busca-em-todos.md) |
| HU-13 | Remover o padrão | [`bdd/HU-13-remover-padrao.md`](./bdd/HU-13-remover-padrao.md) |
| HU-14 | Botões desligados durante o sync | [`bdd/HU-14-botoes-durante-sync.md`](./bdd/HU-14-botoes-durante-sync.md) |
| HU-15 | Continuar a partir de uma sessão | [`bdd/HU-15-continuar-sessao.md`](./bdd/HU-15-continuar-sessao.md) |
