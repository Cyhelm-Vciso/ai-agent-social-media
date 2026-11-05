<#
  One-time setup for SocialAgent on Windows 10/11.

  1. llama.cpp
       default:   winget install llama.cpp      (installs on this PC)
       -Portable: downloads the official llama.cpp release into <drive>\SocialAgent\bin so it runs on any PC
  2. Python: a portable Python (embeddable, ~11 MB) into <drive>\SocialAgent\runtime\python, unless -UseSystemPython
  3. Model:  pre-downloads Qwen2.5-7B-Instruct Q4_K_M (~4.7 GB) into <drive>\SocialAgent\models (skip with -SkipModel)

  Usage:  SETUP-Windows.bat            or   SETUP-Windows.bat -Portable
#>
param(
  [switch]$Portable,
  [ValidateSet("cpu", "vulkan")] [string]$Backend = "cpu",
  [switch]$UseSystemPython,
  [switch]$SkipModel,
  [string]$PythonVersion = "3.12.10"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # much faster downloads in Windows PowerShell 5.1
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = Split-Path -Parent $PSScriptRoot
$arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }

# --- check the drive -------------------------------------------------------------
$drive = (Get-Item $Root).PSDrive.Name + ":"
try {
  $vol = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$drive'"
  $freeGB = [math]::Round($vol.FreeSpace / 1GB, 1)
  Write-Host "Drive $drive  file system: $($vol.FileSystem)  free: $freeGB GB"
  if ($vol.FileSystem -eq "FAT32") {
    Write-Host "WARNING: FAT32 cannot store files over 4 GB. Reformat the USB drive as exFAT (or NTFS) if the model download fails." -ForegroundColor Yellow
  }
  if ($freeGB -lt 7) { Write-Host "WARNING: at least 7 GB free space is recommended." -ForegroundColor Yellow }
} catch { }

# --- 1. llama.cpp --------------------------------------------------------------
Step "llama.cpp (the LLM runtime)"
if ($Portable) {
  $bin = Join-Path $Root "bin"
  if (Get-ChildItem $bin -Filter llama-server.exe -Recurse -ErrorAction SilentlyContinue) {
    Write-Host "Portable llama.cpp already on the drive."
  } else {
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest" -Headers @{ "User-Agent" = "SocialAgent-setup" }
    $pattern = "bin-win-$Backend-$arch\.zip$"
    $asset = $rel.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
    if (-not $asset) { throw "No release asset matching '$pattern' in llama.cpp $($rel.tag_name). Download it manually from https://github.com/ggml-org/llama.cpp/releases into $bin" }
    Write-Host "Downloading $($asset.name) ($([math]::Round($asset.size / 1MB)) MB)..."
    $zip = Join-Path $env:TEMP $asset.name
    Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $zip
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    Expand-Archive -Path $zip -DestinationPath $bin -Force
    Remove-Item $zip
    Write-Host "Installed llama.cpp $($rel.tag_name) to $bin" -ForegroundColor Green
  }
} else {
  if (Get-Command llama-server -ErrorAction SilentlyContinue) {
    Write-Host "llama-server is already installed."
  } else {
    Write-Host "Running: winget install llama.cpp"
    winget install llama.cpp
    Write-Host "Installed. Windows only picks up the new command in a NEW PowerShell window." -ForegroundColor Yellow
  }
}

# --- 2. Python -----------------------------------------------------------------
Step "Python (runs the agent)"
$pyDir = Join-Path $Root "runtime\python"
if ($UseSystemPython) {
  Write-Host "Using the Python installed on this PC."
} elseif (Test-Path (Join-Path $pyDir "python.exe")) {
  Write-Host "Portable Python already on the drive."
} else {
  $pyArch = if ($arch -eq "arm64") { "arm64" } else { "amd64" }
  $url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-$pyArch.zip"
  Write-Host "Downloading portable Python $PythonVersion..."
  $zip = Join-Path $env:TEMP "python-embed.zip"
  Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
  New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
  Expand-Archive -Path $zip -DestinationPath $pyDir -Force
  Remove-Item $zip
  # Let the embedded Python import the agent package from the bundle root (two folders up).
  $pth = Get-ChildItem $pyDir -Filter "python*._pth" | Select-Object -First 1
  if ($pth) { Add-Content -Path $pth.FullName -Value "..\.." }
  Write-Host "Portable Python installed to $pyDir" -ForegroundColor Green
}

# --- 3. accounts file ------------------------------------------------------------
$acc = Join-Path $Root "config\accounts.json"
if (-not (Test-Path $acc)) {
  Copy-Item (Join-Path $Root "config\accounts.example.json") $acc
  Write-Host "`nCreated config\accounts.json. Add tokens for the platforms you want to post to directly (optional)."
}

# --- 4. model ------------------------------------------------------------------
if (-not $SkipModel) {
  Step "Model: Qwen2.5-7B-Instruct Q4_K_M (~4.7 GB)"
  Write-Host "The model downloads the first time the LLM starts. Starting it now so it's ready for later..."
  Write-Host "When you see 'server is listening', the model is on the drive: press Ctrl+C to stop, then use START-SocialAgent.bat."
  & (Join-Path $Root "scripts\start-llm.ps1") -BindHost 127.0.0.1
}

Write-Host "`nSetup complete. Double-click START-SocialAgent.bat to run SocialAgent." -ForegroundColor Green
