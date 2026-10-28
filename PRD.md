# PRD — Nix, Servidor MCP de Conhecimento

| Campo | Valor |
| --- | --- |
| Produto | **Nix** (nome inspirado na Lulu, cachorra do autor) |
| Tipo | Servidor MCP que expõe vaults Obsidian a agentes de desenvolvimento |
| Interfaces | MCP stdio (único transporte do protocolo); CLI (`init`, `vault`, `config`, `sync`, `status`, `doctor`, `ui`, `session`, `hooks`, `skills`); interface local só enquanto `nix ui` está aberto; instalador `install.bat` / `install.sh` (`nix` e `nix-hook` em `NIX_HOME`, `nix` no PATH, sem Python); desinstalador `uninstall.bat` / `uninstall.sh` |
| Status | Implementado — v2.4.1 |
| Autor | Paulo |
| Data | 2026-10-27 |

Especificações técnicas: [TDD.md](./TDD.md). Critérios de aceite: [BDD.md](./BDD.md).

---

## 1. Visão

Nix é a ponte entre bases de conhecimento em Markdown (Obsidian) e agentes de desenvolvimento como Cursor, Claude Code, Copilot, Devin CLI e Devin Desktop. Em vez de o usuário lembrar onde cada anotação foi salva, o agente do editor chama ferramentas do Nix para buscar, ler, criar e atualizar notas — com o índice local sempre alinhado às escritas do próprio Nix.

Tudo roda na máquina do usuário. Embeddings e banco vetorial são locais e gratuitos. Não há LLM no Nix: o raciocínio fica no cliente MCP.

## 2. Problema

Vaults de Obsidian crescem rápido e viram um arquivo morto. Hoje o usuário enfrenta:

- **Busca literal insuficiente.** A busca do Obsidian encontra palavras, não ideias. Quem não lembra o termo exato usado não acha a nota.
- **Conhecimento fragmentado.** A resposta para uma pergunta costuma estar espalhada em várias notas, e sintetizar isso manualmente é caro.
- **Captura com atrito.** Registrar uma nota nova no formato certo, com os links e tags corretos, exige abrir o Obsidian e lembrar das convenções.
- **Agentes de desenvolvimento não conhecem o vault.** Cursor, Claude Code, Copilot, Devin CLI e Devin Desktop não têm, por padrão, busca semântica nem escrita segura nas anotações pessoais.

## 3. Objetivos

| # | Objetivo | Como será medido |
| --- | --- | --- |
| O1 | Entregar trechos relevantes do vault ao cliente MCP, com caminho e citação da nota | ≥ 90% das buscas trazem a nota certa no top-5 em um conjunto de 30 perguntas de avaliação |
| O2 | Dar ao usuário controle explícito sobre quando a base é vetorizada | Nenhuma vetorização de arquivos externos ocorre sem `nix sync` ou `sync_index` |
| O3 | Manter o índice consistente após edições feitas pelas ferramentas | 100% das escritas via MCP refletidas no índice ao final da operação |
| O4 | Custo zero e privacidade | Embeddings e banco vetorial 100% locais e gratuitos; nenhuma chamada remota |
| O5 | Encaixar no fluxo do editor | Registrável como servidor MCP stdio em Cursor, Claude Code, Copilot, Devin CLI e Devin Desktop |

### Não-objetivos (v1)

- Não é um substituto do Obsidian. A interface local cobre configuração, operação e consulta (status, sincronização, diagnóstico, busca, notas, tags, insights, conexão de clientes, tráfego MCP, backups e histórico), não a edição das notas. A única escrita no vault pela interface é restaurar um backup, com confirmação explícita.
- Não haverá LLM, chat, RAG conversacional nem orquestração de agente no Nix.
- O MCP não tem transporte HTTP. Não haverá servidor multiusuário, autenticação de contas nem hospedagem em nuvem. A interface local escuta só em `127.0.0.1` enquanto `nix ui` está aberto.
- Não haverá sincronização de vault entre máquinas (isso é responsabilidade do Obsidian Sync/Git/Dropbox).
- Não haverá edição de anexos binários (PDFs, imagens) na v1 — apenas extração de texto de PDFs referenciados pelas notas, se `index.index_attachments` estiver ativo.
- Não haverá fine-tuning de modelos.

## 4. Persona e contexto de uso

**Paulo — desenvolvedor, usuário avançado de Obsidian.** Mantém um vault com notas técnicas, de projetos, de leituras e diário. É confortável com terminal e com arquivos de configuração. Usa Cursor no dia a dia e quer o vault disponível dentro do editor via MCP. Valoriza controle: não quer que um processo em background fique lendo e reprocessando o vault sem sua autorização.

