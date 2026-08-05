# Расходный диск Kvs — фото для галереи 8100

Круглое **фото отверстия** как есть + белый фон + надписи (как у старых SVG).

| Путь | Назначение |
|------|------------|
| `src/dn{DN}-{letter}.png` | исходник (круговой кроп порта) |
| `dn{DN}-{letter}.webp` | тайл для ProductImage |

Как добавить издание::

1. Положи круглое фото в `src/` (имя `dn15-b.png`, `dn20-a.jpg`, …).
2. Пересобери и повесь::

```bash
poetry run python -m catalog.etl.generate_kvs_disc_schematics
poetry run python manage.py attach_ball_valve_kvs_discs
```

Герой DN не трогаем (`sort_order=30`). Без файла в `src/` тайл не пересобирается.
