# PRD — Nix, Servidor MCP de Conhecimento

| Campo | Valor |
| --- | --- |
| Produto | **Nix** (nome inspirado na Lulu, cachorra do autor) |
| Tipo | Servidor MCP que expõe wikis em Markdown a agentes de desenvolvimento |
| Interfaces | MCP stdio (único transporte do protocolo); CLI (`init`, `wiki`, `config`, `sync`, `status`, `doctor`, `ui`, `brain`, `run`); interface local só enquanto `nix ui` está aberto; instalador `install.bat` / `install.sh` (`nix` e `nix-hook` em `NIX_HOME`, `nix` no PATH, sem Python); desinstalador `uninstall.bat` / `uninstall.sh` |
| Status | Implementado — v5.1.0 |
| Autor | Paulo |
| Data | 2026-11-02 |

Especificações técnicas: [TDD.md](./TDD.md). Critérios de aceite: [BDD.md](./BDD.md).

---

## 1. Visão

Nix é a ponte entre bases de conhecimento em Markdown e agentes de desenvolvimento como Cursor, VS Code, Claude Code e Codex. Em vez de o usuário lembrar onde cada anotação foi salva, o agente do editor chama ferramentas do Nix para buscar, ler, criar e atualizar notas — com o índice local sempre alinhado às escritas do próprio Nix.

O Mega Brain, desligado por padrão, guarda a memória de trabalho entre agentes: páginas de sessão, perfil, mensagens e handoff. A wiki das páginas é escolhida com `nix brain enable --wiki NOME`.

Tudo roda na máquina do usuário. Embeddings e banco vetorial são locais e gratuitos. Não há LLM no Nix: o raciocínio fica no cliente MCP. Não há processo residente nem servidor de time.

## 2. Problema

Pastas de notas crescem rápido e viram um arquivo morto. Hoje o usuário enfrenta:

- **Busca literal insuficiente.** Uma busca literal encontra palavras, não ideias. Quem não lembra o termo exato usado não acha a nota.
- **Conhecimento fragmentado.** A resposta para uma pergunta costuma estar espalhada em várias notas, e sintetizar isso manualmente é caro.
- **Captura com atrito.** Registrar uma nota nova no formato certo, com os links e tags corretos, exige abrir as notas e lembrar das convenções.
- **Agentes de desenvolvimento não conhecem o vault.** Cursor, VS Code, Claude Code e Codex não têm, por padrão, busca semântica nem escrita segura nas anotações pessoais.

## 3. Objetivos

| # | Objetivo | Como será medido |
| --- | --- | --- |
| O1 | Entregar trechos relevantes do vault ao cliente MCP, com caminho e citação da nota | ≥ 90% das buscas trazem a nota certa no top-5 em um conjunto de 30 perguntas de avaliação |
| O2 | Dar ao usuário controle explícito sobre quando a base é vetorizada | Nenhuma vetorização de arquivos externos ocorre sem `nix sync` ou `sync_index` |
| O3 | Manter o índice consistente após edições feitas pelas ferramentas | 100% das escritas via MCP refletidas no índice ao final da operação |
| O4 | Custo zero e privacidade | Embeddings e banco vetorial 100% locais e gratuitos; nenhuma chamada remota |
| O5 | Encaixar no fluxo do editor | Registrável como servidor MCP stdio em Cursor, VS Code, Claude Code e Codex |

### Não-objetivos

- A interface local cobre configuração, operação e consulta (status, sincronização, diagnóstico, busca, notas, tags, insights, conexão de clientes, tráfego MCP, backups e histórico), não a edição das notas. A única escrita no vault pela interface é restaurar um backup, com confirmação explícita.
- Não haverá LLM, chat, RAG conversacional nem orquestração de agente no Nix.
- O MCP não tem transporte HTTP. Não haverá servidor multiusuário, autenticação de contas nem hospedagem em nuvem. A interface local escuta só em `127.0.0.1` enquanto `nix ui` está aberto.
- Não haverá sincronização de vault entre máquinas (isso depende de um mecanismo externo de sincronização).
- Não há edição de anexos binários (PDFs, imagens) — apenas extração de texto de PDFs referenciados pelas notas, se `index.index_attachments` estiver ativo.
- Não haverá fine-tuning de modelos.

