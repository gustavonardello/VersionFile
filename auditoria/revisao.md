# Revisão técnica — VersionFile

Data: 11/09/2026. Aplicação desktop Python/PyQt6/QScintilla com SQLite local.

O erro informado, `UNIQUE constraint failed: clientes.nome`, ocorre quando o cadastro tenta inserir um nome que já existe. A restrição de unicidade está funcionando; faltava tratar a situação de forma adequada na interface. O fluxo corrigido informa a duplicidade em português, mantém o nome preenchido e permite corrigi-lo. Renomear um cliente também trata duplicidade. Não foi removida a restrição nem apagado qualquer cliente.

**Escopo da leitura**

Foram lidos integralmente os arquivos de aplicação em `database/`, `core/`, `ui/` e `main.py`, incluindo SQL, callbacks da interface, importação, exportação, versionamento, migrações, temas e atualizador. Também foram inspecionados `config/themes.json`, `requirements.txt`, `VersionFile.spec`, `installer/VersionFile.iss`, `.github/workflows/release.yml`, README e scripts de diagnóstico/teste. Os binários e artefatos gerados em `build/` e `dist/` não foram auditados internamente nem recompilados.

O banco `versionfile.db` do projeto foi aberto somente para leitura de estrutura e integridade: `PRAGMA integrity_check` retornou `ok`. Esse resultado se aplica ao banco do projeto, não comprova o estado de outro banco utilizado pelo executável instalado. Os cenários de escrita usaram exclusivamente bancos temporários.

**Falhas corrigidas e evidência**

