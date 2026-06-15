[app]

# Название приложения (отображается под иконкой)
title = Сканер билетов РЖД

# Имя пакета (только латиница, без пробелов)
package.name = rzdscanner
package.domain = ru.rzd.scanner

# Исходники
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,json

# Версия
version = 1.0

# Зависимости.
# kivy/kivymd — интерфейс; certifi — корневые сертификаты для HTTPS на Android.
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,certifi

# Ориентация — вертикальная (телефон)
orientation = portrait

# Полноэкранный режим выключен (видна строка состояния)
fullscreen = 0

# Иконка/заставка — по желанию положите свои файлы и раскомментируйте:
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png

# --- Android ---

# Разрешения: доступ в интернет + проверка состояния сети
android.permissions = android.permission.INTERNET, android.permission.ACCESS_NETWORK_STATE

# Версии API/NDK (значения по умолчанию — стабильные на 2025-2026)
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

# Принять лицензии Android SDK автоматически
android.accept_sdk_license = True

# Бэкенд оконной подсистемы
p4a.bootstrap = sdl2

[buildozer]

# Уровень логов (2 — подробно, удобно при первой сборке)
log_level = 2
warn_on_root = 1
