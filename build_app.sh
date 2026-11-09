#!/bin/zsh
# Самодостаточный Severance Studio.app: переносимый Python + все библиотеки
# внутри бандла. По мотивам build_app.sh классического Severance.
# Конверсия голоса (Seed-VC) пока живёт во внешнем окружении
# /Users/tonix/Developer/severance/voice — в бандл не входит.
set -e
setopt null_glob
cd "${0:A:h}"
SRC="$PWD"
OUT="$SRC/build"
APP="$OUT/Severance Studio.app"
REL="https://github.com/astral-sh/python-build-standalone/releases/download/20260901"
PY_URL="$REL/cpython-3.12.14%2B20260901-aarch64-apple-darwin-install_only_stripped.tar.gz"

say() { print -P "%F{green}==>%f $*"; }

rm -rf "$APP"
mkdir -p "$OUT" "$APP/Contents/MacOS" "$APP/Contents/Resources"
RES="$APP/Contents/Resources"

say "переносимый Python"
[ -f "$OUT/python.tar.gz" ] || curl -fsSL "$PY_URL" -o "$OUT/python.tar.gz"
mkdir -p "$RES/python"
tar xzf "$OUT/python.tar.gz" -C "$RES/python" --strip-components=1
PY="$RES/python/bin/python3"

say "библиотеки (это несколько минут)"
uv pip freeze -q --python .venv/bin/python > "$OUT/req.txt"
uv pip install -q --python "$PY" --break-system-packages -r "$OUT/req.txt"

say "чистка лишнего"
SP="$RES/python/lib/python3.12/site-packages"
for m in Qt3D QtCharts QtDataVis QtDesigner QtQuick3D QtSensors QtSerial QtSql \
         QtTest QtBluetooth QtNfc QtRemoteObjects QtScxml QtSpatialAudio \
         QtStateMachine QtTextToSpeech QtHelp QtUiTools QtPdf QtMultimediaQuick \
         QtWebEngine QtWebView QtWebChannel QtWebSockets QtPositioning \
         QtLocation QtQuick QtQml QtGraphs QtVirtualKeyboard QtHttpServer; do
    rm -rf "$SP/PySide6/Qt/lib/${m}"*.framework "$SP/PySide6/${m}"* 2>/dev/null || true
done
rm -rf "$SP/PySide6/Qt/translations" "$SP/PySide6/Qt/qml" \
       "$SP/PySide6/Designer.app" "$SP/PySide6/assistant.app" \
       "$SP/PySide6/linguist.app" "$SP/PySide6/examples" 2>/dev/null || true
rm -rf "$SP/torch/include" "$SP/torch/share"
find "$RES/python/lib" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$RES/python/lib" -name "test" -type d -prune -exec rm -rf {} + 2>/dev/null || true

say "байт-код"
"$PY" -m compileall -q -j 0 --invalidation-mode unchecked-hash "$RES/python/lib/python3.12" >/dev/null 2>&1 || true

say "ffmpeg"
mkdir -p "$RES/app/bin" "$OUT/tools"
if [ ! -f "$OUT/tools/ffmpeg" ]; then
    # готовая LGPL-сборка из классического Severance, если есть
    if [ -f /Users/tonix/Developer/severance/build/tools/ffmpeg ]; then
        cp /Users/tonix/Developer/severance/build/tools/ffmpeg \
           /Users/tonix/Developer/severance/build/tools/ffprobe "$OUT/tools/"
    else
        say "  сборка ffmpeg из исходников, это несколько минут"
        rm -rf "$OUT/ffsrc"; mkdir -p "$OUT/ffsrc"
        curl -fsSL "https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz" -o "$OUT/ffsrc/ff.tar.xz"
        tar xf "$OUT/ffsrc/ff.tar.xz" -C "$OUT/ffsrc" --strip-components=1
        ( cd "$OUT/ffsrc" && ./configure --prefix="$OUT/ffsrc/out" --disable-doc \
            --disable-ffplay --disable-debug --enable-small --disable-autodetect \
            --enable-zlib --enable-videotoolbox --enable-securetransport >/dev/null 2>&1 \
          && make -j"$(sysctl -n hw.ncpu)" >/dev/null 2>&1 \
          && make install >/dev/null 2>&1 )
        cp "$OUT/ffsrc/out/bin/ffmpeg" "$OUT/ffsrc/out/bin/ffprobe" "$OUT/tools/"
        rm -rf "$OUT/ffsrc"
    fi
