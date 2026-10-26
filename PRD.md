# PRD — Nix, Servidor MCP de Conhecimento

| Campo | Valor |
| --- | --- |
| Produto | **Nix** (nome inspirado na Lulu, cachorra do autor) |
| Tipo | Servidor MCP que expõe um vault Obsidian a agentes de desenvolvimento |
| Interfaces | MCP stdio (único transporte do protocolo); CLI (`init`, `config`, `sync`, `status`, `doctor`, `ui`); interface local só enquanto `nix ui` está aberto; instalador `install.bat` / `install.sh` (binário único, `NIX_HOME` + `nix` no PATH, sem Python); desinstalador `uninstall.bat` / `uninstall.sh` |
| Status | Implementado — v2.0.1 |
| Autor | Paulo |
| Data | 2026-10-26 |

Especificações técnicas: [TDD.md](./TDD.md).

---

## 1. Visão

Nix é a ponte entre bases de conhecimento em Markdown (Obsidian) e agentes de desenvolvimento como Cursor, Claude Code e Copilot. Em vez de o usuário lembrar onde cada anotação foi salva, o agente do editor chama ferramentas do Nix para buscar, ler, criar e atualizar notas — com o índice local sempre alinhado às escritas do próprio Nix.

Tudo roda na máquina do usuário. Embeddings e banco vetorial são locais e gratuitos. Não há LLM no Nix: o raciocínio fica no cliente MCP.

## 2. Problema

Vaults de Obsidian crescem rápido e viram um arquivo morto. Hoje o usuário enfrenta:

- **Busca literal insuficiente.** A busca do Obsidian encontra palavras, não ideias. Quem não lembra o termo exato usado não acha a nota.
- **Conhecimento fragmentado.** A resposta para uma pergunta costuma estar espalhada em várias notas, e sintetizar isso manualmente é caro.
- **Captura com atrito.** Registrar uma nota nova no formato certo, com os links e tags corretos, exige abrir o Obsidian e lembrar das convenções.
- **Agentes de desenvolvimento não conhecem o vault.** Cursor, Claude Code e Copilot não têm, por padrão, busca semântica nem escrita segura nas anotações pessoais.

## 3. Objetivos

| # | Objetivo | Como será medido |
| --- | --- | --- |
| O1 | Entregar trechos relevantes do vault ao cliente MCP, com caminho e citação da nota | ≥ 90% das buscas trazem a nota certa no top-5 em um conjunto de 30 perguntas de avaliação |
| O2 | Dar ao usuário controle explícito sobre quando a base é vetorizada | Nenhuma vetorização de arquivos externos ocorre sem `nix sync` ou `sync_index` |
| O3 | Manter o índice consistente após edições feitas pelas ferramentas | 100% das escritas via MCP refletidas no índice ao final da operação |
| O4 | Custo zero e privacidade | Embeddings e banco vetorial 100% locais e gratuitos; nenhuma chamada remota |
| O5 | Encaixar no fluxo do editor | Registrável como servidor MCP stdio em Cursor, Claude Code e Copilot |

### Não-objetivos (v1)

- Não é um substituto do Obsidian. A interface local cobre configuração e operação (status, sincronização, diagnóstico e histórico), não a edição das notas.
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
| RF-01 | O sistema deve guardar a configuração num SQLite na pasta da instalação (`settings.db`), com o caminho do vault e os demais parâmetros | Must |
| RF-02 | O sistema deve oferecer um comando de inicialização que grava o vault (ou recebe `--vault`) e o modelo de embedding (ou recebe `--embedding-model`) no `settings.db` e, se a configuração já existir, só atualiza `vault.path` salvo `--force` ou `--embedding-model` | Must |
| RF-03 | O sistema deve permitir sobrescrever qualquer configuração por variável de ambiente, e essa variável deve ganhar do valor gravado | Must |
| RF-04 | O sistema deve validar a configuração antes de gravar e apresentar mensagens de erro acionáveis (vault inexistente, modelo inválido, campo desconhecido) | Must |
| RF-05 | O sistema deve permitir configurar padrões de inclusão/exclusão de arquivos e pastas (ex.: ignorar `Templates/`, `.trash/`, notas privadas) | Should |
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
| RF-33 | Toda escrita deve ficar restrita ao diretório do vault configurado | Must |
| RF-34 | Operações destrutivas (sobrescrever, remover) devem exigir `confirm=true` e ser sinalizadas como destrutivas no MCP | Must |
| RF-35 | O sistema deve manter um backup da versão anterior do arquivo antes de sobrescrever | Should |
| RF-36 | O sistema deve seguir convenções do vault (template, tags, formato de nome de arquivo) definidas na configuração | Could |

