# Схема направления потока — 3-ходовые 8100

Полностраничная схема (4 состояния монтажа × крайние 0° / 90°) для галереи
только **BV3xx**. Текст той же логики — в `Product.instructions`
(`THREE_WAY_FLOW_INSTRUCTIONS`).

| Путь | Назначение |
|------|------------|
| `flow-3way.webp` | тайл ProductImage (`sort_order=25`) |

```bash
poetry run python -m catalog.etl.generate_ball_valve_flow_scheme
poetry run python manage.py attach_ball_valve_flow_scheme
```
