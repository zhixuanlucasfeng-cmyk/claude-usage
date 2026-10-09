#!/bin/sh
# Build "Claude Usage Widget.app" next to this script, pointing it at the
# claude-usage executable from this checkout's venv (override with $1).
set -e
cd "$(dirname "$0")"
BIN="${1-$(cd .. && pwd)/venv/bin/claude-usage}"  # pass "" for a release build
APP="Claude Usage Widget.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
# Universal binary, so a release built on Apple Silicon also runs on Intel Macs.
for arch in arm64 x86_64; do
  swiftc -O -target $arch-apple-macos13 UsageWidget.swift -o "$APP/Contents/MacOS/UsageWidget-$arch"
done
lipo -create "$APP"/Contents/MacOS/UsageWidget-* -output "$APP/Contents/MacOS/UsageWidget"
rm "$APP"/Contents/MacOS/UsageWidget-*
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>UsageWidget</string>
  <key>CFBundleIdentifier</key><string>local.claude-usage.widget</string>
  <key>CFBundleName</key><string>Claude Usage Widget</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>CUServerBin</key><string>$BIN</string>
</dict></plist>
PLIST
echo "Built $(pwd)/$APP"