### 5.5 CLI de bootstrap

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-40 | A CLI deve gravar a configuração inicial (`nix init [--vault PATH] [--embedding-model NOME] [--force]`) | Must |
| RF-41 | A CLI deve oferecer sincronização e status do índice (`nix sync`, `nix status`) | Must |
| RF-42 | A CLI deve diagnosticar ambiente, config e índice (`nix doctor`); `--json` emite o dump completo | Should |
| RF-43 | Sem subcomando, `nix` deve iniciar o servidor MCP stdio | Must |
| RF-44 | `nix sync` e `nix status` devem oferecer saída em JSON (`--json`) | Could |
| RF-45 | Um instalador (`install.bat` / `install.ps1` no Windows, `install.sh` no Unix) deve baixar o binário da plataforma, conferir o SHA-256, gravar `NIX_HOME`, colocar `{NIX_HOME}/bin` no PATH do usuário e iniciar `nix init` se ainda não houver `settings.db`. Não exige Python na máquina | Must |
| RF-46 | Um desinstalador (`uninstall.bat` / `uninstall.ps1` no Windows, `uninstall.sh` no Unix) deve remover `NIX_HOME` e `{NIX_HOME}/bin` do PATH do usuário só se apontarem para esta instalação, apagar o binário, `.nix/` e `settings.db` (e os arquivos `-wal`/`-shm`), e não tocar no vault. `--keep-data` preserva `settings.db` e `.nix/` | Must |

### 5.6 Interface MCP

| ID | Requisito | Prioridade |
| --- | --- | --- |
| RF-50 | O sistema deve expor um servidor MCP **somente via stdio**, iniciado pelo cliente | Must |
| RF-51 | O servidor MCP deve expor as 19 ferramentas de busca, leitura, escrita, tags, movimentação, insights e sincronização do vault (`search_notes`, `read_note`, `get_note_outline`, `read_note_lines`, `list_notes`, `list_all_tags`, `get_linked_notes`, `create_note`, `append_to_note`, `update_note`, `update_frontmatter`, `manage_tags`, `move_note`, `move_file`, `delete_note`, `sync_index`, `index_status`, `vault_insights`, `remember`) | Must |
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
| RF-62 | `nix ui` deve abrir no navegador uma interface local de status, sincronização (com prévia e progresso), diagnóstico, configuração e histórico. Sem `nix init`, o comando não sobe. A interface escuta só em `127.0.0.1`, exige o link impresso pelo comando e encerra com Ctrl+C ou pelo botão Encerrar. Com sincronização em andamento, o botão pede para esperar e o Ctrl+C só fecha o índice depois que a thread termina | Must |
| RF-63 | Um servidor MCP já em execução deve passar a usar a configuração nova na chamada seguinte. Modelo de embedding e pasta do índice continuam os anteriores até o cliente reiniciar. Troca de modelo exige `nix sync --full` | Must |

## 6. Histórias de usuário e critérios de aceite

**HU-01 — Primeira configuração**
> Como usuário, quero apontar o caminho do meu vault e indexá-lo, para o editor passar a consultá-lo.

- Dado que o Nix nunca foi configurado, quando executo `nix init` e informo o vault e o modelo de embedding, então `settings.db` é criado na pasta do Nix com `vault.path` e `index.embedding_model` preenchidos (barras `/` no Windows).
- Dado `--vault CAMINHO` e `--embedding-model NOME`, quando executo `nix init`, então não há prompt e os valores são gravados.
- Dado que a configuração já existe e não passei `--force` nem `--embedding-model`, quando executo `nix init`, então só `vault.path` é atualizado e o restante permanece.
- Dado que o caminho informado no prompt ainda não existe, quando confirmo a criação, então o diretório é criado e gravado em `vault.path`.
- Dado que o caminho do vault não existe, quando valido com `nix doctor`, então recebo um erro apontando o caminho inválido.

**HU-02 — Indexar um vault existente**
> Como usuário com um vault de anos, quero indexar tudo de uma vez, para poder consultar meu histórico.

- Dado um vault com N notas em Markdown, quando executo `nix sync`, então todas as notas não ignoradas são vetorizadas e um resumo com contagens e tempo é exibido.
- Dado que o processo é longo, quando a sincronização roda, então vejo progresso incremental.
- Dado que uma nota tem encoding inválido, quando a sincronização roda, então ela é reportada como erro ao final e as demais são indexadas normalmente.

**HU-03 — Sincronizar mudanças feitas no Obsidian**
> Como usuário, depois de escrever direto no Obsidian, quero atualizar o índice quando eu decidir.

- Dado que editei 3 notas e apaguei 1 fora do Nix, quando executo `nix sync` (ou `sync_index`), então apenas essas 4 notas são reprocessadas e a apagada é removida do índice.
- Dado que nada mudou, quando executo a sincronização, então nenhuma nota é reprocessada e isso é informado.
- Dado que o vault mudou e eu não sincronizei, quando chamo `index_status`, então recebo aviso de índice desatualizado — e nenhuma vetorização automática acontece.

