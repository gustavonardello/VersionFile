# Contexto do projeto VersionFile

> Documento de referência para pessoas e assistentes que iniciarem uma nova sessão de trabalho neste repositório.
>
> Última leitura integral do código: 12/09/2026
> Versão declarada no código: `1.2.4`

## 1. Resumo executivo

O **VersionFile** é uma aplicação desktop para Windows que organiza, edita e versiona regras da plataforma Senior escritas em **LSP (Linguagem Senior de Programação)**.

Neste projeto, “LSP” significa a linguagem de programação da Senior. Não se trata do protocolo *Language Server Protocol*.

O problema que o aplicativo resolve é manter regras de vários clientes e projetos organizadas em um único local, com histórico, metadados, comparação e exportação. A estrutura principal é:

```text
Cliente
└── Projeto
    └── Regra
        └── Versões
```

O público provável são desenvolvedores, consultores e equipes que mantêm customizações da plataforma Senior e precisam localizar regras, editar conteúdo e recuperar versões anteriores sem depender apenas de pastas soltas.

A aplicação é:

- desktop e local, sem servidor de aplicação;
- escrita em Python 3.11;
- construída com PyQt6 e QScintilla;
- persistida em SQLite com SQL direto, sem ORM;
- empacotada com PyInstaller;
- instalada por usuário com Inno Setup, sem exigir privilégios administrativos;
- atualizada a partir das Releases do GitHub.

## 2. Objetivos funcionais

O VersionFile permite:

- cadastrar clientes;
- cadastrar projetos vinculados a um cliente;
- classificar projetos como `DID`, `Projeto`, `Regra`, `Webservice` ou `Relatório`;
- cadastrar regras ou seções de relatório dentro de um projeto;
- cadastrar portas dentro de projetos do tipo Webservice;
- editar código LSP com destaque de sintaxe;
- manter várias versões de cada regra;
- marcar uma versão como a versão atual;
- registrar tipo, status e notas em cada versão;
- navegar entre versões sem perder edições pendentes;
- comparar duas versões lado a lado;
- pesquisar pelo nome e, opcionalmente, pelo conteúdo das regras;
- importar regras existentes a partir de estruturas de pastas;
- exportar uma regra ou várias regras em `.lsp`/`.txt`;
- personalizar as cores do editor;
- migrar de forma segura os dados de instalações antigas;
- verificar, baixar e instalar novas versões do aplicativo.

## 3. Princípios essenciais do produto

### 3.1 Os dados do usuário são mais importantes que a instalação

O projeto foi desenhado para que atualização, reinstalação ou desinstalação não apaguem regras dos usuários.

No executável instalado, código e dados ficam separados:

```text
Aplicação: %LOCALAPPDATA%\Programs\VersionFile
Dados:    %LOCALAPPDATA%\VersionFile
```

O instalador só manipula a pasta da aplicação. A pasta de dados não deve ser incluída em rotinas de limpeza ou desinstalação.

### 3.2 Escritas relacionadas devem ser atômicas

As mutações em SQLite passam pelas funções de `database/models.py`. O decorador `_atomica` e o contexto `transacao()` usam savepoints, inclusive quando uma operação está dentro de outra.

Fluxos compostos, como criar uma regra junto de sua primeira versão ou importar uma hierarquia inteira, precisam permanecer atômicos. Se uma etapa falhar, nenhuma parte incompleta deve ficar gravada.

### 3.3 Edição pendente não pode ser perdida silenciosamente

O editor tenta salvar:

- um segundo após a última alteração;
- quando perde o foco;
- antes de trocar de versão;
- antes de trocar ou desmarcar a regra;
- antes de abrir histórico ou comparação;
- antes de fechar a janela.

Se o banco falhar, o conteúdo continua no editor e a navegação ou o fechamento são impedidos para que o usuário possa tentar novamente.

### 3.4 Importação, exportação e migração não devem destruir dados

