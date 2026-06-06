[app]

title = ZAuto VIP

package.name = zauto
package.domain = org.zauto

source.dir = .

source.include_exts = py,png,jpg,kv,atlas,js,json
source.include_patterns = nodejs_backend/node_modules/*,nodejs_backend/node_modules/*/*,nodejs_backend/node_modules/*/*/*,nodejs_backend/node_modules/*/*/*/*,nodejs_backend/node_modules/*/*/*/*/*
version = 7.0

orientation = portrait
fullscreen = 0

icon.filename = profile_icon.png
presplash.filename = profile_icon.png
presplash.color = #FFFFFF

# =====================================================
# PYTHON / KIVY
# =====================================================
# ĐÃ KHÓA CỨNG PYTHON 3.11.4 ĐỂ CHỐNG LỖI SERVER
requirements = python3==3.11.4,hostpython3==3.11.4,kivy==2.2.1,kivymd,pyjnius,pillow,requests,plyer

# =====================================================
# LOG
# =====================================================
log_level = 2
warn_on_root = 0

# =====================================================
# ANDROID
# =====================================================
android.api = 34
android.minapi = 24
android.ndk = 25b

android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a

# Khai báo libnode.so cho từng loại chip
android.add_libs_arm64_v8a = nodejs_backend/bin/arm64-v8a/libnode.so
android.add_libs_armeabi_v7a = nodejs_backend/bin/armeabi-v7a/libnode.so

# =====================================================
# P4A
# =====================================================
p4a.bootstrap = sdl2

# =====================================================
# ANDROIDX
# =====================================================
android.enable_androidx = True

# =====================================================
# JAVA / RES
# =====================================================
android.add_src = java_src
android.add_res = ./res

# =====================================================
# GRADLE
# =====================================================
android.gradle_dependencies = androidx.core:core:1.12.0,androidx.webkit:webkit:1.7.0
android.gradle_args = -Xmx4096m

# =====================================================
# APK
# =====================================================
android.release_artifact = apk
android.package_format = apk

# =====================================================
# FOREGROUND SERVICE
# =====================================================
android.foreground_service = True

# =====================================================
# QUERY PACKAGE
# =====================================================
android.manifest_queries = com.zing.zalo

# =====================================================
# PERMISSIONS
# =====================================================
android.permissions = INTERNET,WAKE_LOCK,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,POST_NOTIFICATIONS,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,RECEIVE_BOOT_COMPLETED,SYSTEM_ALERT_WINDOW,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

# =====================================================
# EXTRA MANIFEST
# =====================================================
android.extra_manifest_application = %(source.dir)s/manifest_services.xml

# =====================================================
# SERVICES
# =====================================================
# ĐÃ VÔ HIỆU HÓA: Dòng này được tắt để tránh xung đột với file manifest_services.xml
# services = ZaloForegroundService:java

# =====================================================
# OPENGL
# =====================================================
android.opengl_es_version = 2

# =====================================================
# PERFORMANCE
# =====================================================
android.copy_libs = 1

# =====================================================
# DEBUG
# =====================================================
android.logcat_filters = python:D *:S

# =====================================================
# BUILD FIX
# =====================================================
android.skip_update = False

# =====================================================
# EXCLUDE
# =====================================================
source.exclude_dirs = venv,.venv,env,.git,.github,**pycache**,.buildozer
source.exclude_patterns = *.pyc,*.pyo,*.log,*.tmp

# =====================================================
# ASSETS
# =====================================================
# android.add_assets = .

# =====================================================
# SDL2
# =====================================================
sdl2_gradle_dependencies = True

[buildozer]

log_level = 2
warn_on_root = 0

build_dir = ./.buildozer
bin_dir = ./bin
