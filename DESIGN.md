# DESIGN — Nix

Estilo da interface local (`nix ui`) e da CLI. As duas superfícies compartilham a paleta. A interface local está em `src/nix/web/static/nix.css`; a CLI usa o mesmo acento e as mesmas cores de status no tema Rich de `src/nix/cli/render.py`.

Não há build, fonte remota nem modo escuro. O fundo do terminal é o do usuário: na CLI, texto normal e `dim` seguem o tema do terminal; só o acento e o status têm cor fixa.

## Cores

| Token | Valor | Uso |
| --- | --- | --- |
| `bg` / `surface` | `#FFFFFF` | Fundo da página e dos cartões |
| `ink` | `#222222` | Texto principal, botão secundário, foco |
| `muted` | `#6A6A6A` | Rótulos, navegação inativa, texto de apoio |
| `line` | `#DDDDDD` | Bordas, divisórias de lista e tabela |
| `soft` | `#F7F7F7` | Preenchimento leve, campo desligado, trilha da barra |
| `soft-2` | `#F2F2F2` | Item de navegação atual, aviso informativo |
| `on-ink` | `#FFFFFF` | Texto sobre fundo `ink` ou sobre o acento |
| `accent` | `#FF385C` | Ação principal, barra de progresso, caixa marcada |
| `accent-active` | `#E00B41` | Ação principal sob o ponteiro; link de título em hover |
| `accent-line` | `#FFD1DA` | Contorno claro do acento, quando um selo precisa da marca sem preencher |
| `ok` / `ok-soft` | `#04694A` / `#E3F3EB` | Sucesso, diff de linha adicionada |
| `warn` / `warn-ink` / `warn-soft` | `#8A5300` / `#6B4100` / `#FCF1DD` | Aviso; o texto do aviso usa `warn-ink` |
| `err` / `err-soft` | `#C13515` / `#FDECEA` | Erro, ação destrutiva, diff de linha removida |
| `code-bg` / `code-fg` | `#222222` / `#E8EAEE` | Bloco de código |
| `mark` | `#FFF1B8` | Trecho destacado na busca |

Sombra única, em cartão com link sob o ponteiro e na aba selecionada:

`rgba(0, 0, 0, .02) 0 0 0 1px, rgba(0, 0, 0, .04) 0 2px 6px, rgba(0, 0, 0, .1) 0 4px 8px`

## Tipografia

Família: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.

Monoespaçada, para caminho, código, diff e linhas de nota: `ui-monospace, "Cascadia Mono", Consolas, "SF Mono", monospace`.

| Uso | Tamanho | Peso |
| --- | --- | --- |
| Título da página (`h1`) | 28px | 700 |
| Número de indicador | 28px | 700 |
| Número de indicador com ícone | 22px | 700 |
| Título de cartão | 16px | 600 |
| Botão | 16px | 500 |
| Corpo | 14px | 400, linha 1.5 |
| Botão compacto e título de resultado | 14px / 15px | 500 / 600 |
| Rótulo, selo, nota de indicador | 12px | 500–600 |
| Código, caminho, tabela de diff | 12.5px | 400, linha 1.6 |

Rótulo de grupo na navegação: 11px, peso 600, caixa alta, espaçamento de 0.06em, cor `muted`.

## Espaço e raio

| Token | Valor | Uso |
| --- | --- | --- |
| Raio de botão, campo, navegação e chip | 8px | Controles |
| Raio de cartão, aviso, bloco de código e seletor de abas | 14px | Superfícies |
| Raio de selo, barra e versão | 999px | Pílula |
| Altura mínima do botão | 48px | Alvo de toque |
| Altura mínima do botão compacto | 40px | Ação secundária dentro de aviso ou lista |
| Altura mínima do campo | 56px | Texto e seleção |
| Padding da área principal | 36px 40px 56px | Desktop |
| Largura máxima do conteúdo | 1080px | Coluna central |
| Largura da navegação | base 240px | Barra lateral |

## Layout

A página é uma barra lateral e uma coluna principal.

A barra mostra a marca `nix`, a versão, o seletor **Vault ativo** (nome e caminho) e quatro grupos: Operação (Status, Sincronizar, Diagnóstico), Vault (Busca, Notas, Tags, Insights), Integração (Conectar cliente, Tráfego MCP, Sessões) e Manutenção (Backups, Vaults, Configuração, Histórico). No pé, o botão Encerrar.

O item atual usa fundo `soft-2`, texto `ink` e peso 600. Os outros usam `muted`. Hover usa fundo `soft`.

Abaixo de 760px a barra ocupa a largura inteira, os grupos viram uma faixa horizontal com rolagem, e os rótulos dos grupos e o botão Encerrar saem da barra. O caminho do vault ativo fica numa linha só, com reticências.

## Componentes

**Botão.** Fundo branco, borda `ink`, texto `ink`, raio 8px. Hover: fundo `soft`.

**Botão primário.** Fundo e borda `accent`, texto branco. Hover: `accent-active`. É a ação da tela (por exemplo Sincronizar).

**Botão destrutivo.** Texto e borda `err`. Hover: fundo `err-soft`.

**Botão desligado.** Opacidade 0.6 e cursor de progresso. Enquanto a sincronização roda, o grupo inteiro de controles fica desligado.

**Cartão.** Fundo branco, borda `line`, raio 14px, padding 20px. O cartão que é link ganha a sombra única no hover.

**Indicador.** Rótulo `muted` de 12px e valor de 28px. Valor com erro usa `err`; com aviso, `warn`; em dia, `ok`.

**Aviso.** Faixa com raio 14px. Sucesso em `ok-soft`, aviso em `warn-soft` com texto `warn-ink`, erro em `err-soft`, informação em `soft-2`.

**Selo.** Pílula de 12px. Sucesso, aviso e erro usam o par cor/fundo correspondente. Neutro usa `soft` e `muted`. O selo de destaque tem fundo branco e contorno interno `accent`.

**Campo.** Borda `line`, raio 8px, altura 56px. Desligado: fundo `soft` e texto `muted`. Foco: contorno de 2px em `ink`, deslocado 2px. O mesmo contorno vale para botão, item de navegação e caixa de seleção. A caixa de seleção usa `accent`.

**Tabela.** Cabeçalho `soft`, texto `muted`, 12px. Célula com divisória `line`. A caixa da tabela tem borda e raio 14px.

**Código.** Fundo `code-bg`, texto `code-fg`, raio 14px. O handoff de sessão é a exceção: fundo `soft-2`, texto `ink` e borda `line`, com quebra de linha.

**Diff.** Linha adicionada em `ok-soft`, removida em `err-soft`, contexto sem fundo, intervalo em `soft-2`.

**Barra de progresso.** Altura 8px, trilha `soft`, preenchimento `accent`, pílula. Com `prefers-reduced-motion`, a transição some.

**Abas.** Trilha `soft-2`, raio 14px. A aba atual tem fundo branco, texto `ink` e a sombra única.

**Busca.** Cada trecho é um bloco: título de 15px, caminho em mono, recorte com no máximo 12em de altura. O termo achado usa fundo `mark`.

**Estado vazio.** Padding 32px 16px, texto central `muted`.

## CLI

Painel, tabela e barra de progresso usam a paleta acima: acento `#FF385C`, sucesso `#04694A`, aviso `#8A5300`, erro `#C13515`. A barra concluída fica em sucesso; a barra em andamento fica no acento. Erro de domínio sai em stderr, sem traceback.