- Importações repetidas pulam regras que já existem.
- A importação inteira é revertida se um arquivo falhar.
- Exportações não sobrescrevem arquivos: colisões recebem sufixos como ` (2)`.
- Nomes são normalizados para serem válidos no Windows.
- Migrações copiam os dados e preservam a origem.
- Bancos existentes no destino não são sobrescritos.

## 4. Arquitetura

As responsabilidades estão separadas em três camadas principais:

```text
main.py
├── ui/          widgets, diálogos, sinais e interação do usuário
├── core/        regras de negócio, arquivos, temas, diff e atualização
└── database/    schema SQLite, migrações e funções CRUD
```

A conexão SQLite é criada no ponto de entrada e passada explicitamente para a janela, painéis, diálogos e funções de modelo. Não existe ORM nem repositório global de conexão.

### 4.1 Ponto de entrada

`main.py` executa, nesta ordem:

1. cria o `QApplication` e aplica o estilo Qt `Fusion`;
2. configura o ícone do aplicativo;
3. chama `garantir_dados()` antes de qualquer abertura do banco;
4. garante a existência de `config/themes.json` no local mutável;
5. inicializa ou migra o schema SQLite;
6. abre uma conexão;
7. cria e exibe `MainWindow`;
8. fecha a conexão em `finally` ao encerrar.

O argumento `--smoke-test` desabilita a consulta de atualizações e fecha a janela automaticamente após 500 ms.

### 4.2 Camada `database/`

`database/db.py` é responsável por:

- definir `DB_PATH`;
- criar conexões com `row_factory = sqlite3.Row`;
- ativar chaves estrangeiras;
- criar as tabelas;
- detectar necessidade de migração de schema;
- criar backup antes de migrar um banco que contém dados;
- executar migrações em transação;
- validar referências com `PRAGMA foreign_key_check`.

`database/models.py` contém:

- as dataclasses `Cliente`, `Projeto`, `Porta`, `Regra` e `Versao`;
- todas as operações CRUD;
- a infraestrutura de transações com savepoints;
- regras como validação de nome de cliente, promoção de outra versão após exclusão e proteção contra marcar uma versão pertencente a outra regra.

Widgets podem fazer consultas diretas de leitura em alguns fluxos, mas as escritas devem continuar passando pelas funções do modelo.

### 4.3 Camada `core/`

- `paths.py`: separa recursos empacotados (`base_path`) de dados mutáveis (`data_path`).
- `version_manager.py`: sugere o tipo da versão, importa versão individual e produz diff unificado.
- `highlighter.py`: lexer LSP customizado, carregamento seguro de temas e geração de estilos.
- `importer.py`: reconhece arquivos e estruturas de pastas e importa tudo atomicamente.
- `exporter.py`: sanitiza nomes e grava arquivos sem sobrescrever.
- `migration.py`: localiza e copia bancos de versões antigas com integridade e segurança.
- `updater.py`: consulta Releases do GitHub, valida o download e inicia o instalador.
- `text_utils.py`: normaliza texto para busca sem diferença de acentos ou caixa.
- `version.py`: fonte única da versão atual.

### 4.4 Camada `ui/`

- `main_window.py`: janela principal, menus, composição dos painéis e atualização automática.
- `tree_panel.py`: árvore Cliente → Projeto → Regra ou Cliente → Serviço → Porta, busca, barra de ações e menus de contexto.
- `editor_panel.py`: editor, autosave, navegação e ações de versão.
- `dialogs.py`: formulários de cliente, projeto, regra, relatório e versão.
- `diff_viewer.py`: comparação visual lado a lado.
- `version_history.py`: histórico em cartões com carregar/excluir.
- `import_dialog.py`: seleção, preview e worker de importação.
- `export_dialog.py`: seleção hierárquica e exportação em lote.
- `migracao_dialog.py`: experiência de primeira execução e localização de dados antigos.
- `theme_color_dialog.py`: personalização das cores do lexer/editor.
- `errors.py`: apresentação uniforme de erros recuperáveis.

## 5. Modelo de dados