fi
cp "$OUT/tools/ffmpeg" "$OUT/tools/ffprobe" "$RES/app/bin/"
chmod +x "$RES/app/bin/"*

say "исходники"
cp app.py engine.py pianoroll.py als.py voices.py singer.py "$RES/app/"
cp -R templates "$RES/app/"
"$PY" -m compileall -q --invalidation-mode unchecked-hash "$RES/app" >/dev/null

say "интерпретатор в MacOS"
cp "$RES/python/bin/python3.12" "$APP/Contents/MacOS/SeveranceStudio"

say "оболочка"
cat > "$APP/Contents/MacOS/launcher" <<'LAUNCH'
#!/bin/zsh
LOG="$HOME/Library/Logs/SeveranceStudio.log"
mkdir -p "$HOME/Library/Logs"
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG")" -gt 5000000 ]; then : > "$LOG"; fi
exec >> "$LOG" 2>&1
echo "=== запуск $(date) ==="
DIR="${0:A:h}"
RES="$DIR/../Resources"
export PATH="$RES/app/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONHOME="$RES/python"
export PYTHONDONTWRITEBYTECODE=1
export NUMBA_CACHE_DIR="$HOME/Library/Caches/SeveranceStudio/numba"
cd "$RES/app"
exec "$DIR/SeveranceStudio" "$RES/app/app.py"
LAUNCH
chmod +x "$APP/Contents/MacOS/launcher"
cp icon/AppIcon.icns "$RES/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDevelopmentRegion</key><string>ru</string>
<key>CFBundleLocalizations</key><array><string>ru</string><string>en</string></array>
<key>CFBundleDisplayName</key><string>Severance Studio</string>
<key>CFBundleExecutable</key><string>launcher</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleIconName</key><string>AppIcon</string>
<key>CFBundleIdentifier</key><string>space.bdub.severance-studio</string>
<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
<key>CFBundleName</key><string>Severance Studio</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.2</string>
<key>CFBundleVersion</key><string>2</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSDocumentsFolderUsageDescription</key><string>Severance Studio открывает песни из папки «Документы».</string>
<key>NSDownloadsFolderUsageDescription</key><string>Severance Studio открывает песни из папки «Загрузки».</string>
<key>NSDesktopFolderUsageDescription</key><string>Severance Studio открывает песни с рабочего стола.</string>
<key>NSHumanReadableCopyright</key><string>DrTonix · bdub.space</string>
</dict></plist>
PLIST

say "подпись"
# ВАЖНО: если проект лежит в ~/Documents (iCloud Drive), Finder/iCloud
# постоянно добавляет xattr (com.apple.provenance и др.) — codesign падает
# с "resource fork ... not allowed". Поэтому подписываем копию в /tmp.
xattr -cr "$APP" 2>/dev/null || true
if xattr -l "$APP/Contents/Info.plist" 2>/dev/null | grep -q .; then
    say "  iCloud-атрибуты: подписываю копию в /tmp"
    rm -rf "/tmp/Severance Studio.app"
    cp -R "$APP" /tmp/
    xattr -cr "/tmp/Severance Studio.app"
    rm -rf "/tmp/Severance Studio.app/Contents/_CodeSignature"
    codesign --force --deep --sign - "/tmp/Severance Studio.app"
    codesign --verify --deep --strict "/tmp/Severance Studio.app"
    say "  подписанная копия: /tmp/Severance Studio.app"
else
    codesign --force --deep --sign - "$APP"
    codesign --verify --deep --strict "$APP"
fi

say "готово: $(du -sh "$APP" | cut -f1)  ->  $APP"