## 4. Persona e contexto de uso

**Paulo — desenvolvedor, usuário de notas em Markdown.** Mantém um vault com notas técnicas, de projetos, de leituras e diário. É confortável com terminal e com arquivos de configuração. Usa Cursor no dia a dia e quer o vault disponível dentro do editor via MCP. Valoriza controle: não quer que um processo em background fique lendo e reprocessando o vault sem sua autorização.

**Momentos de uso principais:**

1. Durante o trabalho, no Cursor / Claude Code / Copilot, perguntando algo que sabe ter anotado antes.
2. Ao final de uma leitura ou reunião, pedindo ao agente do editor que registre uma nota nova no vault.
3. Depois de uma sessão de escrita direta nos arquivos, rodando `nix sync` (ou pedindo `sync_index`).

## 5. Escopo funcional

### 5.1 Configuração

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-01 | O sistema deve guardar a configuração num SQLite na pasta da instalação (`settings.db`), com as wikis nomeadas (de 1 a 100, exatamente um padrão) e os demais parâmetros | Must |
| RF-02 | O sistema deve oferecer um comando de inicialização que grava a primeira wiki (nome `Default`, ou `--name`), o caminho (`--wiki` ou pergunta) e o modelo de embedding (`--embedding-model` ou pergunta) no `settings.db`, e marca a instalação como configurada. Se a configuração já existir, sem `--force` só atualiza o caminho da wiki padrão, salvo `--embedding-model`. `--name` com wikis já cadastradas é recusado e pede `nix wiki add`. Uma configuração anterior, com um único caminho, passa a ser a wiki `Default` e continua usando o índice e os backups já gravados. `--force` recria a configuração do zero, sem alterar as notas. A tela Wikis da interface também cadastra a pasta (a primeira vira o padrão), mas não grava essa marca: `nix ui` e o servidor MCP continuam exigindo o `nix init` | Must |
| RF-03 | O sistema deve permitir sobrescrever a configuração global (`index`, `retrieval`, `safety`, `logging`, `brain`, `profile`) por variável de ambiente, e essa variável deve ganhar do valor gravado. O cadastro das wikis não entra nessa precedência (`NIX_VAULT__*` e `NIX_WIKI__*` são ignorados) | Must |
| RF-04 | O sistema deve validar a configuração antes de gravar e apresentar mensagens de erro acionáveis (wiki inexistente, modelo inválido, campo desconhecido) | Must |
| RF-05 | O sistema deve permitir configurar, por wiki, padrões de inclusão/exclusão de arquivos e pastas (ex.: ignorar `Templates/`, `.trash/`, notas privadas), com `nix wiki set NOME include\|exclude VALOR` | Should |
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
| RF-16 | `index_status` deve informar quando o índice estiver desatualizado em relação ao vault, sugerindo sincronizar — sem sincronizar por conta própria. Uma nota gravada pelo Nix, com a mesma data e o mesmo tamanho da linha indexada, não conta como desatualizada | Should |
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
| RF-33 | Toda escrita deve ficar restrita ao diretório de uma única wiki: o nome informado ou, se o nome for omitido, o padrão | Must |
| RF-34 | Operações destrutivas (sobrescrever, remover) devem exigir `confirm=true` e ser sinalizadas como destrutivas no MCP | Must |
| RF-35 | O sistema deve manter um backup da versão anterior do arquivo antes de sobrescrever | Should |
| RF-36 | O sistema deve seguir convenções do vault (template, tags, formato de nome de arquivo) definidas na configuração | Could |