### 5.1 `clientes`

| Campo | Regra |
|---|---|
| `id` | chave primária autoincremental |
| `nome` | obrigatório e único |
| `criado_em` | data/hora local gerada pelo SQLite |

O nome é aparado antes da gravação e não pode ser vazio. Duplicidade é protegida pelo banco e tratada de forma amigável no fluxo da interface.

### 5.2 `projetos`

| Campo | Regra |
|---|---|
| `id` | chave primária |
| `cliente_id` | FK para cliente, com exclusão em cascata |
| `nome` | obrigatório |
| `tipo` | `DID`, `Projeto`, `Regra`, `Webservice` ou `Relatório` |
| `descricao` | opcional |
| `criado_em` | data/hora local |

O par `(cliente_id, nome)` é único.

### 5.3 `portas`

| Campo | Regra |
|---|---|
| `id` | chave primária |
| `projeto_id` | FK para projeto, com exclusão em cascata |
| `numero` | identificador textual da porta, como `443` ou `8080` |
| `criado_em` | data/hora local |

O par `(projeto_id, numero)` é único. Portas pertencem exclusivamente a projetos do tipo `Webservice`. Na interface, a porta representa diretamente o conteúdo editável: selecioná-la abre o editor e suas versões. Cada porta possui exatamente uma regra interna, que não aparece como outro nível da árvore. Excluir uma porta exclui esse conteúdo e suas versões por cascata, após confirmação.

### 5.4 `regras`

| Campo | Regra |
|---|---|
| `id` | chave primária |
| `projeto_id` | FK para projeto, com exclusão em cascata |
| `porta_id` | FK opcional; identifica a porta quando a regra é o armazenamento interno de um Webservice |
| `numero` | identificador textual da regra ou seção do relatório |
| `descricao` | opcional |
| `criado_em` | data/hora local |

O par `(projeto_id, numero)` é único.

Em projetos normais, a interface apresenta itens como `Regra 800`. Para projetos do tipo `Relatório`, `numero` representa uma seção/evento, por exemplo `Detalhe / Antes de Imprimir`.

### 5.5 `versoes`

| Campo | Regra |
|---|---|
| `id` | chave primária |
| `regra_id` | FK para regra, com exclusão em cascata |
| `numero` | sequencial por regra |
| `conteudo` | código da versão |
| `status` | estágio operacional |
| `notas` | descrição livre opcional |
| `atual` | booleano representado por `0`/`1` |
| `tipo` | natureza da alteração |
| `criado_em` | data/hora local |

Status aceitos:

- `Em desenvolvimento`
- `Em teste`
- `Produção`
- `Depreciada`

Tipos aceitos pela aplicação:

- `Criação`
- `Correção`
- `Melhoria`
- `Refatoração`

O número é único dentro de cada regra. Ao criar uma versão, todas as anteriores são desmarcadas e a nova vira atual. A exclusão da única versão é proibida. Se a versão atual for excluída, a versão restante de maior número é promovida.

## 6. Fluxos principais

### 6.1 Cadastro pela árvore

O painel esquerdo é uma `QTreeWidget`. Acima da lista há uma barra de ações: `+ Cliente` fica sempre disponível e os demais botões mudam conforme a seleção.

- sem seleção: `+ Cliente`;
- cliente: `+ Cliente`, `+ Projeto`, `Editar` e `Excluir`;
- projeto comum: `+ Cliente`, `+ Regra`, `Editar` e `Excluir`;
- projeto Webservice: `+ Cliente`, `+ Porta`, `Editar` e `Excluir`;
- porta: `+ Cliente`, `Editar` e `Excluir`; selecionar a porta abre o editor;
- regra: `+ Cliente`, `Editar` e `Excluir`.

As mesmas ações aparecem no menu de contexto:

- espaço vazio: novo cliente, expandir ou recolher tudo;
- cliente: novo projeto, renomear, excluir ou criar outro cliente;
- projeto comum: nova regra, editar projeto ou excluir;
- projeto Webservice: nova porta, editar projeto ou excluir;
- porta: editar ou excluir; não existe uma ação “Nova regra” nesse nível;
- regra: editar ou excluir.

