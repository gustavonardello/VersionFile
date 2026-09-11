# VersionFile

Gerenciador de regras LSP com versionamento completo, desenvolvido para facilitar o controle de versões de regras da plataforma Senior.

## Funcionalidades

### Organização hierárquica
Estrutura em árvore: **Cliente → Projeto/DID → Regra → Versões**

Tipos de projeto suportados: `DID`, `Projeto`, `Regra`, `Webservice`, `Relatório`

Para projetos do tipo Relatório, a regra segue a estrutura de seções do gerador (Título, Cabeçalho, Detalhe, Total Geral, etc.).

### Editor
- Syntax highlight para LSP (Linguagem Senior de Programação) — palavras-chave, funções, tipos, strings, comentários
- Alternância de fundo **preto / branco** com preferência salva entre sessões
- Autosave ao perder foco ou após 1 segundo de inatividade

### Versionamento
- Detecção automática do tipo de alteração: **Criação**, **Correção**, **Melhoria**, **Refatoração**
- Navegação entre versões com setas `‹ ›` ou combo direto
- Indicador de versão: `N de Total · Tipo (Atual)`
- Edição de metadados da versão (tipo, status, notas) via diálogo dedicado
- Notas exibidas em modo leitura no painel lateral

Status de versão: `Em desenvolvimento`, `Em teste`, `Produção`, `Depreciada`

### Diff visual
- Comparação lado a lado entre quaisquer duas versões
- Cores por tipo de alteração: removido, adicionado, alterado, sem mudança
- Scroll sincronizado entre os painéis
- Alternância de fundo preto / branco
- Estatísticas de linhas removidas, adicionadas e alteradas

### Importação e exportação
- Importação de estrutura de pastas existente (`.lsp` / `.txt`)
- Suporte simultâneo a arquivos na raiz e estruturas de 2 ou 3 níveis
- Exportação de regra individual (`.lsp`)
- Exportação em lote de múltiplas regras via `Arquivo → Exportar múltiplas regras`
- Nomes inválidos são normalizados e arquivos existentes não são sobrescritos

### Configuração
- Importação disponível em `Arquivo → Importar estrutura de pastas`
- Personalização das cores em `Configurações → Personalizar cores do editor`
- Recuperação automática com tema padrão quando a configuração estiver inválida

### Histórico
- Visualização de todas as versões com cards detalhados
- Carregamento ou exclusão de versões específicas pelo histórico

## Requisitos

- Python 3.11+
- Dependências: `PyQt6 >= 6.6.0`, `PyQt6-QScintilla >= 2.14.0`

## Instalação (modo desenvolvedor)

```bash
pip install -r requirements.txt
py -3.11 main.py
```

## Testes

```bash
py -3.11 -m unittest discover -s tests -v
py -3.11 scripts/validar_interface.py
```

Depois de empacotar, `dist/VersionFile/VersionFile.exe --smoke-test` abre a
interface sem consultar atualizações e encerra automaticamente.

## Build do executável

```bash
pyinstaller VersionFile.spec
# Saída: dist/VersionFile/VersionFile.exe
```

O instalador publicado inclui um arquivo `.sha256`; o atualizador exige e
confere esse checksum antes de executar uma nova versão.

## Download

Acesse a aba [Releases](../../releases) para baixar o `.exe` — não requer Python instalado.

## Estrutura do projeto

```
main.py              # Ponto de entrada: bootstrap, DB, QApplication
database/
  db.py              # Inicialização e conexão SQLite
  models.py          # Dataclasses (Cliente, Projeto, Regra, Versão) + CRUD raw SQL
core/
  highlighter.py     # Lexer LSP para QScintilla
  version_manager.py # Lógica de diff e detecção de tipo
  importer.py        # Importação de estrutura de pastas
  paths.py           # base_path() / data_path() para compatibilidade com .exe
ui/
  main_window.py     # Janela principal com TreePanel + EditorPanel
  tree_panel.py      # Árvore hierárquica Cliente→Projeto→Regra
  editor_panel.py    # Editor + painel lateral de versões
  diff_viewer.py     # Comparação lado a lado entre versões
  version_history.py # Histórico completo de versões em cards
  dialogs.py         # Diálogos de criação/edição (Cliente, Projeto, Regra, Versão)
  export_dialog.py   # Exportação em lote
  import_dialog.py   # Importação de estrutura
config/
  themes.json        # Paletas de cor do editor
  ui_prefs.json      # Preferências de UI (gerado automaticamente)
```

## Tecnologias

- [Python 3.11](https://python.org)
- [PyQt6](https://pypi.org/project/PyQt6/) — interface gráfica
- [QScintilla](https://pypi.org/project/PyQt6-QScintilla/) — editor de código com syntax highlight
- SQLite — banco de dados local via `sqlite3` puro

## Licença

MIT — veja [LICENSE](LICENSE).
