# База знаний GigaChat — один файл

Бот отвечает **только** по файлу `gigachat_kb.txt`. На проде нет `_manuals-ru`
и `_инструкции-pdf` — всё упаковано в ветки `@BRANCH` и коммитится в git.

## Формат (v2)

```text
@META version=2 built_at=... branches=120

@BRANCH BEGIN id=policy.bot tags=_always,policy,овк
@TITLE Политика ответов бота
Правила…
@BRANCH END

@BRANCH BEGIN id=manual.html.da2mu-d-ds tags=manual,da,mu tokens=da2mu,da2mu24
@TITLE _manuals-ru/DA/da2mu-d-ds.html — …
@GOTO da2mu → manual.html.da2mu-d-ds
– Крутящий момент: 2 Нм
…
@BRANCH END

@BRANCH BEGIN id=nav.index tags=_index,навигация
@GOTO da2mu → manual.html.da2mu-d-ds
…
@BRANCH END
```

- `@BRANCH` — изолированный блок фактов
- `tags` / `tokens` / `series` — умный поиск по вопросу клиента
- `@GOTO` — подсказка «токен → id ветки»
- `policy.bot` — всегда в контексте; нет факта → `[ESCALATE]`

Рантайм **не** читает БД — только этот файл (актуальность = пересборка).

## Пересборка (локально)

```bash
./scripts/build-gigachat-kb.sh
```

```bash
cd backend && poetry run python manage.py build_gigachat_kb
```

Только мануалы:

```bash
cd backend && poetry run python manage.py build_gigachat_kb --no-site
```

После изменений CMS, FAQ или мануалов — пересобрать и закоммитить TXT.
