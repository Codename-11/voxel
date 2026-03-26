param(
    [string]$Distro = "Ubuntu",
    [string]$PiHost = "172.16.24.33",
    [string]$User = "pi",
    [string]$Password = "voxel",
    [string]$FramesDir = "./out/lvgl-frames",
    [int]$Frames = 24,
    [double]$FrameDelay = 0.18,
    [int]$Backlight = 70,
    [switch]$Rebuild,
    [switch]$NoPlayRemote,
    [switch]$PreviewLocal,
    [switch]$InteractivePreview,
    [double]$HoldToExit = 1.2,
    [switch]$UpdatePi,
    [switch]$PauseAtEnd,
    [switch]$NoPauseAtEnd
)

$ErrorActionPreference = "Stop"

$repoWin = (Resolve-Path $PSScriptRoot).Path
$repoWsl = "/mnt/" + $repoWin[0].ToString().ToLower() + ($repoWin.Substring(2) -replace "\\", "/")

$flags = @(
    "--frames-dir `"$FramesDir`"",
    "--frames $Frames",
    "--frame-delay $FrameDelay",
    "--backlight $Backlight",
    "--host $PiHost",
    "--user $User",
    "--password $Password"
)

if ($Rebuild) {
    $flags += "--rebuild"
}

if ($NoPlayRemote) {
    $flags += "--no-play-remote"
}

if ($PreviewLocal) {
    $flags += "--preview-local"
}

if ($InteractivePreview) {
    $flags += "--hold-to-exit $HoldToExit"
}

if ($UpdatePi) {
    $flags += "--update-pi"
}

$command = @(
    "cd `"$repoWsl`"",
    'export PATH="$HOME/.local/bin:$PATH"',
    "uv run voxel lvgl-dev $($flags -join ' ')"
) -join " && "

wsl.exe -d $Distro -- bash -lc $command

if ($PreviewLocal) {
    $previewPath = Join-Path $repoWin ($FramesDir -replace '^\./', '')
    $previewGif = Join-Path $previewPath 'preview.gif'
    if (Test-Path $previewGif) {
        Start-Process $previewGif
    }
}

$shouldPause = $PauseAtEnd -or (-not $NoPauseAtEnd)

if ($shouldPause) {
    Read-Host "Press Enter to close"
}