| Prioridade | Local | Problema anterior | Resultado da correção |
|---|---|---|---|
| Alta | `ui/tree_panel.py`, `ui/dialogs.py` | Cadastro duplicado exibia SQL bruto; renomear duplicado podia gerar exceção sem tratamento. | Mensagem compreensível, nova tentativa com nome preservado, edição com nome atual preenchido e bloqueio do OK para nome vazio. Testado por unidade e por diálogos reais offscreen. |
| Alta | `database/models.py` | Escritas não tinham rollback explícito; falhas podiam manter transação aberta e alterações intermediárias. | Todas as mutações usam savepoints. Operações podem ser compostas e revertidas integralmente. Testes de duplicidade, transação composta e falha por trigger. |
| Alta | `database/models.py` | Criar versão desmarcava a atual antes de uma inserção que poderia falhar. Marcar atual aceitava versão de outra regra. | Rollback preserva a versão atual e a relação versão/regra é validada. |
| Alta | `database/db.py` | Reconstrução da tabela de projetos podia perder `descricao`; falhas podiam deixar migração parcial ou chaves estrangeiras desativadas. A detecção não considerava isoladamente a falta de `Relatório`. | Migração transacional, preservação de descrição e dependentes, verificação de referências e restauração do PRAGMA em `finally`. Backup mantém o comportamento anterior e recebe carimbo com microssegundos. |
| Alta | `core/migration.py` | Copiar apenas o arquivo `.db` podia omitir dados confirmados ainda no WAL de um banco aberto. | Snapshot via API de backup SQLite, validação de integridade e publicação sem sobrescrever banco existente. Testado com WAL ativo. |
| Alta | `ui/editor_panel.py` | Autosave reconstruía o combo e retornava à versão marcada como atual; apagava o histórico de desfazer do editor. | Salva e atualiza o conteúdo em memória sem substituir o documento nem mudar a versão selecionada. Testado com digitação e undo. |
| Alta | `ui/editor_panel.py`, `ui/main_window.py` | Trocas de versão/seleção podiam cancelar edição pendente; falha de salvamento não protegia o fechamento. | Salva antes da navegação. Falha mantém o texto, permite nova tentativa e impede troca de versão e fechamento. Testado com falha simulada de banco bloqueado. |
| Alta | `ui/editor_panel.py` | Abrir regra sem versões deixava referência ao documento anterior. Carregar pelo histórico podia usar índices desatualizados e depois retornar à versão atual. | Documento vazio limpo; histórico carregado por ID com seleção preservada após fechar o diálogo. |
| Alta | `ui/import_dialog.py` | Worker usava conexão SQLite criada na thread da interface. | Conexão própria aberta e fechada na thread, usando o mesmo caminho do banco em modo `rw`. Testado executando a thread. |
| Alta | `core/importer.py`, `ui/tree_panel.py` | Importar arquivo ilegível podia deixar regra vazia; criar regra e primeira versão eram duas operações independentes. | Importação inteira e criação de regra com primeira versão são atômicas. Falha de leitura reverte o lote. |
| Alta | `core/exporter.py`, `ui/export_dialog.py` | Números de seção como `Titulo / Antes de Imprimir` geravam caminhos inválidos; nomes de clientes/projetos entravam diretamente no caminho. Arquivos com o mesmo destino eram sobrescritos. | Sanitização de todos os componentes, verificação de permanência no destino e gravação exclusiva, com sufixos numerados para colisões. |
| Média | `ui/import_dialog.py` | Falha ao escanear mantinha seleção antiga; tipo padrão escolhido era ignorado; fechar o diálogo podia destruir worker ativo. | Limpa seleção antes de escanear, aplica tipo padrão sobre cópia dos itens e bloqueia fechamento durante o trabalho. |
| Média | `ui/tree_panel.py` | Recarregar limpava seleção silenciosamente; editor podia continuar ligado a item excluído; exceção podia deixar sinais bloqueados. | Restaura seleção de regra, reaplica filtro, emite desmarcação quando necessário e restaura sinais em `finally`. |
| Média | `database/models.py` | Exclusão e promoção da versão restante dependiam de chamadas separadas feitas pela UI. | Exclusão e promoção são atômicas no modelo; exclusão da única versão é rejeitada. |
| Média | `ui/export_dialog.py` | Cliente aparecia desmarcado quando um projeto filho estava parcialmente selecionado. | Estado parcial propagado corretamente. |
| Média | `core/version_manager.py` | Importação individual substituía caracteres de arquivos não UTF-8 por caracteres de reposição. | Usa o mesmo fallback latin-1 do importador; teste com `ação`. |
| Média | `ui/main_window.py`, `main.py`, `database/db.py` | Encerramento podia destruir threads ativas; context manager SQLite não fechava a conexão de inicialização. | Aguarda workers de forma assíncrona e fecha conexões explicitamente. |

Os INSERTs passaram a recuperar o registro por `lastrowid` em vez de `RETURNING`. Trata-se de um ajuste das operações de persistência; **não era a causa da mensagem informada**. O cadastro original de um nome novo funcionou no Python/SQLite instalado.

**Pendências concluídas na versão 1.2.2**

Os itens que permaneceram abertos na primeira etapa também foram corrigidos e cobertos por testes quando automatizáveis.

