---
name: atualizar-docs
description: >-
  Atualiza PRD.md, TDD.md e README.md para refletir somente o que existe no
  código commitado. Não faz perguntas nem chama outras skills ou scripts.
  Commita e envia somente as alterações produzidas com a mensagem
  "documentacao atualizada". Use para pedidos de atualização ou sincronização
  da documentação após mudanças no código. Pedidos apenas de revisão ou
  análise não autorizam executar este fluxo.
---

# Atualizar documentação

Atualize apenas os documentos de produto, técnico e de uso (`PRD.md`,
`TDD.md` e `README.md`, ou equivalentes do repositório), em português (Brasil).
Não altere código, testes, configuração ou versão. Não crie marcadores de
revisão. Não faça perguntas, ofertas ou chamadas a outras skills ou scripts.

## 1. Conferir a implementação commitada

Leia as instruções do repositório e identifique os documentos de destino.
Fixe o commit de referência com `git rev-parse HEAD`. Inspecione o estado
completo desse commit com `git ls-tree -r --name-only <commit>`,
`git show <commit>:<caminho>` e `git grep -n <termo> <commit> -- <caminhos>`.
O histórico é apenas apoio: não use a última edição dos documentos como
prova de revisão da implementação.

Considere capacidades, contratos, dependências, estrutura, configuração e
operação. Inclua implementações em Markdown, como skills, prompts e comandos;
não exclua arquivos apenas pela extensão.

Ignore mudanças não commitadas, no stage e arquivos não rastreados como
fonte de comportamento, sem emitir alertas sobre eles. Preserve as edições
locais existentes nos documentos.

## 2. Atualizar os documentos

- **PRD:** capacidades, regras de negócio, objetivos atendidos e limites
  comprovados na implementação commitada. Não inclua planos ou requisitos futuros.
- **TDD:** stack, componentes, estrutura, dados, interfaces, configuração,
  segurança e decisões técnicas existentes no commit de referência.
- **README:** instalação, primeiros passos, comandos, configuração e operação
  disponíveis nesse commit.

Cada assunto tem um documento dono; os demais apontam para ele, sem repetir
os detalhes. Descreva o estado atual, não um changelog.

Confira toda afirmação no commit de referência: comandos, parâmetros,
retornos, chaves, padrões e versões. Remova ou corrija conteúdo incompatível
com o que existe e foi commitado, inclusive funcionalidades apenas planejadas.
Se o PRD divergir do código commitado, ajuste o documento ao comportamento
comprovado, sem perguntar qual deve prevalecer. Não invente comportamento.

Preserve estilo, organização e identificadores existentes. Não renumere
requisitos. Atualize datas ou status existentes apenas quando a alteração
justificar. Não acrescente cenários especiais de execução da skill à
documentação do produto.

## 3. Verificar consistência

Confira nomes, contagens, comandos, versões, configuração e padrões entre
os documentos e o commit de referência. Confira links relativos e duplicações.
Revise o diff e rode `git diff --check` apenas nos documentos alterados.
Não execute scripts do projeto.

## 4. Commitar e enviar

Inclua somente alterações de documentação produzidas nesta execução.
Preserve edições anteriores do usuário e conteúdo previamente no stage;
se necessário, selecione somente os trechos desta atualização.
Não use `git add .`, `git add -A`, `--amend`, `--no-verify` ou push forçado.

Crie o commit com a mensagem exata `documentacao atualizada` e faça push da
branch atual para seu upstream. Sem upstream, use o remoto configurado para
a branch; se houver um único remoto, envie para ele com o mesmo nome da
branch e configure o upstream.

Não suba versão, crie tags, publique release ou abra PR. Não chame outras
skills. Não faça pull, merge ou rebase para resolver rejeições de push.
Se uma operação falhar ou o destino não puder ser determinado, preserve o
estado e relate o impedimento, sem perguntas. Sem alterações produzidas,
não crie commit vazio nem envie commits alheios.

## 5. Relatar

Informe brevemente os documentos atualizados, o hash do commit e o resultado
do push. Relate falhas efetivas de execução, se houver. Não faça perguntas
nem ofereça etapas adicionais.
