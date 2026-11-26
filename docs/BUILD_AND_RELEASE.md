# Build and release

## One-time: Android SDK (free)

The SDK is installed through Android Studio's SDK Manager (Android Studio is already
installed on the dev machine). Put it on the drive with free space (F:).

1. Android Studio → **More Actions → SDK Manager** (or Settings → Languages & Frameworks → Android SDK).
2. Set **Android SDK Location** to `F:\Android\Sdk`.
3. *SDK Platforms*: the latest stable Android platform.
4. *SDK Tools*: Android SDK Build-Tools, Android SDK Platform-Tools, Android SDK Command-line Tools (latest), NDK (Side by side), CMake.
5. Apply, accept the licenses.
6. Environment variables (PowerShell, current user):

```powershell
[Environment]::SetEnvironmentVariable('ANDROID_HOME', 'F:\Android\Sdk', 'User')
```

```powershell
[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','User') + ';F:\Android\Sdk\platform-tools', 'User')
```

Open a new terminal and check with `adb version`.

## Phone

Settings → About phone → tap *Build number* 7 times → Developer options →
enable **USB debugging** → connect by USB → accept the "Allow USB debugging" prompt.
`adb devices` must list the phone as `device` (not `unauthorized`).

## Development build

```powershell
cd mobile
npx expo run:android
```

This runs `expo prebuild` (generates `android/`, which is not committed) and builds with Gradle locally.

## Release (Phase 10)

Local signing key + `./gradlew assembleRelease`. Documented in Phase 10.

## Why a local SDK rather than cloud builds (measured 2026-11-21)

At ~129 KB/s, every cloud-built dev APK (expected 100–200 MB once native ML libraries and models are in)
takes roughly 13–26 minutes just to download to the phone, and Phases 6–8 need many native rebuilds.
The local SDK is a one-time download (several hours at this speed, can run overnight); after that
rebuilds need no download. Keep the Gradle cache off drive C: as well:

```powershell
[Environment]::SetEnvironmentVariable('GRADLE_USER_HOME', 'F:\gradle-home', 'User')
```

## Network: local proxy (found 2026-11-22)

This machine reaches the internet through a local proxy set in Windows Internet Settings
(`http/https = 127.0.0.1:63560`, socks `127.0.0.1:63559`). curl and the Android CLI use it;
**Java/Gradle does not**, and direct connections to dl.google.com time out
("Connect to dl.google.com:443 ... Connection timed out"). Fix, in `F:\gradle-home\gradle.properties`:

```
systemProp.http.proxyHost=127.0.0.1
systemProp.http.proxyPort=63560
systemProp.https.proxyHost=127.0.0.1
systemProp.https.proxyPort=63560
```

plus longer timeouts/retries (`systemProp.org.gradle.internal.http.socketTimeout=300000`,
`org.gradle.internal.repository.max.retries=10`). If the proxy app changes its port, update these lines.
