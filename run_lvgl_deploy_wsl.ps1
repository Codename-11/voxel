param(
    [string]$Distro = "Ubuntu",
    [string]$Host = "172.16.24.33",
    [string]$User = "pi",
    [string]$Password = "voxel",
    [string]$FramesDir = "./out/lvgl-frames",
    [int]$Frames = 24,
    [double]$FrameDelay = 0.18,
    [int]$Backlight = 70,
    [switch]$Rebuild,
    [switch]$NoPlayRemote
)

$ErrorActionPreference = "Stop"

$repoWin = (Resolve-Path $PSScriptRoot).Path
$repoWsl = "/mnt/" + $repoWin[0].ToString().ToLower() + ($repoWin.Substring(2) -replace "\\", "/")

$flags = @(
    "--frames-dir `"$FramesDir`"",
    "--frames $Frames",
    "--frame-delay $FrameDelay",
    "--backlight $Backlight",
    "--host $Host",
    "--user $User",
    "--password $Password"
)

if ($Rebuild) {
    $flags += "--rebuild"
}

if ($NoPlayRemote) {
    $flags += "--no-play-remote"
}

$command = @(
    "cd `"$repoWsl`"",
    'export PATH="$HOME/.local/bin:$PATH"',
    "uv run voxel lvgl-deploy $($flags -join ' ')"
) -join " && "

wsl.exe -d $Distro -- bash -lc $command
