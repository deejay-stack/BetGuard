param(
    [switch]$Install,
    [switch]$SkipChecks,
    [ValidatePattern('^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$')]
    [string]$VersionName,
    [ValidatePattern('^(armeabi-v7a|arm64-v8a|x86|x86_64)(,(armeabi-v7a|arm64-v8a|x86|x86_64))*$')]
    [string]$Architectures = 'arm64-v8a',
    [ValidatePattern('^[A-Za-z0-9.:_-]+$')]
    [string]$DeviceSerial
)

$ErrorActionPreference = 'Stop'
$frontendRoot = Split-Path -Parent $PSScriptRoot
$versionPath = Join-Path $frontendRoot 'app.version.json'
$originalJavaHome = $env:JAVA_HOME
$originalAndroidHome = $env:ANDROID_HOME

function Invoke-CheckedCommand([string]$Executable, [string[]]$Arguments, [string]$Action) {
    Get-Command $Executable -ErrorAction Stop | Out-Null
    # Windows PowerShell wraps ordinary native stderr (including Jest PASS output)
    # as error records when redirected. Use the process exit code for success.
    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments
        $nativeExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousErrorPreference }
    if ($nativeExitCode -ne 0) { throw "$Action failed (exit $nativeExitCode). No app was uninstalled." }
}

Push-Location $frontendRoot
try {
    # JAVA_HOME points at the JDK, not its bin folder. Repair only this process.
    if ($env:JAVA_HOME -and (Split-Path -Leaf $env:JAVA_HOME) -eq 'bin') {
        $env:JAVA_HOME = Split-Path -Parent $env:JAVA_HOME
    }
    if (-not $env:ANDROID_HOME) {
        $defaultSdkRoot = Join-Path $env:LOCALAPPDATA 'Android/Sdk'
        if (Test-Path -LiteralPath $defaultSdkRoot) { $env:ANDROID_HOME = $defaultSdkRoot }
    }
    if (-not $SkipChecks) {
        Invoke-CheckedCommand 'npm.cmd' @('run', 'typecheck') 'Typecheck'
        Invoke-CheckedCommand 'npm.cmd' @('run', 'lint') 'Lint'
        Invoke-CheckedCommand 'npm.cmd' @('test', '--', '--runInBand', '--silent') 'Tests'
    }

    $version = Get-Content -LiteralPath $versionPath -Raw | ConvertFrom-Json
    if ($VersionName) { $version.versionName = $VersionName }
    $version.versionCode = [int]$version.versionCode + 1
    [System.IO.File]::WriteAllText($versionPath, ($version | ConvertTo-Json) + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Building BetGuard Dev $($version.versionName), build $($version.versionCode)."
    $apiConfig = Get-Content -LiteralPath (Join-Path $frontendRoot 'api.config.json') -Raw | ConvertFrom-Json
    if (-not $apiConfig.remoteBaseUrl) {
        Write-Host 'Saved APK: on-device rules. Online smart protection needs a deployed HTTPS remoteBaseUrl.'
    }
    Push-Location (Join-Path $frontendRoot 'android')
    try {
        Invoke-CheckedCommand '.\gradlew.bat' @(':app:assembleDevelopmentRelease', "-PreactNativeArchitectures=$Architectures", '--max-workers=2', '--console=plain') 'Android build'
    } finally { Pop-Location }

    $artifactDirectory = Join-Path $frontendRoot 'build/apk'
    New-Item -ItemType Directory -Force -Path $artifactDirectory | Out-Null
    $artifactName = "BetGuard-v$($version.versionName)-b$($version.versionCode).apk"
    $artifactPath = Join-Path $artifactDirectory $artifactName
    Copy-Item -LiteralPath (Join-Path $frontendRoot 'android/app/build/outputs/apk/development/release/app-development-release.apk') -Destination $artifactPath
    Copy-Item -LiteralPath $artifactPath -Destination (Join-Path $artifactDirectory 'BetGuard-latest.apk')
    $hash = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [System.IO.File]::WriteAllText(($artifactPath + '.sha256'), "$hash  $artifactName" + [Environment]::NewLine)
    Write-Host "Saved APK: $artifactPath"
    Write-Host 'Install the APK to apply changes; rebuilding alone does not update the phone.'

    if ($Install) {
        $sdkRoot = $env:ANDROID_HOME
        if (-not $sdkRoot) { $sdkRoot = Join-Path $env:LOCALAPPDATA 'Android/Sdk' }
        $adbPath = Join-Path $sdkRoot 'platform-tools/adb.exe'
        if (-not (Test-Path -LiteralPath $adbPath)) { throw 'adb was not found. Set ANDROID_HOME to the Android SDK.' }
        $adbTarget = @()
        if ($DeviceSerial) { $adbTarget = @('-s', $DeviceSerial) }
        Invoke-CheckedCommand $adbPath ($adbTarget + @('install', '-r', $artifactPath)) 'APK update (same signing key required)'
        Invoke-CheckedCommand $adbPath ($adbTarget + @('push', $artifactPath, "/sdcard/Download/$artifactName")) 'Copy to phone Download folder'
        Invoke-CheckedCommand $adbPath ($adbTarget + @('shell', 'am', 'start', '-n', 'com.betguard.dev/com.betguard.MainActivity')) 'Launch'
        Write-Host 'Updated BetGuard Dev and saved a copy in Download. Rules/settings are retained.'
    }
} finally {
    $env:JAVA_HOME = $originalJavaHome
    $env:ANDROID_HOME = $originalAndroidHome
    Pop-Location
}
