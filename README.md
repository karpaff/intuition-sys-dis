# «Интуиция»: персонажи. ML System Design

Учебный репозиторий (ITMO, ML System Design, ДЗ №1). Проект: фича «Персонажи» в читалке
[«Интуиция»](https://readintuition.ru) для художественных книг: автоматически собранные карточки героев,
которые растут по мере чтения (антиспойлер), вопросы о героях в чате и схема отношений.

## Структура

```
.
├── docs/
│   └── ml_system_design_doc.md   # design doc (шаблон Reliable ML)
├── src/intuition/                # код (появится в следующих ДЗ)
├── pyproject.toml                # настройки ruff
└── .pre-commit-config.yaml       # pre-commit хуки
```

## Быстрый старт

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
```

## Линтеры и форматирование

```bash
ruff check .          # линтер
ruff format .         # форматтер
pre-commit run -a     # все хуки на всех файлах
```

## Процесс работы

Каждое ДЗ оформляется отдельной веткой `hw_n` и Pull Request в `main`,
ревьюеры: ментор и кросс-ревьюеры.

## Документация

- [ML System Design Doc](docs/ml_system_design_doc.md)