### 5.5 CLI de bootstrap

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-40 | A CLI deve gravar a configuração inicial (`nix init [--name NOME] [--wiki PATH] [--embedding-model NOME] [--force]`) | Must |
| RF-41 | A CLI deve oferecer sincronização e status do índice (`nix sync`, `nix status`) | Must |
| RF-42 | A CLI deve diagnosticar ambiente, config e índice (`nix doctor`); `--json` emite o dump completo | Should |
| RF-43 | No terminal, `nix` sem subcomando abre a interface, mesmo antes do `nix init`. Sem terminal, inicia o servidor MCP stdio, que exige o `nix init` | Must |
| RF-44 | `nix sync` e `nix status` devem oferecer saída em JSON (`--json`) | Could |
| RF-45 | Um instalador (`install.bat` / `install.ps1` no Windows, `install.sh` no Unix) deve baixar os binários `nix` e `nix-hook` da plataforma, conferir o SHA-256 de cada um, gravar `NIX_HOME` e colocar `{NIX_HOME}/bin` no PATH do usuário. Não roda `nix init`: pede para executar `nix` e, se o comando não funcionar, fechar e abrir o terminal. Não exige Python na máquina | Must |
| RF-46 | Um desinstalador (`uninstall.bat` / `uninstall.ps1` no Windows, `uninstall.sh` no Unix) deve remover `NIX_HOME` e `{NIX_HOME}/bin` do PATH do usuário só se apontarem para esta instalação, apagar `nix` e `nix-hook`, `.nix/` e `settings.db` (e os arquivos `-wal`/`-shm`), apagar o cache de extração (`onefile-*` e `hook-*`) e a pasta da instalação se ela ficar vazia, e não tocar no vault. `--keep-data` preserva `settings.db` e `.nix/` e ainda apaga o cache de extração. No Windows, se `nix.exe` ou `nix-hook.exe` estiver em uso, o desinstalador encerra antes de alterar o PATH e pede para fechar o cliente e rodar de novo | Must |

### 5.6 Interface MCP

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-50 | O sistema deve expor um servidor MCP **somente via stdio**, iniciado pelo cliente | Must |
| RF-51 | O servidor MCP deve expor 20 ferramentas de busca, leitura, escrita, tags, movimentação, insights, sincronização e cadastro (`search_notes`, `read_note`, `get_note_outline`, `read_note_lines`, `list_notes`, `list_all_tags`, `get_linked_notes`, `create_note`, `append_to_note`, `update_note`, `update_frontmatter`, `manage_tags`, `move_note`, `move_file`, `delete_note`, `sync_index`, `index_status`, `wiki_insights`, `remember`, `list_wikis`). Com o Mega Brain ligado, entram as 18 ferramentas `brain_*` da seção 5.7 (38 no total) | Must |
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
| RF-62 | `nix ui` deve abrir no navegador uma interface local de status, sincronização (com prévia e progresso), diagnóstico, wikis, Mega Brain, configuração e histórico. Sem `nix init`, o comando não sobe. `nix` no terminal abre a mesma interface mesmo antes dessa marca. A interface escuta só em `127.0.0.1`, exige o link impresso pelo comando e encerra com Ctrl+C ou pelo botão Encerrar. Com sincronização em andamento, o botão Encerrar pede para esperar e o Ctrl+C só fecha o índice depois que a thread termina. A sincronização pode valer para a wiki escolhida ou para todas. Os controles dessa tela seguem o RF-71. No Status, o bloco Para começar fica visível enquanto a wiki selecionada ainda não foi sincronizada ou o editor ainda não chamou uma ferramenta. A faixa de índice desatualizado só aparece depois da primeira sincronização | Must |
| RF-63 | Um servidor MCP já em execução deve passar a usar a configuração nova na chamada seguinte. Modelo de embedding e pasta do índice continuam os anteriores até o cliente reiniciar. Troca de modelo exige `nix sync --full` | Must |
| RF-64 | A interface local deve consultar as wikis só para leitura, pelas mesmas ferramentas do MCP. A busca aceita uma wiki, várias ou todas e mostra a wiki de cada trecho. As demais consultas usam a wiki escolhida na página (o padrão, se nenhuma for escolhida; o seletor é `?wiki=`): lista de notas com filtro por pasta ou tag, contorno, linhas e links de uma nota, tags com contagem e insights (resumo, órfãs, títulos duplicados e sugestões de link). A página de insights explica o que é cada um desses quatro tipos. Enquanto a wiki consultada sincroniza, a consulta pede para esperar; outra wiki continua legível | Should |
| RF-65 | A interface deve gerar a configuração MCP de Cursor, VS Code, Claude Code e Codex, com o caminho real do executável, e listar as ferramentas expostas, marcadas como leitura, escrita ou destrutiva | Should |
| RF-66 | O servidor MCP deve gravar cada chamada de ferramenta (quando, cliente, ferramenta, duração e situação) em `.nix/traffic.db`, mantendo as 5.000 mais recentes. Argumentos só entram com `logging.log_prompts`; o conteúdo das notas nunca entra. Falha ao gravar não derruba a chamada. A interface mostra esse registro com filtros por ferramenta e situação | Should |
| RF-67 | A interface deve listar os backups de `safety.backup_dir`, comparar cada um com a nota atual, permitir baixá-lo e restaurá-lo. Restaurar exige confirmação, vale só para `.md`, grava backup do estado atual antes e reindexa a nota pelo write-through | Should |
| RF-68 | O sistema deve cadastrar de 1 a 100 wikis nomeadas, com exatamente um padrão. O `nix init` cria a primeira com o nome `Default` (ou `--name`). A tela Wikis também cadastra; a primeira vira o padrão. O nome tem de 1 a 32 caracteres, começa com letra ou dígito e segue com letras, dígitos, `_` ou `-`. Um nome no formato de carimbo de backup (`AAAAMMDDTHHMMSS`) é recusado. A comparação ignora maiúsculas e a grafia original é preservada. Os caminhos não podem coincidir nem um ficar dentro do outro. Omitir a wiki numa ferramenta usa o padrão. Remover o padrão é recusado até outro ser escolhido; remover a única wiki também é recusado. Renomear troca o cadastro e não move o índice nem os backups. Inclusão, exclusão, pastas padrão e a pasta da wiki mudam com `nix wiki set` e `nix wiki path`. Renomear, remover, trocar a pasta ou gravar um ajuste enquanto aquela wiki sincroniza é recusado até o término | Must |
| RF-69 | A busca e as operações que aceitam várias wikis (`search_notes`, `list_notes`, `list_all_tags`, `index_status`, `sync_index`) devem consultar um nome, uma lista de nomes ou todas as wikis quando o valor é `"*"`. O parâmetro é `wiki` | Must |
| RF-70 | Toda escrita deve ocorrer numa única wiki. Lista de nomes ou `"*"` é recusado, com mensagem que pede um nome só ou o padrão | Must |
| RF-71 | Na interface, os controles de sincronização ficam desligados desde o início do job até o fim, também quando a página de sincronizar é recarregada no meio. Há no máximo um job por processo. Um segundo pedido pede para esperar, sem substituir o progresso. A prévia, com job ativo, pede para esperar e não varre o vault | Must |