Excluir um nível pai remove os filhos por cascata, depois de confirmação na interface.

A árvore salva os IDs de clientes, projetos e portas expandidos em `tree_state.json`, restaura a seleção quando possível e emite `regra_desmarcada` se o item selecionado deixar de existir.

O diálogo de projeto adapta o primeiro rótulo ao tipo: `Código` para DID, `Nome` para Projeto, `Código` para Regra, `Serviço` para Webservice e `Modelo` para Relatório. No tipo Regra há ainda o segundo campo `Nome`.

### 6.2 Particularidade de relatórios

Projetos `Relatório` usam `DialogRegraRelatorio`, com uma lista fixa de seções e eventos definida em `ESTRUTURA_RELATORIO`.

Exemplos de seções:

- Título;
- Cabeçalho;
- Detalhe;
- Subtotal;
- Total Geral;
- Inicialização;
- Finalização;
- Funções Globais;
- campos de descrição, cadastro, fórmula, totalizador e sistema.

Se a seção possui evento, o identificador salvo é `Seção / Evento`. Esse valor precisa ser sanitizado ao virar nome de arquivo porque `/` é inválido e poderia ser interpretado como separador de pasta.

### 6.3 Busca

A busca tem debounce de 300 ms e encontra correspondências em clientes, projetos e regras. A opção “Buscar no conteúdo” também examina todas as versões no banco.

A comparação é feita em Python após normalização Unicode. Assim:

- maiúsculas e minúsculas são equivalentes;
- `ação` pode ser encontrada por `acao`;
- `%` e `_` são literais, e não curingas SQL.

Quando há filtro, os ramos com resultado são exibidos e expandidos.

### 6.4 Edição e autosave

O editor é um `QsciScintilla` configurado com:

- UTF-8;
- fonte Consolas;
- números de linha;
- indentação de quatro espaços;
- autoindentação;
- destaque de palavras-chave, tipos, funções, números, strings, comentários, operadores, identificadores e constantes LSP.

Comentários reconhecidos pelo lexer:

- `@ ... @`;
- `@ ...` até o final da linha;
- `// ...`.

O painel começa vazio até uma regra ser selecionada. Ao abrir uma regra, carrega por padrão a versão marcada como atual. A lista de versões vem em ordem decrescente.

O autosave atualiza somente o conteúdo da versão aberta. Ele não cria uma nova versão automaticamente e não deve reconstruir o documento, pois isso apagaria o histórico de desfazer do QScintilla.

### 6.5 Criação e metadados de versões

“Nova versão” abre um diálogo para tipo e notas. O comportamento atual é importante:

- a nova versão começa com conteúdo vazio;
- ela não copia automaticamente o conteúdo da versão anterior;
- o tipo sugerido é calculado com base no conteúdo de referência atual comparado à versão mais recente;
- o usuário pode alterar a sugestão antes de confirmar.

A heurística de classificação considera a proporção de linhas alteradas:

- sem conteúdo anterior: `Criação`;
- até 20%: `Correção`;
- acima de 20% e até 60%: `Melhoria`;
- acima de 60%: `Refatoração`.

Tipo, status e notas são editados juntos exclusivamente por `DialogEditarVersao`. O painel lateral exibe as notas em modo somente leitura.

### 6.6 Histórico e exclusão

O histórico exibe todas as versões em cartões, da mais recente para a mais antiga, mostrando número, tipo, status, data, notas e marcador de versão atual.

Ele permite carregar uma versão pelo ID e excluir versões quando existe mais de uma. Usar o ID, e não apenas o índice do combo, evita carregar a versão errada depois de exclusões.

### 6.7 Comparação de versões

O `DiffViewer` compara duas versões lado a lado usando `difflib.SequenceMatcher`.

Classificações visuais:

- removido;
- adicionado;
- alterado;
- igual;
- vazio, usado para alinhar os lados.