**Momentos de uso principais:**

1. Durante o trabalho, no Cursor / Claude Code / Copilot, perguntando algo que sabe ter anotado antes.
2. Ao final de uma leitura ou reunião, pedindo ao agente do editor que registre uma nota nova no vault.
3. Depois de uma sessão de escrita direta no Obsidian, rodando `nix sync` (ou pedindo `sync_index`).

## 5. Escopo funcional

### 5.1 Configuração

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-01 | O sistema deve guardar a configuração num SQLite na pasta da instalação (`settings.db`), com os vaults nomeados (de 1 a 5, exatamente um padrão) e os demais parâmetros | Must |
| RF-02 | O sistema deve oferecer um comando de inicialização que grava o primeiro vault (nome `Default`, ou `--name`) e o caminho (`--vault` ou pergunta) e o modelo de embedding (`--embedding-model` ou pergunta) no `settings.db`. Se a configuração já existir, sem `--force` só atualiza o caminho do vault padrão, salvo `--embedding-model`. `--name` com vaults já cadastrados é recusado e pede `nix vault add`. Uma configuração anterior, com um único caminho de vault, passa a ser o vault `Default` e continua usando o índice e os backups já gravados. `--force` recria a configuração do zero, sem alterar as notas | Must |
| RF-03 | O sistema deve permitir sobrescrever a configuração global (`index`, `retrieval`, `safety`, `logging`) por variável de ambiente, e essa variável deve ganhar do valor gravado. O cadastro dos vaults não entra nessa precedência | Must |
| RF-04 | O sistema deve validar a configuração antes de gravar e apresentar mensagens de erro acionáveis (vault inexistente, modelo inválido, campo desconhecido) | Must |
| RF-05 | O sistema deve permitir configurar, por vault, padrões de inclusão/exclusão de arquivos e pastas (ex.: ignorar `Templates/`, `.trash/`, notas privadas), com `nix vault set NOME include\|exclude VALOR` | Should |
| RF-06 | O sistema deve permitir configurar modelo de embedding, tamanho de chunk e número de resultados recuperados | Should |

### 5.2 Sincronização e vetorização

Esta é a regra de negócio central do produto:

> **Alterações feitas fora do Nix nunca são vetorizadas automaticamente. Alterações feitas pelas ferramentas MCP são vetorizadas imediatamente.**

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-10 | O sistema deve oferecer sincronização explícita (`nix sync` e ferramenta `sync_index`) que indexa uma base existente ou reindexa o que mudou fora do Nix | Must |
| RF-11 | A sincronização deve ser incremental: apenas arquivos novos, modificados ou removidos são reprocessados | Must |
| RF-12 | A sincronização deve remover do índice os vetores de notas apagadas ou que passaram a ser ignoradas pelos filtros | Must |
| RF-13 | O sistema deve oferecer um modo de pré-visualização da sincronização (o que seria adicionado/atualizado/removido) sem alterar o índice | Should |
| RF-14 | O sistema deve oferecer reindexação completa forçada, para casos de troca de modelo de embedding ou corrupção do índice | Must |
| RF-15 | Escritas realizadas pelas ferramentas (criação, edição, anexação, remoção de nota) devem atualizar o índice na mesma operação | Must |
| RF-16 | `index_status` deve informar quando o índice estiver desatualizado em relação ao vault, sugerindo sincronizar — sem sincronizar por conta própria | Should |
| RF-17 | A sincronização via CLI deve exibir progresso e um resumo final (arquivos processados, chunks criados, tempo, erros) | Should |
| RF-18 | Falhas em arquivos individuais não devem abortar a sincronização; devem ser reportadas ao final | Must |

### 5.3 Busca e leitura

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-20 | O sistema deve buscar trechos relevantes no vault (híbrida: semântica + léxica) a partir de uma consulta | Must |
| RF-21 | Toda resposta de ferramenta baseada no vault deve incluir caminho relativo e trecho da fonte | Must |
| RF-22 | `index_status` deve declarar quando o índice está vazio ou defasado, em vez de devolver resultados silenciosamente errados | Must |
| RF-24 | A busca deve suportar filtros por pasta, tag e intervalo de datas | Should |
| RF-25 | O sistema deve ler uma nota inteira quando o trecho recuperado não for suficiente | Must |
| RF-26 | O sistema deve navegar por links entre notas (wikilinks) para expandir o contexto | Should |
| RF-27 | O sistema deve oferecer insights do vault (órfãs, duplicatas, sugestão de links, resumo) | Should |