### 5.7 Mega Brain

Memória local entre agentes, desligada por padrão. `nix brain enable --wiki NOME` escolhe a wiki das páginas. Essa wiki conta no limite de 100 e não pode ser apagada enquanto o Mega Brain estiver ligado. Não há LLM, processo residente nem servidor de time. O `sessions.db` antigo não é migrado.

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-80 | O projeto é a raiz Git da pasta de trabalho, ou a própria pasta. O `.nix.toml` pode definir o nome, `[capture] enabled/exclude` e `[profile] contribute/consume`. Toml ilegível desliga a captura | Must |
| RF-81 | Os eventos ficam em `{app_root}/.nix/brain.db`. A captura só ocorre com o Mega Brain ligado e com hook global daquele agente ou hook do projeto, e com a captura do projeto ligada. Caminhos excluídos saem evento a evento | Must |
| RF-83 | Antes de gravar, um sanitizador remove chaves, tokens, senhas, `Authorization` e conteúdo de `.env`. Raciocínio oculto, prompts de sistema e binários não entram | Must |
| RF-100 | A página da sessão fica em `projects/<projeto>/sessions/<AAAA-MM-DD>-<agente>-<id curto>.md`, montada por regras (primeiro e último pedido, os cinco últimos, arquivos alterados, último erro, o que ficou aberto, tokens) e gravada pelo writer da wiki, com backup e write-through | Must |
| RF-110 | Há no máximo um handoff aberto por projeto. `accept` reivindica uma única vez. Mostrar o handoff no briefing não o consome | Must |
| RF-120 | `nix brain hooks install --scope global\|project` não marca nenhum agente. Há prévia, confirmação e backup antes de alterar arquivo existente. O escopo global avisa sobre privacidade. Agente cujo formato de hook não foi confirmado fica como captura parcial, sem arquivo inventado | Must |
| RF-130 | O subcomando do `nix-hook` é `brain`. O subcomando antigo `hook` termina em silêncio com código 0. O hook devolve sempre 0. O início da sessão escreve o briefing no formato do agente | Must |
| RF-136 | No `session-end`, um processo destacado grava a página. `brain.idle_end_after_hours` vale 0 por padrão e não encerra sessão sozinho | Must |
| RF-140 | A interface tem o grupo Mega Brain: Painel (cartões e filtro pelo nome), Caixa de entrada e Perfil. O projeto tem as abas Visão geral, Agentes, Tokens, Sessões e Conhecimento, e a URL guarda a aba. Os links de perfil e das páginas de sessão abrem a wiki configurada no Mega Brain, não a wiki selecionada na interface | Must |
| RF-160 | O perfil não usa LLM. Listas de palavras em inglês e português, `profile.min_projects` padrão 2, a frase mais nova prevalece, a evidência fica guardada e `forget` vira lápide | Must |
| RF-161 | `brain_message_pop` entrega uma mensagem uma única vez, na mesma transação. O briefing avisa a quantidade esperando para o agente destinatário | Must |
| RF-162 | O mesmo id de resposta conta uma vez nos eventos `stop` e `post-tool`. Sem uso, o relatório diz desconhecido | Must |
| RF-163 | `nix run <agente>` instala hook e MCP se faltarem (`--no-autowire` desliga). A cópia do histórico nativo é temporária, só leitura, permissão só do usuário, apontada por `NIX_PREVIOUS_SESSION_HISTORY` e apagada ao terminar. Leitores v1: Claude Code e Codex. Sem leitor, segue com aviso | Must |
| RF-164 | O briefing do `session-start` sai nesta ordem: perfil (até 3000 bytes, 6000 se o projeto não tem memória), handoff oferecido e não consumido, resumo do projeto, aviso de mensagens, aviso de sessão interrompida. O texto é histórico, nunca uma ordem | Must |