Os scrolls vertical e horizontal são sincronizados. A presença ou ausência de quebra de linha no fim do arquivo é representada por um marcador próprio. O rodapé resume linhas removidas, adicionadas e alteradas.

### 6.8 Importação

Extensões reconhecidas pelo núcleo:

- `.txt`
- `.lsp`
- `.srule`
- `.rule`

Estruturas aceitas, inclusive quando coexistem:

```text
raiz/arquivo
raiz/projeto/arquivo
raiz/cliente/projeto/arquivo
```

Regras de interpretação:

- arquivo solto: cliente e projeto recebem o nome da pasta raiz;
- estrutura de dois níveis: o cliente recebe o nome da raiz;
- pastas cujo nome contém `did` são inferidas como `DID`;
- demais pastas usam `Projeto`, ou o tipo padrão escolhido no diálogo;
- leitura tenta UTF-8 e usa Latin-1 como fallback;
- entradas já existentes são puladas;
- cada regra importada recebe uma primeira versão;
- a importação completa é uma única operação atômica.

O preview é montado antes da confirmação. A escrita roda em `QThread`, com uma conexão SQLite própria aberta e fechada dentro da thread. O diálogo não pode ser fechado enquanto o worker está ativo.

### 6.9 Exportação

A exportação individual salva a versão aberta e sugere o nome:

```text
numero - descricao_vN.lsp
```

A exportação em lote permite:

- selecionar regras pela árvore;
- exportar a versão atual, a mais recente ou todas;
- escolher `.lsp` ou `.txt`;
- recriar ou não as subpastas Cliente/Projeto. Em Webservices, cada porta é exportada como o próprio arquivo editável.

Todos os componentes de caminho são sanitizados. Nomes reservados do Windows, caracteres inválidos, nomes vazios e tentativas de sair da pasta escolhida são tratados. Arquivos existentes nunca são sobrescritos.

## 7. Temas e aparência

O tema padrão fica em `config/themes.json`. O carregador:

- valida a estrutura JSON;
- valida cada cor com `QColor`;
- completa campos ausentes com uma paleta interna;
- usa um tema escuro interno se o arquivo estiver inválido;
- preserva uma cópia `themes.invalid-<data>.json` antes de substituir um arquivo inválido.

O usuário pode personalizar as cores usadas pelo lexer. O editor também possui botões para alternar fundo preto ou branco; essa preferência é salva em `ui_prefs.json`.

O modo branco do editor usa uma paleta própria codificada em `editor_panel.py`. Grande parte da interface geral ainda possui estilo escuro codificado diretamente nos widgets. Portanto, alterar `themes.json` não equivale a trocar todo o tema da aplicação.

## 8. Caminhos e persistência

`core/paths.py` diferencia dois conceitos:

### `base_path()`

Local de recursos somente leitura que acompanham o programa:

- durante desenvolvimento: raiz do repositório;
- no PyInstaller: diretório `_MEIPASS` do pacote.

Recursos principais: `config/themes.json`, `icone.ico` e `logo.png`.

### `data_path()`

Local de dados mutáveis:

- durante desenvolvimento: raiz do repositório;
- no executável: `%LOCALAPPDATA%\VersionFile`;
- fallback sem `LOCALAPPDATA`: `~/.versionfile`.

Arquivos mutáveis:

```text
versionfile.db
versionfile.bak-*.db
config/themes.json
config/ui_prefs.json
config/tree_state.json
config/update_check.json
```

### Atenção ao executar pelo código-fonte

Ao executar:

```powershell
py -3.11 main.py
```

o aplicativo usa o arquivo `versionfile.db` da raiz do projeto. Esse banco pode conter regras reais. Não o apague, não o recrie e não o use em testes de escrita automatizados.

A suíte oficial e `scripts/validar_interface.py` usam bancos temporários e são os caminhos seguros para testes automatizados.

## 9. Migração de dados e schema

Existem duas migrações diferentes.