| Prioridade | Local / ponto de entrada | Cenário anterior | Correção aplicada |
|---|---|---|---|
| Alta | `core/highlighter.py`, `ui/editor_panel.py` | Configurações inválidas podiam impedir a abertura. | Validação com paleta padrão interna, validação de preferências e backup `themes.invalid-*.json` ao substituir configuração inválida. |
| Alta | scripts de instalação/atualização | Podiam operar no usuário real sem confirmação; o teste de update omitia o clique manual necessário. | Exigem `-ConfirmarAmbienteReal`, orientam uso em VM/usuário de teste, aceitam versões por parâmetro e declaram a ação manual. |
| Alta | `core/updater.py`, `ui/main_window.py` | Uma consulta feita antes da publicação ocultava releases novas por 20 horas; o diálogo não tinha referência persistente nem consulta manual. | Cache reduzido a uma hora somente sem update, limpeza ao encontrar versão nova, diálogo persistente e ação `Ajuda > Verificar atualizações...` com retorno ao usuário. |
| Média | `ui/main_window.py` | Importação e cores não estavam acessíveis. | Ações adicionadas aos menus Arquivo e Configurações e testadas. |
| Baixa | `ui/main_window.py`, `core/version.py` | A versão em execução não aparecia na interface. | Barra de status mostra a versão no canto inferior direito a partir da fonte única usada pelo instalador e atualizador. |
| Média | `core/importer.py` | Estruturas mistas ignoravam arquivos. | Scanner agrega simultaneamente arquivos na raiz e hierarquias de dois e três níveis. |
| Média | `ui/tree_panel.py`, `core/text_utils.py` | Busca divergia com acentos e interpretava `%`/`_` como curingas. | Normalização Unicode uniforme e comparação literal em Python. |
| Média | `ui/diff_viewer.py` | Linhas excedentes e quebra final eram classificadas incorretamente. | Excedentes passam a ser adição/remoção e a quebra final recebe marcador próprio. |
| Média | callbacks de banco e arquivo | Algumas falhas ainda escapavam dos slots da interface. | Tratamento contextual adicionado em metadados, versão atual, exclusões e exportação individual. |
| Média | `core/updater.py` | Instalador temporário previsível e verificação apenas por tamanho. | Pasta exclusiva, origem HTTPS do GitHub e SHA-256 obrigatório antes da execução. |
| Média | `.github/workflows/release.yml` | Pipeline não testava antes do build. | Executa a suíte offscreen e publica instalador com seu `.sha256`. |
| Baixa | `ui/theme_color_dialog.py` | Exibia estilo inexistente e omitia estilos usados. | Opções alinhadas a função e constante do lexer. |
| Baixa | `README.md`, `CLAUDE.md` | Caminhos e comandos divergiam da aplicação atual. | Documentação atualizada para onedir, dados em LocalAppData, testes e regras de persistência/release. |

**Validação executada**

- Python 3.11, SQLite 3.45.1 e PyQt6 6.11.0 disponíveis no ambiente.
- `py -3.11 -m unittest discover -s tests -v`: **47 testes passaram** na rodada da conclusão das pendências. Inclui sintaxe, persistência, rollback, migração, temas, importação mista, busca Unicode literal, diff, exportação, checksum, cache e diálogo de atualização, navegação e falha de salvamento.
- `py -3.11 scripts/validar_interface.py`: executou `main.main()` com banco temporário, abriu cadastro, reproduziu duplicidade, verificou mensagem e preservação do nome, cadastrou outro nome e encerrou normalmente. Checagem de atualização substituída para não acessar rede.
- Capturas offscreen inspecionadas: [cadastro](capturas/01-cadastro.png), [aviso de duplicidade](capturas/02-duplicidade.png), [cliente cadastrado](capturas/03-cliente-cadastrado.png). Layout e texto do fluxo ficaram legíveis; o renderizador offscreen usa fontes diferentes do desktop nativo.
- O pacote PyInstaller foi reconstruído e `dist/VersionFile/VersionFile.exe --smoke-test` encerrou com código zero usando banco e pasta de dados temporários.
- `git diff --check`: sem erros de whitespace; Git apenas avisou sobre conversão futura de LF para CRLF.

**Limites e aplicação das mudanças**

A leitura cobre o código-fonte descrito, mas os testes exercitam cenários selecionados; não constituem cobertura de todos os ramos, teste de carga ou garantia de ausência de defeitos. Instalação, desinstalação e atualização real dependem do pipeline e de um ambiente isolado; por isso os scripts destrutivos não foram executados contra os dados do usuário. O snapshot usa hard link quando disponível e cópia exclusiva como fallback.

As correções compõem a versão 1.2.2. O executável instalado recebe as mudanças depois que o pipeline concluir e a release for publicada. Nenhum banco do usuário foi modificado durante a revisão.