As ferramentas `brain_*` só aparecem no MCP com o Mega Brain ligado. `remember` continua gravando na wiki padrão e não faz parte do Mega Brain.

## 6. Histórias de usuário

Os critérios de aceite de cada história ficam em [`bdd/`](./bdd), em Gherkin, com o mesmo ID (`@HU-01`, `@HU-01.1`…). O [BDD.md](./BDD.md) é o índice.

**HU-01 — Primeira configuração**
> Como usuário, quero apontar o caminho do meu vault e indexá-lo, para o editor passar a consultá-lo.

**HU-02 — Indexar um vault existente**
> Como usuário com um vault de anos, quero indexar tudo de uma vez, para poder consultar meu histórico.

**HU-03 — Sincronizar mudanças feitas fora do Nix**
> Como usuário, depois de escrever direto nos arquivos, quero atualizar o índice quando eu decidir.

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

**HU-16 — Wiki genérica**
> Como usuário, quero chamar a base de wiki.

**HU-17 — Captura do Mega Brain**
> Como usuário, quero gravar a conversa só quando eu ligar o Mega Brain e instalar o hook, e quero excluir caminhos sensíveis.

**HU-18 — Briefing e handoff**
> Como usuário, quero que a sessão nova mostre o histórico e que o handoff seja reivindicado uma única vez.

**HU-19 — Perfil entre projetos**
> Como usuário, quero que uma preferência repetida vire página de perfil, e que o que eu esquecer não volte.

**HU-20 — Mensagens entre agentes**
> Como usuário, quero deixar um recado que só o primeiro a buscar recebe, e ser avisado no início da sessão.

**HU-21 — Tokens**
> Como usuário, quero o uso de cada resposta uma vez, e ver desconhecido quando o agente não informa números.

**HU-22 — Painel do Mega Brain**
> Como usuário, quero filtrar os projetos pelo nome e abrir as abas do projeto com a aba na URL.

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

