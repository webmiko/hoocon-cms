# Hoocon Manager — мобильный дизайн (v1 internal)

Внутреннее Flutter-приложение для роли **Менеджер**. Не копия Unfold Admin.

## Бренд

| Токен | Значение |
|-------|----------|
| `--color-bg` | `#F4F5F6` |
| `--color-surface` | `#FFFFFF` |
| `--color-ink` | `#1A1D21` |
| `--color-muted` | `#5A626C` |
| `--color-primary` | `#3D4650` (промышленный серый) |
| `--color-accent` | `#C45C26` (терракота CTA, умеренно) |
| `--color-ok` | `#2F6B4F` |
| `--color-warn` | `#B45309` |
| `--radius` | 12 dp |
| `--tap-min` | 48 dp |

Шрифт: системный (`Roboto` / SF на iOS). Без Inter/фиолетовых градиентов.

## Навигация

Bottom bar (4 пункта):

1. **Заявки** — список + detail  
2. **Чат** — inbox поддержки  
3. **Клиенты** — CRM  
4. **Ещё** — профиль, выход, статус push  

Бейджи на «Заявки» и «Чат» из `GET /api/staff/badges/`.

## Экраны

### 1. Вход
- Поле email / логин  
- CTA «Получить код»  
- Экран OTP: 6 цифр, resend, ошибка  
- После verify — сохранение token в secure storage  

### 2. Заявки (list)
- Карточки на всю ширину: статус chip, имя/компания, канал, время  
- Фильтр: Новые / В работе / Все (scoped)  
- Pull-to-refresh + polling badges 12 с  

### 3. Заявка (detail)
- Один столбец: контакты, текст, SKU-строки  
- Sticky CTA: «Взять в работу» / «Завершить»  
- Ссылка на клиента → CRM  

### 4. Клиенты
- Поиск по email/имени  
- Карточка: контакты, активности, «Написать письмо» (subject + body)  

### 5. Чат
- Список диалогов (unread badge)  
- Тред: poll `?after=`, поле ответа, assign себе  

### 6. Ещё / профиль
- Имя, email, группы  
- Push on/off (FCM register)  
- Выход  

## Deep links

- `hoocon-manager://lead/{id}`  
- `hoocon-manager://conversation/{id}`  

## Offline-lite

Кэш последнего списка в памяти/local; баннер «Нет сети» без скрытой порчи данных.

## Дистрибуция

Только internal APK (App Distribution / файл). Сторы вне скоупа.