### 5.4 Escrita no vault

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-30 | O sistema deve criar notas novas em Markdown, com frontmatter e no diretório indicado | Must |
| RF-31 | O sistema deve anexar conteúdo a uma nota existente (ex.: adicionar item ao diário ou a uma nota de projeto) | Must |
| RF-32 | O sistema deve editar uma nota existente preservando o restante do conteúdo | Should |
| RF-33 | Toda escrita deve ficar restrita ao diretório de um único vault: o nome informado ou, se o nome for omitido, o padrão | Must |
| RF-34 | Operações destrutivas (sobrescrever, remover) devem exigir `confirm=true` e ser sinalizadas como destrutivas no MCP | Must |
| RF-35 | O sistema deve manter um backup da versão anterior do arquivo antes de sobrescrever | Should |
| RF-36 | O sistema deve seguir convenções do vault (template, tags, formato de nome de arquivo) definidas na configuração | Could |

### 5.5 CLI de bootstrap

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-40 | A CLI deve gravar a configuração inicial (`nix init [--name NOME] [--vault PATH] [--embedding-model NOME] [--force]`) | Must |
| RF-41 | A CLI deve oferecer sincronização e status do índice (`nix sync`, `nix status`) | Must |
| RF-42 | A CLI deve diagnosticar ambiente, config e índice (`nix doctor`); `--json` emite o dump completo | Should |
| RF-43 | Sem subcomando, `nix` deve iniciar o servidor MCP stdio | Must |
| RF-44 | `nix sync` e `nix status` devem oferecer saída em JSON (`--json`) | Could |
| RF-45 | Um instalador (`install.bat` / `install.ps1` no Windows, `install.sh` no Unix) deve baixar os binários `nix` e `nix-hook` da plataforma, conferir o SHA-256 de cada um, gravar `NIX_HOME`, colocar `{NIX_HOME}/bin` no PATH do usuário e iniciar `nix init` se ainda não houver `settings.db`. Não exige Python na máquina | Must |
| RF-46 | Um desinstalador (`uninstall.bat` / `uninstall.ps1` no Windows, `uninstall.sh` no Unix) deve remover `NIX_HOME` e `{NIX_HOME}/bin` do PATH do usuário só se apontarem para esta instalação, apagar `nix` e `nix-hook`, `.nix/` e `settings.db` (e os arquivos `-wal`/`-shm`), e não tocar no vault. `--keep-data` preserva `settings.db` e `.nix/` | Must |

