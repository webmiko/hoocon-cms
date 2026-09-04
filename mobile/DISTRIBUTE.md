# Внутренняя раздача Hoocon Manager

Сторы **не** используются.

## Backend (прод / стейдж)

```bash
# .env
STAFF_API_ENABLED=true
FCM_SERVER_KEY=...   # Legacy server key из Firebase Console → Cloud Messaging
                     # без ключа API работает; FCM push = no-op

poetry run python manage.py migrate staff_api
# recreate web + celery after .env change
```

## Стикеры и push в приложении

| Что | Как работает сейчас |
|-----|---------------------|
| Стикеры на «Заявки» / «Чат» | `GET /api/staff/badges/` каждые 12 с |
| Локальный алерт | При росте счётчика, пока приложение открыто |
| FCM (фон / убитое приложение) | Нужны реальный `google-services.json` + `FCM_SERVER_KEY` |

### Firebase (один раз)

1. Firebase Console → проект → Add Android app  
   package: `ru.hoocon.hoocon_manager`
2. Скачать `google-services.json` → заменить  
   `mobile/hoocon_manager/android/app/google-services.json`
3. Cloud Messaging → **Cloud Messaging API (Legacy)** → Server key  
   → в `.env` на VPS: `FCM_SERVER_KEY=…`
4. Пересобрать APK, на устройстве: **Ещё → Push-уведомления**

Пока стоит placeholder JSON — стикеры и локальные алерты работают,
FCM-токен не выдаётся.

## APK

```bash
cd mobile/hoocon_manager
flutter build apk --release \
  --dart-define=API_BASE=https://hoocon.ru/api/staff
```

Файл: `build/app/outputs/flutter-apk/app-release.apk`  
Копия: `mobile/dist/hoocon-manager-0.1.2.apk` (v0.1.2+3).

В этой сборке: OTP на одном экране, стикеры внизу, локальные push-алерты,
чат без «Сайт» в заголовке.

Варианты раздачи:

1. Firebase App Distribution (тестеры по email)
2. Прямая ссылка / мессенджер + «установка из неизвестных источников»

## Подпись

Debug-подпись годится только для своих устройств. Для команды —
создать keystore (`key.properties` вне git) и собрать release.

## iOS (внутренняя раздача, без App Store)

Нужен полный **Xcode** (у нас: `/Applications/Xcode-beta.app`) и Apple ID
в Xcode (бесплатного хватает для своего iPhone; Ad Hoc / TestFlight —
с платной командой).

```bash
# один раз
sudo xcode-select --switch /Applications/Xcode-beta.app/Contents/Developer

export PATH="$HOME/flutter-sdk/bin:$PATH"
cd mobile/hoocon_manager

flutter build ipa --release \
  --dart-define=API_BASE=https://hoocon.ru/api/staff

# или сразу на телефон:
flutter run --release -d <device-id> \
  --dart-define=API_BASE=https://hoocon.ru/api/staff
```

Push (FCM) потребует `GoogleService-Info.plist` + APNs в Firebase —
без этого стикеры работают, фоновых push нет.

## Проверка API

```bash
curl -s -X POST https://hoocon.ru/api/staff/auth/otp/start/ \
  -H 'Content-Type: application/json' \
  -d '{"login":"manager@hoocon.ru"}'
```
