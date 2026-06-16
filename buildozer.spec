[app]

title = Сканер билетов РЖД
package.name = rzdscanner
package.domain = ru.rzd.scanner

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,json

version = 1.0

# kivy/kivymd — интерфейс; certifi — корневые сертификаты для HTTPS
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,certifi

orientation = portrait
fullscreen = 0

android.permissions = android.permission.INTERNET, android.permission.ACCESS_NETWORK_STATE
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

p4a.bootstrap = sdl2
# Закрепляем python-for-android на релизе, который собирает Python 3.11.5.
# Свежий p4a тянет Python 3.14, несовместимый с Cython 0.29.x (ошибка PyCode_New).
p4a.fork = kivy
p4a.branch = v2024.01.21

[buildozer]

log_level = 2
warn_on_root = 1
