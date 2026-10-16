#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source_dir="src/linguacaption/native/macos"
app_dir="$source_dir/AudioCapture.app/Contents"
mkdir -p "$app_dir/MacOS"
cp "$source_dir/Info.plist" "$app_dir/Info.plist"
xcrun swiftc -O -parse-as-library -swift-version 5 \
  -target "$(uname -m)-apple-macos13.0" \
  -framework AppKit -framework AVFoundation -framework ScreenCaptureKit -framework CoreMedia \
  "$source_dir/SystemAudio.swift" -o "$app_dir/MacOS/AudioCapture"
codesign --force --sign - "$source_dir/AudioCapture.app"
echo "Built ScreenCaptureKit helper: $source_dir/AudioCapture.app"