### 5.6 Interface MCP

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-50 | O sistema deve expor um servidor MCP **somente via stdio**, iniciado pelo cliente | Must |
| RF-51 | O servidor MCP deve expor 20 ferramentas de busca, leitura, escrita, tags, movimentação, insights, sincronização e cadastro (`search_notes`, `read_note`, `get_note_outline`, `read_note_lines`, `list_notes`, `list_all_tags`, `get_linked_notes`, `create_note`, `append_to_note`, `update_note`, `update_frontmatter`, `manage_tags`, `move_note`, `move_file`, `delete_note`, `sync_index`, `index_status`, `vault_insights`, `remember`, `list_vaults`) e, com `sessions.enabled` ligado, as 3 de sessão da seção 5.7 (23 no total) | Must |
| RF-52 | As ferramentas MCP devem ter descrições e esquemas claros o bastante para um cliente LLM usá-las corretamente sem instruções extras | Must |
| RF-53 | O servidor MCP deve respeitar as regras de segurança e de vetorização (incluindo `confirm=true` em operações destrutivas) | Must |
| RF-54 | O sistema deve documentar o trecho de configuração necessário para registrar o servidor no cliente MCP: `command` aponta para o binário na pasta da instalação (`NIX_HOME`). Windows: `${env:NIX_HOME}/bin/nix.exe` (ou o caminho absoluto). macOS/Linux: caminho absoluto `{NIX_HOME}/bin/nix` — não o nome `nix` no PATH | Must |
| RF-55 | stdout pertence ao protocolo: logs só em arquivo; bibliotecas não podem escrever no canal | Must |
| RF-56 | `get_note_outline` e `read_note_lines` devem ler a nota por heading ou por intervalo de linhas do arquivo (começando em 1, frontmatter incluído), com limite de 400 linhas e indicação de truncamento. Heading ausente orienta a usar `get_note_outline`. As linhas de `search_notes` usam o mesmo critério | Must |
| RF-57 | `update_frontmatter` deve alterar só as chaves de topo pedidas e preservar comentários, ordem e aspas do restante do YAML. O bloco resultante é validado antes de gravar; se for inválido, a nota não muda | Must |
| RF-58 | `manage_tags` deve adicionar e remover tags do frontmatter (lista ou string, sem `#`, sem duplicata, ordem preservada) sem mexer nas tags inline do corpo, e informar quais ficaram. `list_all_tags` lista as tags indexadas com contagem, para alimentar o filtro `tag` de `search_notes` e `list_notes` | Must |
| RF-59 | `move_note` (só `.md`) e `move_file` (recusa `.md`) devem mover dentro do vault. `move_note` reescreve por padrão os wikilinks e links Markdown que apontam para a nota, com backup de cada nota alterada. Links pelo título do frontmatter não mudam se o título não mudou. Notas fora de include/exclude não são alteradas e voltam como pendentes. Destino existente exige `overwrite=true` e `confirm=true`. `move_file` atualiza `![[alvo]]`, `[[alvo]]` e links Markdown relativos de PDF, imagem e outros anexos. O índice perde o id antigo e ganha o caminho novo; anexo só é reindexado com `index.index_attachments` | Must |
| RF-60 | `update_note` com `mode=prepend` deve inserir o texto depois do frontmatter, com o YAML original intacto, uma linha em branco e o corpo antigo, sem `confirm`. A ação é atualização. `mode=replace` continua destrutivo | Must |
| RF-61 | `nix config` deve listar, ler, gravar, remover e desfazer valores. A gravação de um ou mais campos valida o conjunto inteiro; se for inválido, nada daquela gravação entra no banco. Campo definido por variável de ambiente não é gravado por cima. `index.auto_sync_external_changes` não pode ser ligado | Must |
| RF-62 | `nix ui` deve abrir no navegador uma interface local de status, sincronização (com prévia e progresso), diagnóstico, vaults, configuração e histórico. Sem `nix init`, o comando não sobe. A interface escuta só em `127.0.0.1`, exige o link impresso pelo comando e encerra com Ctrl+C ou pelo botão Encerrar. Com sincronização em andamento, o botão Encerrar pede para esperar e o Ctrl+C só fecha o índice depois que a thread termina. A sincronização pode valer para o vault escolhido ou para todos. Os controles dessa tela seguem o RF-71 | Must |
| RF-63 | Um servidor MCP já em execução deve passar a usar a configuração nova na chamada seguinte. Modelo de embedding e pasta do índice continuam os anteriores até o cliente reiniciar. Troca de modelo exige `nix sync --full` | Must |
| RF-64 | A interface local deve consultar os vaults só para leitura, pelas mesmas ferramentas do MCP. A busca aceita um vault, vários ou todos e mostra o vault de cada trecho. As demais consultas usam o vault escolhido na página (o padrão, se nenhum for escolhido): lista de notas com filtro por pasta ou tag, contorno, linhas e links de uma nota, tags com contagem e insights (resumo, órfãs, títulos duplicados e sugestões de link). Enquanto o vault consultado sincroniza, a consulta pede para esperar; outro vault continua legível | Should |
| RF-65 | A interface deve gerar a configuração MCP de Cursor, Claude Code, VS Code, do Devin CLI local e do Devin Desktop, com o caminho real do executável, e listar as ferramentas expostas, marcadas como leitura, escrita ou destrutiva. O Devin na nuvem não alcança o Nix desta máquina | Should |
| RF-66 | O servidor MCP deve gravar cada chamada de ferramenta (quando, cliente, ferramenta, duração e situação) em `.nix/traffic.db`, mantendo as 5.000 mais recentes. Argumentos só entram com `logging.log_prompts`; o conteúdo das notas nunca entra. Falha ao gravar não derruba a chamada. A interface mostra esse registro com filtros por ferramenta e situação | Should |
| RF-67 | A interface deve listar os backups de `safety.backup_dir`, comparar cada um com a nota atual, permitir baixá-lo e restaurá-lo. Restaurar exige confirmação, vale só para `.md`, grava backup do estado atual antes e reindexa a nota pelo write-through | Should |
| RF-68 | O sistema deve cadastrar de 1 a 5 vaults nomeados, com exatamente um padrão. O `nix init` cria o primeiro com o nome `Default` (ou `--name`). O nome tem de 1 a 32 caracteres, começa com letra ou dígito e segue com letras, dígitos, `_` ou `-`. Um nome no formato de carimbo de backup (`AAAAMMDDTHHMMSS`) é recusado. A comparação ignora maiúsculas e a grafia original é preservada. Os caminhos não podem coincidir nem um ficar dentro do outro. Omitir o vault numa ferramenta usa o padrão. Remover o padrão é recusado até outro ser escolhido; remover o único vault também é recusado. Renomear troca o cadastro e não move o índice nem os backups. Inclusão, exclusão, pastas padrão e a pasta do vault mudam com `nix vault set` e `nix vault path`. Renomear, remover, trocar a pasta ou gravar um ajuste enquanto aquele vault sincroniza é recusado até o término | Must |
| RF-69 | A busca e as operações que aceitam vários vaults (`search_notes`, `list_notes`, `list_all_tags`, `index_status`, `sync_index`) devem consultar um nome, uma lista de nomes ou todos os vaults quando o valor é `"*"` | Must |
| RF-70 | Toda escrita deve ocorrer num único vault. Lista de nomes ou `"*"` é recusado, com mensagem que pede um nome só ou o padrão | Must |
| RF-71 | Na interface, os controles de sincronização ficam desligados desde o início do job até o fim, também quando a página de sincronizar é recarregada no meio. Há no máximo um job por processo. Um segundo pedido pede para esperar, sem substituir o progresso. A prévia, com job ativo, pede para esperar e não varre o vault | Must |

