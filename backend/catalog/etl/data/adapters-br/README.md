# Адаптеры BR-M / BR-ML — локальные фото

| Файл | Назначение |
|------|------------|
| `br-*-nobg-source.png` | cut-out без фона (приоритет) |
| `br-*-source.jpg` | запасной JPEG с белым фоном |
| `br-*.webp` | предпросмотр после обработки |
| `tech-zh/*.png` | OEM-чертежи (CN) → RU PDF через `br_adapter_tech_sheets` |

`manage.py ensure_br_adapters` берёт `*-nobg-source.png` → upscale ~1600px,
WebP **q55** с альфой → `ProductImage` media (без hotlink).

Технички RU: `python -m catalog.etl.br_adapter_tech_sheets`, затем
`manage.py attach_manual_pdfs --series br`.