- **RN-01 — Consentimento de indexação.** O Nix nunca varre nem vetoriza o vault por iniciativa própria. Não há watcher de arquivos nem indexação em background. A indexação ocorre só por `nix sync` ou pela ferramenta `sync_index`.
- **RN-02 — Coerência write-through.** Toda escrita originada nas ferramentas tenta atualizar o índice na mesma operação. Se a vetorização falhar, o arquivo no vault é preservado (fonte da verdade), o arquivo é marcado com `status = error` e o usuário é instruído a rodar `nix sync` ou `sync_index`.
- **RN-03 — Confinamento ao vault.** Nenhuma leitura ou escrita ocorre fora do diretório do vault da operação, incluindo tentativas via caminho relativo ou link simbólico.
- **RN-04 — Proveniência da fonte.** Toda resposta de ferramenta que devolve conteúdo do vault inclui caminho relativo e o trecho (ou o corpo da nota). A fidelidade da resposta em linguagem natural é responsabilidade do cliente LLM.
- **RN-05 — Não destruição silenciosa.** Sobrescrita e remoção exigem confirmação e geram backup.
- **RN-06 — Respeito aos filtros.** Notas excluídas pela configuração não são indexadas, lidas nem citadas.
- **RN-07 — Consentimento do Mega Brain.** A captura exige o Mega Brain ligado e um hook global daquele agente ou um hook do projeto. O `.nix.toml` pode desligar a captura ou excluir caminhos. Sem isso, o banco não recebe o evento.
- **RN-08 — Uma entrega.** Há no máximo um handoff aberto por projeto, e `accept` o reivindica uma única vez. `brain_message_pop` entrega cada mensagem uma única vez.
- **RN-09 — Evidência, não ordem.** Briefing, handoff e páginas de sessão são histórico. O texto nunca é uma ordem para o agente.

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
- Servidor MCP stdio com 20 ferramentas de wiki (leitura parcial, frontmatter preservando o YAML, tags, movimentação com links e prepend, `list_wikis`, `wiki_insights`) e, com o Mega Brain ligado, as 18 `brain_*`. Recursos `nix://note/{+rel_path}` (wiki padrão) e `nix://wiki/{name}/note/{+rel_path}`. Logs de tráfego em arquivo e em `.nix/traffic.db`.
- CLI de bootstrap: `init [--name] [--wiki] [--embedding-model] [--force]` (a primeira wiki chama-se `Default` se `--name` for omitido), `wiki` (listar, cadastrar, renomear, remover, padrão, pasta e ajustes), `sync` e `status` com `--wiki` repetível e `--all`, `doctor` (com `--json` em `sync`/`status`/`doctor`); no terminal, `nix` sem argumentos abre a interface mesmo antes do init; sem terminal, inicia o servidor, que exige o init. Uma configuração anterior, de uma wiki só, vira o `Default` e conserva o índice e os backups já gravados.
- Várias wikis nomeadas (de 1 a 100, exatamente um padrão) no mesmo processo. Ferramenta sem `wiki` usa o padrão. Busca em uma, em várias ou em todas. Escrita numa única wiki.
- Instalador `install.bat` / `install.ps1` / `install.sh` (`nix` e `nix-hook` da release, SHA-256, `NIX_HOME`/`nix` no PATH; a wiki fica para a interface).
- Desinstalador `uninstall.bat` / `uninstall.ps1` / `uninstall.sh` (remove PATH/`NIX_HOME`, `nix` e `nix-hook`, `.nix/`, `settings.db` e o cache `onefile-*`/`hook-*`; apaga a pasta da instalação se ficar vazia; não toca no vault). No Windows, se o binário estiver em uso, para antes de alterar o PATH.
- CLI `nix config` (listar, gravar, remover, histórico e desfazer) e interface local (`nix` no terminal, ou `nix ui` depois do init): status com o bloco Para começar até a wiki escolhida ter sido sincronizada e o editor ter chamado uma ferramenta (o aviso de índice desatualizado só depois dessa sincronização), sincronização com progresso e controles desligados até o fim do job, diagnóstico, busca em uma ou mais wikis, notas, tags, insights explicados na página, Mega Brain, conexão de clientes, tráfego MCP, backups com restauração, tela Wikis, configuração e histórico.
- Servidor MCP recarrega a configuração entre chamadas; modelo de embedding e pasta do índice pedem reinício do cliente.
- Registro MCP: `command` aponta para o binário em `NIX_HOME` (Windows: `${env:NIX_HOME}/bin/nix.exe` ou caminho absoluto; macOS/Linux: `{NIX_HOME}/bin/nix` absoluto). A interface gera o trecho de Cursor, VS Code, Claude Code e Codex.
- Escrita com write-through, confirmação e backup.
- Mega Brain: `brain.db`, `nix brain enable`, hooks com prévia e backup, páginas de sessão na wiki escolhida, briefing, handoff, perfil sem LLM, mensagens, tokens, `nix run` e o painel na interface. Os links de perfil e de conhecimento abrem a wiki configurada. A migração do `settings.db` renomeia `vaults` para `wikis` sem mexer em índices nem backups.
- Filtros pasta/tag/data e wikilinks.
- Memória de longo prazo (`remember` → `longterm_folder` da wiki), insights (órfãs, duplicatas, links, resumo).
- Erros de domínio (`NixError`) na CLI e no MCP vão para stderr, sem traceback.
- Seções globais graváveis: `index`, `retrieval`, `safety`, `logging`, `brain` e `profile`. O cadastro das wikis fica à parte (`nix wiki`). Um campo global definido por `NIX_SECAO__CAMPO` ganha do banco.
- Guia publicado em `https://paulocesaaars.github.io/nix/` a cada push na `main` que altera `site/`. A release também publica a ficha `server.json` no MCP Registry.

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