### 5.7 Sessões dos agentes

Guarda as sessões feitas com Claude Code, Cursor, Copilot, Devin CLI e Devin Desktop para que, quando a cota de uma assinatura acabar, outro agente continue de onde o anterior parou. Tudo local, sem LLM e sem servidor HTTP. É opcional e por projeto (RN-07).

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-80 | A sessão é identificada por agente, id do agente e projeto (raiz Git da pasta de trabalho, ou a própria pasta) | Must |
| RF-81 | Os eventos (`session-start`, `user-prompt`, `post-tool`, `compact`, `stop`, `session-end`) ficam em `{app_root}/.nix/sessions.db`, fora do vault, sem duplicar o mesmo evento recebido duas vezes | Must |
| RF-83 | Antes de gravar, um sanitizador remove chaves, tokens, senhas, `Authorization` e conteúdo de `.env`; pedidos têm até 16 KiB e trechos de ferramenta até 2 KB, com corte respeitando UTF-8. Raciocínio oculto, prompts de sistema e binários não entram | Must |
| RF-86 | Os eventos não expiram por padrão; `sessions.retention_days > 0` apaga os de sessões encerradas e mantém a nota | Should |
| RF-100 | Cada sessão vira uma nota Markdown em `{sessions.folder}/<projeto>/<data>-<agente>-<id curto>.md`, com frontmatter, o handoff no topo e um turno por seção `##`, gravada pelo `writer` com backup e write-through. A nota tem tamanho máximo (`sessions.max_note_bytes`) | Must |
| RF-104 | Os filtros do vault valem para a pasta de sessões: se ela estiver excluída, a nota não é gravada e a mensagem diz como corrigir | Must |
| RF-106 | As sessões não formam um vault: são notas dentro de `sessions.vault` (padrão: o vault padrão) e entram no índice dele. Recomenda-se um vault só de sessões | Should |
| RF-107 | Com `sessions.search_default = excluir` (padrão), `search_notes` sem filtro de pasta ignora a pasta de sessões; com filtro explícito nela, ou com `incluir`, as sessões entram | Must |
| RF-108 | Status e `vault_insights` tratam as sessões à parte: elas não entram em "notas indexadas" nem geram órfãs | Should |
| RF-110 | O handoff reúne o primeiro e o último pedido, os 5 últimos, os arquivos alterados, o último erro e o que ficou aberto, em até 6.000 caracteres e terminando no caminho da nota. Há no máximo um pendente por projeto, entregue uma única vez | Must |
| RF-112 | O handoff é criado no `session-end`, no `session_handoff` e por `nix session handoff --create`; é entregue na saída do hook de início de sessão ou em `session_handoff` | Must |
| RF-120 | `nix hooks install` roda no repositório, mostra os arquivos que vai criar ou alterar e só escreve depois de confirmar (ou com `--yes`); nenhum agente vem marcado. `remove` apaga só o que a Nix marcou e `status` mostra o que está ativo. Os hooks ficam no projeto, nunca na pasta da conta, com backup antes de alterar arquivo existente | Must |
| RF-127 | `nix skills install` roda no repositório, mostra as pastas que vai criar ou alterar e só escreve depois de confirmar (ou com `--yes`); nenhum agente vem marcado. Copia as skills do pacote (`sessoes-nix`) para a pasta do agente: Claude em `.claude/skills/`, Cursor e Copilot em `.agents/skills/`, Devin CLI e Devin Desktop em `.devin/skills/`. `remove` apaga só as pastas com a marca da Nix, `status` mostra o que está ativo, e uma pasta já existente sem essa marca não é sobrescrita. Uma pasta marcada com o texto da skill incompleto fica desatualizada e o `install` seguinte a completa. As skills de desenvolvimento não entram nesse comando | Must |
| RF-130 | `nix hook` usa um ponto de entrada mínimo (sem CLI nem Pydantic), termina sempre com código 0 e em menos de 300 ms com o cache do binário aquecido; só o início da sessão escreve no stdout (o handoff, no formato do agente). Evento de projeto sem hooks instalados é descartado | Must |
| RF-136 | No `session-end`, um processo destacado grava a nota sem o hook esperar; um único consolidador roda por vez e processa a fila inteira | Must |
| RF-140 | A interface tem a tela Sessões (lista por projeto e agente, nota, handoff pendente com cancelamento) e, na tela Conectar clientes, o Devin Desktop e o arquivo de hook de cada agente, sem oferecer skill | Should |
| RF-150 | Cada chunk guarda o hash do texto vetorizado; ao reindexar um arquivo alterado, o vetor de chunk com o mesmo hash é reaproveitado e só os novos passam pelo embedding. O resultado do sync informa os chunks reaproveitados | Must |

