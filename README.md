# tutoring

Платформа репетитора по химии (ОГЭ/ЕГЭ): многоразовая библиотека теории и заданий по темам и сборка из неё материалов к занятиям — теории на слайдах, ДЗ, входной проверки и решений.

## Цели

По убыванию приоритета:

1. **Польза на занятиях** — готовиться к занятиям быстро и системно.
2. **Открытый инструмент** — в перспективе им смогут пользоваться другие преподаватели: сначала как кодом, который запускают у себя со своим содержанием, а затем, возможно, как веб-сервисом.

При конфликте целей сначала делаем то, что нужно к ближайшему занятию; технологию берём, только когда она решает настоящую проблему подготовки.

## Что не входит в проект

- Workflow для других областей (встречи, отчёты для клиентов) — отдельные проекты.

## Документация

- [`GLOSSARY.md`](GLOSSARY.md) — словарь предметной области.
- [`docs/adr/`](docs/adr/) — принятые архитектурные решения.

## Сборка PDF

Нужны Python 3.9+, Google Chrome (печатает HTML в PDF), `pdftoppm` из poppler (слайды теста в PNG) и интернет (формулы KaTeX и шрифт грузятся из сети). Путь к Chrome в `tools/build_kit.py` записан под macOS.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python tools/build_kit.py ../tutoring-content kits/oge/atom-structure-periodic-law-1/kit.md ../tutoring-content/build/atom-structure-periodic-law-1
.venv/bin/python tools/build_kit.py ../tutoring-content tests/level-test-9.md ../tutoring-content/build/level-test-9
```
