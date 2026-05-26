# CLAUDE.md

## Commands
```
pip install -r requirements.txt   # instala dependências (PyQt6, QScintilla)
python main.py                    # inicia a aplicação desktop
pyinstaller VersionFile.spec      # gera executável em dist/VersionFile.exe
```
Não há test runner, linter ou formatter configurados no projeto.
Validação manual: `python main.py` deve subir sem erros de import.
Inspecione visualmente a funcionalidade afetada antes de marcar como concluído.

## Architecture
App desktop Python com PyQt6 (UI) + QScintilla (widget de editor); syntax highlighting
implementado em `core/highlighter.py` sobre a API do QScintilla — não é um servidor LSP externo.
Banco de dados SQLite acessado via `sqlite3` puro — sem ORM. A conexão é criada em `main.py` e
passada explicitamente via construtor para todos os widgets e funções de modelo.
Camadas: `ui/` (widgets PyQt6), `core/` (lógica de negócio), `database/` (modelos + SQL raw).
A hierarquia de dados é: Cliente → Projeto → Regra → Versão.
Build para distribuição feito com PyInstaller; `core/paths.py` separa `base_path()` (recursos)
de `data_path()` (dados do usuário, ao lado do .exe).

## Project structure
```
main.py          # ponto de entrada: bootstrap, inicializa DB, cria QApplication e MainWindow
core/            # lógica pura sem UI: version_manager, highlighter, importer, paths
database/        # db.py (inicialização/conexão SQLite), models.py (dataclasses + CRUD raw SQL)
ui/              # widgets PyQt6: main_window, tree_panel, editor_panel, dialogs, diff_viewer…
config/          # themes.json (paletas de cor), tree_state.json, ui_prefs.json (gerado em runtime)
dist/            # saída do PyInstaller — não editar manualmente
build/           # artefatos intermediários do PyInstaller — ignorar
```

## Key design decisions
- Edição de metadados de versão (tipo, status, notas) é feita exclusivamente via `DialogEditarVersao` — o painel lateral exibe notas em modo somente leitura.
- `atualizar_meta_versao` em `models.py` salva tipo+status+notas juntos; `atualizar_versao` (legado) salva só status+notas — prefira o novo.
- `config/ui_prefs.json` persiste preferências de UI (ex: `bg_mode`); gerado automaticamente via `data_path()`; não incluído no `.spec`.
- Preferência de fundo do editor é carregada no `__init__` do `EditorPanel` e re-aplicada após `_setup_editor()` (que sempre inicia em modo escuro).

## Code conventions
- Arquivos e módulos em `snake_case.py`; classes em `PascalCase`; sem barrel files nem aliases de import.
- Imports entre pacotes são absolutos a partir da raiz (`from database.models import …`, `from core.paths import …`).
- Modelos de dados são `@dataclass` em `database/models.py`; cada entidade tem suas funções CRUD no mesmo arquivo.
- A conexão SQLite (`conn`) é passada como primeiro argumento em todas as funções de modelo — nunca global.
- Widgets não acessam o banco diretamente; recebem dados via construtor ou sinal. Toda escrita no DB passa pelas funções em `database/models.py`.
- Todo o código, comentários e strings da UI estão em português (pt-BR). Mantenha o padrão.
- Erros são propagados como exceções Python padrão; não há tipo `Result` nem tratamento global centralizado.
- Sinais PyQt6 (`pyqtSignal`) são definidos na classe que emite; conexões feitas no pai (ex.: `MainWindow`).

## Claude behavior
- Antes de criar um arquivo, verifique se já existe algo com função similar.
- Faça mudanças incrementais: um problema por vez, não reescritas completas.
- Após qualquer mudança, verifique manualmente se `python main.py` ainda sobe sem erros de import.
- Se travar por mais de 2 tentativas no mesmo problema, pare e explique o bloqueio.
- Nunca modifique `.gitignore`, arquivos em `dist/` ou `build/`, o spec do PyInstaller, ou `config/tree_state.json` sem perguntar antes.
- `config/themes.json` pode ser editado apenas para adicionar ou ajustar paletas de cor.
- Quando houver múltiplas abordagens válidas, liste-as brevemente antes de escolher.