Ferramentas: `session_handoff` (escrita, entrega o handoff pendente), `list_sessions` e `read_session` (leitura), expostas com `sessions.enabled`. A skill `sessoes-nix` vem no pacote, orienta o agente a chamá-las e entra no projeto com `nix skills install`.

## 6. Histórias de usuário

Os critérios de aceite de cada história ficam em [`bdd/`](./bdd), em Gherkin, com o mesmo ID (`@HU-01`, `@HU-01.1`…). O [BDD.md](./BDD.md) é o índice.

**HU-01 — Primeira configuração**
> Como usuário, quero apontar o caminho do meu vault e indexá-lo, para o editor passar a consultá-lo.

**HU-02 — Indexar um vault existente**
> Como usuário com um vault de anos, quero indexar tudo de uma vez, para poder consultar meu histórico.

**HU-03 — Sincronizar mudanças feitas no Obsidian**
> Como usuário, depois de escrever direto no Obsidian, quero atualizar o índice quando eu decidir.

**HU-04 — Instalar o ambiente**
> Como usuário, quero um único arquivo para copiar, sem instalar Python, e que a configuração do vault comece em seguida.

**HU-07 — Desinstalar o ambiente**
> Como usuário, quero um único executável que desfaça a instalação sem apagar o vault.

**HU-05 — Registrar conhecimento pelo editor**
> Como usuário, quero pedir ao agente do editor que crie uma nota, e que ela já fique pesquisável.

**HU-06 — Usar o Nix dentro do Cursor (ou equivalente)**
> Como usuário, quero acessar meu vault de dentro do editor.

**HU-08 — Configurar e operar pela interface**
> Como usuário, quero ver o índice, sincronizar e ajustar a configuração sem editar arquivo à mão.

**HU-09 — Ferramenta sem vault**
> Como usuário, quero que o agente use o vault padrão quando a chamada não disser qual.

**HU-10 — Vault inexistente**
> Como usuário, quero um erro que mostre os vaults que existem quando o nome estiver errado.

**HU-11 — Escrita recebendo lista**
> Como usuário, quero que uma escrita não se espalhe por vários vaults numa chamada só.

**HU-12 — Busca em todos**
> Como usuário, quero uma busca que olhe todos os vaults de uma vez.

**HU-13 — Remover o padrão**
> Como usuário, quero que sempre exista um vault padrão.

**HU-14 — Botões desligados durante o sync**
> Como usuário, quero que a sincronização da interface não seja disparada de novo enquanto a anterior não termina.

## 7. Requisitos não funcionais

| ID | Categoria | Requisito |
| --- | --- | --- |
| RNF-01 | Custo | Embeddings e banco vetorial devem ser locais, gratuitos e sem limite de uso. Nenhuma chamada remota. |
| RNF-02 | Privacidade | O conteúdo do vault não sai da máquina por iniciativa do Nix. O cliente MCP é quem decide o que enviar ao LLM. |
| RNF-03 | Desempenho | Recuperação (busca híbrida) em menos de 500ms em vault de até 5.000 notas. |
| RNF-04 | Desempenho | Sincronização inicial de 1.000 notas em até ~5 minutos em hardware de desenvolvedor típico, sem GPU. |
| RNF-05 | Portabilidade | O binário publicado funciona em Windows amd64, Linux amd64/arm64 e macOS Apple Silicon, sem Python instalado. O desenvolvimento do código usa Python 3.11+ (incluindo 3.14). |
| RNF-06 | Segurança | Todas as operações de arquivo devem ser confinadas ao vault. |
| RNF-07 | Confiabilidade | Interrupção durante a sincronização não deve corromper o índice; a operação seguinte deve retomar de onde parou. |
| RNF-08 | Observabilidade | Logs estruturados em arquivo, com nível configurável. No stdio, nada em stdout além do protocolo. |
| RNF-09 | Usabilidade | Toda mensagem de erro deve indicar a ação corretiva. |
| RNF-10 | Manutenibilidade | Núcleo independente de interface; CLI, MCP e a interface local são adaptadores finos sobre o mesmo core. |