### 9.1 Migração do local dos arquivos

Versões antigas guardavam dados ao lado do executável. O fluxo atual move o uso para `%LOCALAPPDATA%\VersionFile`, mas faz isso por cópia:

1. se o banco já está no local novo, segue normalmente;
2. se há banco ao lado do executável antigo, copia e informa o usuário;
3. se nenhum banco foi encontrado, pergunta se é a primeira utilização ou permite localizar manualmente `versionfile.db`;
4. se o diálogo for fechado, o app encerra sem criar banco vazio.

Antes de copiar, o arquivo é validado pela presença das quatro tabelas esperadas. A cópia usa a API de backup do SQLite para incluir transações confirmadas ainda presentes no WAL, valida `PRAGMA integrity_check` e publica o snapshot sem sobrescrever um destino existente.

### 9.2 Migração do schema SQLite

A inicialização detecta schemas antigos pela ausência de:

- coluna `tipo` em `versoes`;
- coluna `descricao` em `projetos`;
- tipos `Regra`, `Webservice` ou `Relatório` no `CHECK` de projetos.
- tabela `portas` e coluna `porta_id` em `regras`.

Se há dados, um backup timestampado é criado antes da alteração. A migração reconstrói tabelas quando necessário, preserva descrições e dependentes, executa verificação de chaves estrangeiras e reverte tudo em caso de falha.

Regras antigas de Webservice são preservadas e associadas automaticamente a portas. Se mais de uma regra tiver sido agrupada na mesma porta por uma versão intermediária, a migração cria portas separadas para preservar cada conteúdo e impõe uma regra interna por porta. Não há tabela de número de migração; a necessidade é inferida inspecionando o schema.

## 10. Atualização automática

O atualizador consulta a release mais recente de `gustavonardello/VersionFile` no GitHub.

Fluxo:

1. compara a tag remota com `core.version.__version__`;
2. exige um asset cujo nome termina em `Setup.exe`;
3. exige o asset correspondente `<Setup.exe>.sha256`;
4. aceita downloads somente por HTTPS com host `github.com`;
5. baixa o checksum;
6. baixa o instalador em streaming para uma pasta temporária exclusiva;
7. valida tamanho, quando informado, e SHA-256;
8. inicia o Inno Setup destacado e silencioso;
9. fecha normalmente o aplicativo atual, passando pela proteção de autosave.

A checagem automática roda em thread para não travar a UI. Um resultado sem atualização é armazenado por uma hora. Quando uma atualização é encontrada, o cache é removido para que ela continue sendo oferecida nas próximas aberturas até ser instalada.

O menu `Ajuda > Verificar atualizações...` força uma nova consulta e mostra também falhas de rede de forma amigável.

## 11. Build, instalador e release

### Executável

O `VersionFile.spec` gera um pacote PyInstaller no modo `onedir`:

```powershell
pyinstaller --noconfirm VersionFile.spec
```

Saída principal:

```text
dist/VersionFile/VersionFile.exe
```

O spec inclui temas, ícone e logo. Não inclui banco nem configurações mutáveis.

### Instalador

`installer/VersionFile.iss` instala em `%LOCALAPPDATA%\Programs\VersionFile`, cria atalhos e pode fechar uma instância antiga com o Restart Manager. Ele nunca deve tocar `%LOCALAPPDATA%\VersionFile`.

Compilação manual:

```powershell
ISCC installer\VersionFile.iss /DAppVersion=1.2.4
```

### CI/CD

`.github/workflows/release.yml` roda em Windows quando uma tag `v*` é enviada ou por disparo manual.

O pipeline:

1. prepara Python 3.11;
2. exige que a tag corresponda a `core/version.py`;
3. instala dependências e PyInstaller 6.11.1;
4. roda a suíte de regressão com Qt offscreen;
5. gera o pacote PyInstaller;
6. instala Inno Setup;
7. compila o instalador;
8. verifica se os artefatos foram criados e têm tamanho plausível;
9. gera SHA-256;
10. publica instalador e checksum como artefatos;
11. em tags, anexa os arquivos a uma release existente ou cria uma release em rascunho.