Interface de edição de notas ou plugin de editor; LLM/chat/agente próprio; CLI de consulta (`ask`/`chat`); transporte MCP HTTP; multiusuário; hospedagem em nuvem; servidor de time; processo residente; edição de anexos binários; geração automática de notas sem pedido do usuário (a página de sessão e o perfil do Mega Brain são a exceção e dependem de `nix brain enable` e do hook, RN-07); migração do `sessions.db`; banco vetorial separado para sessões; sincronização de arquivos entre dispositivos.

## 13. Glossário

- **Wiki** — diretório de notas em Markdown. O Nix guarda de 1 a 100, cada um com nome. O padrão é o usado quando o nome é omitido.
- **Chunk** — trecho de uma nota, unidade indexada e recuperada.
- **Embedding** — representação vetorial de um chunk, usada para busca por similaridade.
- **MCP** — Model Context Protocol. O Nix expõe ferramentas exclusivamente via stdio.
- **Write-through** — política em que uma escrita atualiza dado e índice na mesma operação.
- **Mega Brain** — memória entre agentes, desligada por padrão, com páginas na wiki escolhida em `nix brain enable`.
- **Sessão** — conversa de um agente com o projeto, gravada pelos hooks em `brain.db` e resumida numa página da wiki.
- **Handoff** — texto oferecido de onde a sessão parou. Há no máximo um aberto por projeto, reivindicado uma única vez. Não é uma ordem.
- **Perfil** — preferência repetida em projetos suficientes, em `profile/<categoria>/`, sem modelo de linguagem. Esquecer vira lápide.
- **Hook de captura** — comando `nix-hook brain` que o agente chama a cada evento, instalado com `nix brain hooks install`.
- **Wikilink** — referência entre notas no formato `[[Nome da Nota]]`.
- **Instalador** — `install.bat` / `install.ps1` / `install.sh`: baixa `nix` e `nix-hook`, confere o SHA-256, grava `NIX_HOME` e pede para executar `nix`. A wiki entra na interface ou com `nix init`. O MCP e `nix ui` exigem o `nix init`.
- **Desinstalador** — `uninstall.bat` / `uninstall.ps1` / `uninstall.sh`: remove `NIX_HOME` e o `nix` do PATH, apaga `nix` e `nix-hook`, `.nix/`, `settings.db` e o cache `onefile-*`/`hook-*`, e a pasta da instalação se ficar vazia; não altera o vault. No Windows, se o binário estiver em uso, para antes de alterar o PATH.