## 8. Regras de negócio

- **RN-01 — Consentimento de indexação.** O Nix nunca varre nem vetoriza o vault por iniciativa própria. Não há watcher de arquivos nem indexação em background na v1. A indexação ocorre só por `nix sync` ou pela ferramenta `sync_index`.
- **RN-02 — Coerência write-through.** Toda escrita originada nas ferramentas tenta atualizar o índice na mesma operação. Se a vetorização falhar, o arquivo no vault é preservado (fonte da verdade), o arquivo é marcado com `status = error` e o usuário é instruído a rodar `nix sync` ou `sync_index`.
- **RN-03 — Confinamento ao vault.** Nenhuma leitura ou escrita ocorre fora do diretório do vault da operação, incluindo tentativas via caminho relativo ou link simbólico.
- **RN-04 — Proveniência da fonte.** Toda resposta de ferramenta que devolve conteúdo do vault inclui caminho relativo e o trecho (ou o corpo da nota). A fidelidade da resposta em linguagem natural é responsabilidade do cliente LLM.
- **RN-05 — Não destruição silenciosa.** Sobrescrita e remoção exigem confirmação e geram backup.
- **RN-06 — Respeito aos filtros.** Notas excluídas pela configuração não são indexadas, lidas nem citadas.
- **RN-07 — Consentimento de sessões.** Capturar sessões exige `nix hooks install` naquele projeto e naqueles agentes. Sem isso, o banco não recebe eventos.
- **RN-08 — Uma entrega por handoff.** Dois agentes não recebem o mesmo handoff pendente.
- **RN-09 — Evidência, não ordem.** O conteúdo de uma sessão antiga é histórico: ferramentas antigas ficam marcadas como já executadas e o texto nunca é tratado como instrução.

## 9. Métricas de sucesso

| Métrica | Alvo v1 |
| --- | --- |
| Acurácia de recuperação (a nota certa está no top-5) | ≥ 90% em conjunto de avaliação de 30 perguntas |
| Respostas de ferramenta com caminho da fonte | 100% das buscas e leituras |
| Tempo de busca híbrida | ≤ 500ms (p50) |
| Falhas de sincronização por arquivo | ≤ 1% dos arquivos |
| Uso pessoal | Uso em ≥ 4 dias por semana após 1 mês |

## 10. Roadmap

**Entregue**

- Configuração em `settings.db` na pasta do aplicativo (ambiente ganha do banco; índice em `.nix/data`), sync incremental e `--full`, indexação de Markdown e PDFs referenciados, busca híbrida (densa + FTS5 + RRF).
- Servidor MCP stdio com 20 ferramentas de vault (leitura parcial, frontmatter preservando o YAML, tags, movimentação com links e prepend, `list_vaults`) e, com `sessions.enabled`, as 3 de sessão, recursos `nix://note/{+rel_path}` (vault padrão) e `nix://vault/{name}/note/{+rel_path}`, logs de tráfego em arquivo e em `.nix/traffic.db`.
- CLI de bootstrap: `init [--name] [--vault] [--embedding-model] [--force]` (o primeiro vault chama-se `Default` se `--name` for omitido), `vault` (listar, cadastrar, renomear, remover, padrão, pasta e ajustes), `sync` e `status` com `--vault` repetível e `--all`, `doctor` (com `--json` em `sync`/`status`/`doctor`); `nix` sem argumentos inicia o servidor. Uma configuração anterior, de um vault só, vira o `Default` e conserva o índice e os backups já gravados.
- Vários vaults nomeados (de 1 a 5, exatamente um padrão) no mesmo processo. Ferramenta sem `vault` usa o padrão. Busca em um, em vários ou em todos. Escrita num único vault.
- Instalador `install.bat` / `install.ps1` / `install.sh` (`nix` e `nix-hook` da release, SHA-256, `NIX_HOME`/`nix` no PATH, `nix init`).
- Desinstalador `uninstall.bat` / `uninstall.ps1` / `uninstall.sh` (remove PATH/`NIX_HOME`, `nix` e `nix-hook`, `.nix/` e `settings.db`; não toca no vault).
- CLI `nix config` (listar, gravar, remover, histórico e desfazer) e interface local `nix ui` (status, sincronização com progresso e controles desligados até o fim do job, diagnóstico, busca em um ou mais vaults, notas, tags, insights, conexão de clientes, tráfego MCP, backups com restauração, tela Vaults, configuração e histórico).
- Servidor MCP recarrega a configuração entre chamadas; modelo de embedding e pasta do índice pedem reinício do cliente.
- Registro MCP: `command` aponta para o binário em `NIX_HOME` (Windows: `${env:NIX_HOME}/bin/nix.exe` ou caminho absoluto; macOS/Linux: `{NIX_HOME}/bin/nix` absoluto). A interface gera o trecho de Cursor, Claude Code, VS Code, Devin CLI e Devin Desktop.
- Escrita com write-through, confirmação e backup.
- Sessões dos agentes: `sessions.db`, hooks por projeto para Claude Code, Cursor, Copilot, Devin CLI e Devin Desktop (`nix hooks install/remove/status`), a skill `sessoes-nix` instalada no projeto com `nix skills install/remove/status`, nota no vault, handoff, as ferramentas `list_sessions`, `read_session` e `session_handoff`, a tela Sessões e o reaproveitamento de vetores por hash de chunk.
- Filtros pasta/tag/data e wikilinks.
- Memória de longo prazo (`remember` → `vault.longterm_folder`), insights (órfãs, duplicatas, links, resumo).
- Erros de domínio (`NixError`) na CLI e no MCP vão para stderr, sem traceback.
- Seções globais graváveis: `index`, `retrieval`, `safety` e `logging`. O cadastro dos vaults fica à parte (`nix vault`). Um campo global definido por `NIX_SECAO__CAMPO` ganha do banco.

