# VersionFile

Gerenciador de regras LSP com versionamento, desenvolvido para facilitar o controle de versões de regras da plataforma Senior.

## Funcionalidades

- Organização hierárquica: **Cliente → Projeto/DID → Regra → Versões**
- Editor com **syntax highlight** para LSP (Linguagem Senior de Programação)
- **Versionamento inteligente** com detecção automática do tipo de alteração (Criação, Correção, Melhoria, Refatoração)
- **Diff visual** lado a lado entre versões
- **Busca** por número de regra ou por conteúdo
- Importação de estrutura de pastas existente
- Exportação de regras individuais ou em lote
- Temas de editor: **Senior (padrão)** e **Escuro**

## Requisitos

- Python 3.11+
- Dependências listadas em `requirements.txt`

## Instalação (modo desenvolvedor)

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/VersionFile.git
cd VersionFile

# Instale as dependências
pip install -r requirements.txt

# Execute
python main.py
```

## Download (executável)

Acesse a aba [Releases](../../releases) para baixar o instalador `.exe` — não requer Python instalado.

## Estrutura do projeto

```
main.py              # Entry point
database/            # Banco SQLite e modelos
ui/                  # Interface gráfica (PyQt6)
core/                # Lógica de highlight, versionamento e importação
config/              # Temas do editor
```

## Tecnologias

- [Python 3.11](https://python.org)
- [PyQt6](https://pypi.org/project/PyQt6/)
- [QScintilla](https://pypi.org/project/PyQt6-QScintilla/)
- SQLite

## Licença

MIT — veja [LICENSE](LICENSE).
