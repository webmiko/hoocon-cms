# Hoocon Manager (Flutter) — внутренняя сборка

Мобильное приложение менеджера: заявки, CRM, чат поддержки, FCM.

Дизайн: [../DESIGN.md](../DESIGN.md) · API: [../API.md](../API.md)

## Требования

- Flutter 3.8+
- Backend: `STAFF_API_ENABLED=true`, миграции `staff_api`
- Для push: `FCM_SERVER_KEY` на сервере + `google-services.json` в `android/app/`

## Запуск

```bash
export PATH="$HOME/flutter-sdk/bin:$PATH"   # или ваш Flutter
cd mobile/hoocon_manager
flutter pub get
flutter run --dart-define=API_BASE=https://hoocon.ru/api/staff
# локально:
# flutter run --dart-define=API_BASE=http://10.0.2.2:8000/api/staff
```

## Internal APK (без сторов)

```bash
flutter build apk --release --dart-define=API_BASE=https://hoocon.ru/api/staff
# артефакт: build/app/outputs/flutter-apk/app-release.apk
```

Раздача: Firebase App Distribution или файл менеджерам. На устройстве —
разрешить установку из неизвестных источников.

## Deep links

- `hoocon-manager://lead/{id}`
- `hoocon-manager://conversation/{id}`

(настройка intent-filter — при подключении Firebase / релизной подписи)