**Próximo**

- Conjunto de avaliação `eval/` (harness e 30 perguntas; ainda não está no repositório).

## 11. Riscos

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Qualidade de recuperação baixa em vault heterogêneo | Alto | Chunking consciente da estrutura Markdown, busca híbrida, conjunto de avaliação |
| Índice desatualizado gera trechos errados (consequência da indexação manual) | Alto | Aviso de defasagem em `index_status`, comando `nix status`, sincronização rápida |
| Modelo de embedding local lento sem GPU | Médio | Modelo pequeno e quantizado por padrão, processamento em lote, opção de trocar de modelo |
| Perda de dados em escrita | Alto | Confinamento ao vault, confirmação, backup antes de sobrescrever, escrita atômica |
| Troca de modelo de embedding invalida o índice | Médio | Registro do modelo usado no índice e detecção de incompatibilidade com pedido de reindexação |
| Bibliotecas escrevem em stdout e corrompem o stdio | Alto | Silenciamento na inicialização; logs só em arquivo |

## 12. Fora de escopo

Interface de edição de notas ou plugin do Obsidian; LLM/chat/agente próprio; CLI de consulta (`ask`/`chat`); transporte MCP HTTP; multiusuário; hospedagem em nuvem; edição de anexos binários; geração automática de notas sem pedido do usuário (exceto a nota de sessão, que depende de `nix hooks install`, RN-07); leitura dos arquivos de sessão dos agentes; banco vetorial separado para sessões; Devin na nuvem; sincronização de arquivos entre dispositivos.

## 13. Glossário

- **Vault** — diretório do Obsidian contendo as notas em Markdown. O Nix guarda de 1 a 5, cada um com nome. O padrão é o usado quando o nome é omitido.
- **Chunk** — trecho de uma nota, unidade indexada e recuperada.
- **Embedding** — representação vetorial de um chunk, usada para busca por similaridade.
- **MCP** — Model Context Protocol. O Nix expõe ferramentas exclusivamente via stdio.
- **Write-through** — política em que uma escrita atualiza dado e índice na mesma operação.
- **Sessão** — conversa de um agente com o projeto, gravada pelos hooks em `sessions.db` e resumida numa nota do vault.
- **Handoff** — resumo montado por regras (sem LLM) do ponto em que uma sessão parou, entregue uma única vez a outro agente.
- **Hook de sessão** — comando que o agente chama a cada evento (`nix-hook` no binário publicado, `nix hook` no checkout), instalado por projeto com `nix hooks install`.
- **Skill da Nix** — `SKILL.md` que vem no pacote e o `nix skills install` copia para a pasta de skills do agente, no projeto. O arquivo `.nix-skill` marca essas pastas para o `remove` não apagar as skills de desenvolvimento.
- **Wikilink** — referência entre notas no formato `[[Nome da Nota]]`.
- **Instalador** — `install.bat` / `install.ps1` / `install.sh`: baixa `nix` e `nix-hook`, confere o SHA-256, grava `NIX_HOME` e dispara `nix init`.
- **Desinstalador** — `uninstall.bat` / `uninstall.ps1` / `uninstall.sh`: remove `NIX_HOME` e o `nix` do PATH, apaga `nix` e `nix-hook`, `.nix/` e `settings.db`; não altera o vault.