`core/version.py`, a tag e a versão do instalador precisam permanecer sincronizados.

## 12. Testes e validação

### Instalação das dependências

```powershell
py -3.11 -m pip install -r requirements.txt
```

Dependências de runtime:

- `PyQt6 >= 6.6.0`
- `PyQt6-QScintilla >= 2.14.0`

### Executar o aplicativo em desenvolvimento

```powershell
py -3.11 main.py
```

O executável em `dist` não reflete mudanças recentes no código até um novo build.

### Suíte de regressão

```powershell
py -3.11 -m unittest discover -s tests -v
```

São 52 testes no estado atual deste projeto. Eles cobrem, entre outros:

- persistência e validação de clientes;
- rollback e atomicidade;
- cascatas e invariantes de versão;
- migração de schema e snapshot com WAL;
- hierarquia de portas e migração de Webservices legados;
- importação e exportação;
- nomes válidos no Windows;
- busca Unicode literal;
- autosave e proteção em falhas;
- seleção da árvore e histórico;
- inicialização da janela;
- temas inválidos;
- diff e quebra final de linha;
- cache, checksum e origem do atualizador.

### Smoke test visual isolado

```powershell
py -3.11 scripts/validar_interface.py
```

Esse script abre a UI offscreen com banco temporário, exercita cadastro e duplicidade e grava capturas em `auditoria/capturas/`.

### Smoke test do pacote

Após o build:

```powershell
dist\VersionFile\VersionFile.exe --smoke-test
```

### Scripts que afetam o ambiente real

Os scripts abaixo instalam/desinstalam versões, encerram processos ou usam os dados do usuário atual:

- `scripts/testar_instalador.ps1`
- `scripts/testar_auto_update.ps1`
- `scripts/capturar_processos.ps1`

Eles devem ser executados somente em usuário ou VM de teste e exigem explicitamente `-ConfirmarAmbienteReal`. Não devem ser executados como parte de uma validação comum.

`scripts/testar_updater.py` consulta o repositório real do GitHub e, portanto, depende de rede e do estado atual das releases.

## 13. Mapa rápido de arquivos

```text
main.py                         bootstrap e ciclo de vida do app
requirements.txt               dependências Python
core/version.py                versão atual
core/paths.py                  caminhos de recursos e dados
core/version_manager.py        classificação e diff de versões
core/highlighter.py            lexer LSP e temas
core/importer.py               leitura/importação de pastas
core/exporter.py               nomes seguros e escrita exclusiva
core/migration.py              migração segura de dados antigos
core/updater.py                consulta, download e instalação de update
database/db.py                 schema, conexão, backup e migração
database/models.py             dataclasses, portas, CRUD e transações
ui/main_window.py              janela, menus e workers de update
ui/tree_panel.py               navegação, ações visuais, busca e CRUD hierárquico
ui/editor_panel.py             edição, autosave e ações de versões
ui/dialogs.py                  formulários de entidades e versões
ui/diff_viewer.py              comparação lado a lado
ui/version_history.py          histórico visual
ui/import_dialog.py            preview e importação em thread
ui/export_dialog.py            exportação em lote
ui/migracao_dialog.py          localização/migração na primeira execução
ui/theme_color_dialog.py       personalização do editor
config/themes.json             paleta padrão distribuída
tests/test_regressoes.py       suíte automatizada
scripts/validar_interface.py   validação visual isolada
VersionFile.spec               build PyInstaller
installer/VersionFile.iss      instalador Inno Setup
.github/workflows/release.yml  pipeline de build e release
auditoria/revisao.md           revisão técnica de 11/09/2026
```

`build/` e `dist/` são artefatos gerados. Não devem ser editados manualmente.

## 14. Convenções de código