**HU-04 — Instalar o ambiente**
> Como usuário, quero um único arquivo para copiar, sem instalar Python, e que a configuração do vault comece em seguida.

- Dado um Windows amd64, Linux (amd64 ou arm64) ou macOS Apple Silicon, sem Python no PATH, quando executo `install.bat`, `.\install.ps1` ou `sh install.sh`, então o binário da plataforma é baixado, o SHA-256 confere, `NIX_HOME` aponta para a pasta da instalação, `{NIX_HOME}/bin` entra no PATH do usuário, `nix init` pergunta o vault se ainda não houver `settings.db`, e a mensagem de **configuração concluída** é exibida.
- Dado que a instalação concluiu, quando abro um **novo** terminal em qualquer diretório, então `nix sync` (e os demais subcomandos) são encontrados no PATH.
- Dado que já existe outro `nix` no PATH (gerenciador NixOS/Nixpkgs), quando o instalador registra o comando, então um aviso é emitido e este projeto passa a ter prioridade no PATH.
- Dado `--vault CAMINHO` no instalador, quando ele chega no `init`, então o argumento é repassado e o prompt do vault é pulado.
- Dado que `NIX_HOME` já aponta para uma pasta com `settings.db`, quando rodei o instalador de novo, então essa pasta é preservada, o binário em `{NIX_HOME}/bin` é substituído e o `init` não é repetido.
- Dado Windows arm64 ou macOS Intel, quando executo o instalador, então ele recusa a arquitetura e diz qual binário existe.

**HU-07 — Desinstalar o ambiente**
> Como usuário, quero um único executável que desfaça a instalação sem apagar o vault.

- Dado uma instalação concluída, quando executo `uninstall.bat`, `.\uninstall.ps1` ou `sh uninstall.sh` e confirmo, então `NIX_HOME` e `{NIX_HOME}/bin` saem do PATH do usuário, o binário, `.nix/` e `settings.db` são apagados, e o vault permanece intacto.
- Dado `--keep-data`, quando desinstalo, então o PATH é desfeito e o binário some, mas `settings.db` e `.nix/` permanecem.
- Dado `--yes` (ou `-y`), quando não há terminal interativo, então a confirmação é dispensada e a desinstalação segue.
- Dado que `NIX_HOME` aponta para outra pasta, quando desinstalo esta cópia, então a variável e o bloco de shell da outra instalação não são removidos.
- Dado que a desinstalação concluiu, quando abro um **novo** terminal, então o comando `nix` deste projeto não é encontrado no PATH.

**HU-05 — Registrar conhecimento pelo editor**
> Como usuário, quero pedir ao agente do editor que crie uma nota, e que ela já fique pesquisável.

- Dado que peço a criação de uma nota, quando ela é gravada no vault, então imediatamente após a operação ela já retorna em buscas — sem sincronização manual.
- Dado que a nota já existe, quando peço para sobrescrever, então a ferramenta exige `confirm=true`.
- Dado que peço para gravar fora do vault, quando a operação é tentada, então ela é rejeitada.

**HU-06 — Usar o Nix dentro do Cursor (ou equivalente)**
> Como usuário, quero acessar meu vault de dentro do editor.

- Dado o Nix registrado no cliente MCP com `command` apontando para o binário na pasta da instalação (Windows: `${env:NIX_HOME}/bin/nix.exe` ou o caminho absoluto; macOS/Linux: `{NIX_HOME}/bin/nix` absoluto), quando peço ao agente do editor algo sobre minhas notas, então ele usa as ferramentas do Nix e recebe trechos com caminho e citação.
- Dado `"command": "nix"` (só o nome no PATH) na IDE aberta pelo Dock/menu, quando o cliente tenta iniciar o processo, então a conexão falha com `spawn nix ENOENT`.
- Dado macOS ou Linux, quando o `command` do MCP é o caminho absoluto da linha `comando nix:` do `nix doctor` (`{NIX_HOME}/bin/nix`), então o servidor sobe.
- Dado que peço uma alteração de nota via MCP, quando ela é aplicada, então o índice é atualizado automaticamente.
- Dado `update_note` em modo replace ou `delete_note`, quando o cliente chama a ferramenta, então a escrita só ocorre com `confirm=true` após aprovação (anotação `destructiveHint`).

**HU-08 — Configurar e operar pela interface**
> Como usuário, quero ver o índice, sincronizar e ajustar a configuração sem editar arquivo à mão.

