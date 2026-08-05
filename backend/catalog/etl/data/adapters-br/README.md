# Адаптеры BR-M / BR-ML — локальные фото

| Файл | Назначение |
|------|------------|
| `br-*-nobg-source.png` | cut-out без фона (приоритет) |
| `br-*-source.jpg` | запасной JPEG с белым фоном |
| `br-*.webp` | предпросмотр после обработки |

`manage.py ensure_br_adapters` берёт `*-nobg-source.png` → upscale ~1600px,
WebP **q55** с альфой → `ProductImage` media (без hotlink).