- Código, comentários e textos da interface em português do Brasil.
- Arquivos e funções em `snake_case`; classes em `PascalCase`.
- Imports absolutos a partir da raiz do projeto.
- Dataclasses e funções CRUD permanecem juntas em `database/models.py`.
- A conexão é o primeiro argumento das funções do modelo.
- Sinais PyQt são definidos na classe emissora e normalmente conectados pelo componente pai.
- Falhas recuperáveis em callbacks de UI devem virar mensagens contextuais, usando `ui.errors.mostrar_erro` quando aplicável.
- Mudanças devem ser incrementais; evitar reescritas amplas sem necessidade.
- Não há linter ou formatador configurado. A suíte inclui pelo menos validação sintática de todos os módulos Python.

## 15. Restrições e cuidados para alterações futuras

Antes de alterar o projeto, considerar estas invariantes:

1. Não apagar, recriar ou sobrescrever `versionfile.db`.
2. Não usar o banco real em testes automatizados.
3. Não permitir que instalação/desinstalação toque a pasta de dados.
4. Não remover transações/savepoints de operações compostas.
5. Não permitir que troca de seleção ou fechamento descarte texto pendente.
6. Não criar regra sem primeira versão no fluxo normal da interface.
7. Não permitir excluir a única versão de uma regra.
8. Não marcar como atual uma versão de outra regra.
9. Workers com SQLite devem abrir sua própria conexão dentro da thread.
10. Exportações devem continuar confinadas ao destino e sem sobrescrita.
11. Migrações devem manter origem intacta, backup e rollback.
12. O atualizador deve exigir HTTPS, GitHub e checksum SHA-256.
13. Não editar manualmente `build/` ou `dist/`.
14. Não modificar `VersionFile.spec`, `.gitignore` ou `config/tree_state.json` sem uma necessidade explícita e confirmação.
15. `config/themes.json` deve ser alterado apenas para ajustes ou novas paletas.

Depois de mudanças em lógica, banco ou UI, executar a suíte de regressão. Para UI, executar também a validação visual e inspecionar as capturas. Para mudanças de pacote, executar o smoke test do executável reconstruído.

## 16. Estado de trabalho observado em 12/09/2026

No momento em que este documento foi criado:

- o código declara a versão `1.2.4`;
- a suíte desta sessão passou antes da validação final com 51 testes e passou a conter 52 após adicionar o cenário de migração legada;
- a validação visual retornou `OK`;
- os ajustes em andamento incluem a barra visual da árvore, rótulos dinâmicos e a porta como item diretamente editável dos Webservices;
- `.claude/` e `auditoria/capturas/` aparecem como itens não rastreados;
- essas alterações preexistentes pertencem ao usuário e não devem ser descartadas.

Este estado pode ficar desatualizado. Em toda nova sessão, executar `git status --short` antes de editar e tratar este bloco apenas como histórico, não como substituto do estado atual do Git.

## 17. Roteiro recomendado para uma nova sessão

1. Ler este `contexto.md`.
2. Ler `git status --short` e preservar alterações existentes.
3. Localizar os arquivos diretamente relacionados ao pedido.
4. Confirmar no código as invariantes relevantes; este documento pode ficar defasado.
5. Implementar uma alteração por vez.
6. Rodar os testes proporcionais ao risco.
7. Se houver UI, abrir com `py -3.11 main.py` para revisão manual e rodar `scripts/validar_interface.py` quando o fluxo coberto for relevante.
8. Relatar arquivos alterados, validações executadas e qualquer risco ou pendência.

## 18. Intenção de manutenção deste documento

Este arquivo explica o contexto, mas o código continua sendo a fonte de verdade. Ele deve ser atualizado quando houver mudanças relevantes em:

- propósito ou escopo do produto;
- arquitetura;
- schema ou invariantes do banco;
- fluxos de edição/versionamento;
- caminhos de dados;
- atualização e segurança;
- build/release;
- comandos e estratégia de testes.

Preferências efêmeras, detalhes puramente visuais e o estado momentâneo do Git não precisam ser promovidos às seções permanentes, salvo quando ajudam a preservar trabalho em andamento.