- Dado que já rodei `nix init`, quando executo `nix ui`, então o navegador abre numa página local e o terminal mostra a URL.
- Dado que ainda não configurei, quando executo `nix ui`, então o comando pede `nix init` e não sobe servidor.
- Dado a página de configuração, quando salvo um campo válido, então o valor passa a valer e a origem deixa de ser o padrão.
- Dado um campo definido por variável de ambiente, quando abro a configuração, então o campo aparece travado.
- Dado que desfaço uma alteração no histórico, quando a operação termina, então o valor anterior volta a valer.
- Dado o botão Encerrar ou Ctrl+C no terminal, quando confirmo e não há sincronização, então o processo da interface termina.
- Dado uma sincronização em andamento, quando clico em Encerrar, então a página pede para esperar. Ctrl+C nesse meio só fecha o índice depois que a sincronização termina.

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
- **RN-03 — Confinamento ao vault.** Nenhuma leitura ou escrita ocorre fora do diretório configurado, incluindo tentativas via caminho relativo ou link simbólico.
- **RN-04 — Proveniência da fonte.** Toda resposta de ferramenta que devolve conteúdo do vault inclui caminho relativo e o trecho (ou o corpo da nota). A fidelidade da resposta em linguagem natural é responsabilidade do cliente LLM.
- **RN-05 — Não destruição silenciosa.** Sobrescrita e remoção exigem confirmação e geram backup.
- **RN-06 — Respeito aos filtros.** Notas excluídas pela configuração não são indexadas, lidas nem citadas.

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
- Servidor MCP stdio com 19 ferramentas (leitura parcial, frontmatter preservando o YAML, tags, movimentação com links e prepend), recursos `nix://note/{+rel_path}`, logs de tráfego em arquivo.
- CLI de bootstrap: `init [--vault] [--embedding-model] [--force]`, `sync`, `status`, `doctor` (com `--json` em `sync`/`status`/`doctor`); `nix` sem argumentos inicia o servidor.
- Instalador `install.bat` / `install.ps1` / `install.sh` (binário único da release, SHA-256, `NIX_HOME`/`nix` no PATH, `nix init`).
- Desinstalador `uninstall.bat` / `uninstall.ps1` / `uninstall.sh` (remove PATH/`NIX_HOME`, o binário, `.nix/` e `settings.db`; não toca no vault).
- CLI `nix config` (listar, gravar, remover, histórico e desfazer) e interface local `nix ui` (status, sincronização com progresso, diagnóstico, configuração e histórico).
- Servidor MCP recarrega a configuração entre chamadas; modelo de embedding e pasta do índice pedem reinício do cliente.
- Registro MCP: `command` aponta para o binário em `NIX_HOME` (Windows: `${env:NIX_HOME}/bin/nix.exe` ou caminho absoluto; macOS/Linux: `{NIX_HOME}/bin/nix` absoluto). Exemplos em `.cursor/mcp.json`.
- Escrita com write-through, confirmação e backup.
- Filtros pasta/tag/data, wikilinks, reordenação opcional (`retrieval.rerank`).
- Memória de longo prazo (`remember` → `vault.longterm_folder`), insights (órfãs, duplicatas, links, resumo).
- Erros de domínio (`NixError`) na CLI e no MCP vão para stderr, sem traceback.
- Seções de configuração fora de `vault`, `index`, `retrieval`, `safety` e `logging` não são gravadas. Um campo definido por `NIX_SECAO__CAMPO` ganha do banco.

**Próximo**

- Conjunto de avaliação `eval/` (harness e 30 perguntas; ainda não está no repositório).
- Reordenação ligada por padrão e outras melhorias de qualidade de recuperação.
- Registro documentado para mais clientes MCP (Claude Code, Copilot) além do Cursor.

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

Interface de edição de notas ou plugin do Obsidian; LLM/chat/agente próprio; CLI de consulta (`ask`/`chat`); transporte MCP HTTP; multiusuário; hospedagem em nuvem; edição de anexos binários; geração automática de notas sem pedido do usuário; sincronização de arquivos entre dispositivos.

## 13. Glossário

- **Vault** — diretório do Obsidian contendo as notas em Markdown.
- **Chunk** — trecho de uma nota, unidade indexada e recuperada.
- **Embedding** — representação vetorial de um chunk, usada para busca por similaridade.
- **MCP** — Model Context Protocol. O Nix expõe ferramentas exclusivamente via stdio.
- **Write-through** — política em que uma escrita atualiza dado e índice na mesma operação.
- **Wikilink** — referência entre notas no formato `[[Nome da Nota]]`.
- **Instalador** — `install.bat` / `install.ps1` / `install.sh`: baixa o binário único, confere o SHA-256, grava `NIX_HOME` e dispara `nix init`.
- **Desinstalador** — `uninstall.bat` / `uninstall.ps1` / `uninstall.sh`: remove `NIX_HOME` e o `nix` do PATH, apaga o binário, `.nix/` e `settings.db`; não altera o vault.
