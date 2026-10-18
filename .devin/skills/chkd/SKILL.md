---
name: chkd
description: Команда «чкд» — pre-commit checkup, атомарный коммит, push develop, ensure release PR. Отдельно «PR на прод / деплой / сведи в main» — merge release PR в main. Вызывать при словах чкд, коммит, пуш, деплой, выкатываем, сведи в main.
---

# чкд — checkup · коммит · release PR

Прочитай и выполняй канон по шагам:

- `.cursor/rules/chkd-checkup-commit-deploy.mdc` — порядок «чкд» и
  отдельная команда выката на прод (merge всего release PR).
- `.cursor/rules/atomic-commits.mdc` — одна узкая обратимая тема = один
  коммит; прошедшее время в сообщении; бамп версии отдельным коммитом.
- `.cursor/rules/develop-main.mdc` — работа на develop; прямой push в main
  и merge в обход PR запрещены.
- `.cursor/rules/release-version.mdc` — patch/minor/major: когда поднимать;
  minor только после явного согласия в разговоре; бамп отдельным коммитом.

Ключевое:

1. `./scripts/pre-commit-checkup.sh` до коммита; красный → не коммитить.
2. Коммит — только по явной просьбе пользователя.
3. Diff на границе доверия → сначала скилл `trust-boundary`.
4. «чкд» по умолчанию без merge в main; merge — только по явной просьбе.
