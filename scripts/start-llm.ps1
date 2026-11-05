<#
  Starts the "brain": llama.cpp's llama-server running Qwen2.5-7B-Instruct (4-bit Q4_K_M).

  With the default parameters this runs exactly:
    llama-server -hf Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M --jinja -c 0 --host 0.0.0.0 --port 8034

  The model (about 4.7 GB) is downloaded on first run into <drive>\SocialAgent\models, so it travels with the USB drive.

  Examples:
    .\start-llm.ps1                      # the command above
    .\start-llm.ps1 -LowMemory           # 8 GB RAM PCs: 8K context instead of the model's full 32K
    .\start-llm.ps1 -BindHost 127.0.0.1  # only this PC can reach the model (recommended on public Wi-Fi)
    .\start-llm.ps1 -GpuLayers 99        # offload to a GPU (needs a CUDA/Vulkan build of llama.cpp)
#>
param(
  [string]$Model = "Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M",
  [int]$Context = 0,
  [string]$BindHost = "0.0.0.0",
  [int]$Port = 8034,
  [int]$Threads = 0,
  [int]$GpuLayers = -1,
  [switch]$LowMemory,
  [switch]$NoMmap
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

# Keep the downloaded model on the USB drive instead of the PC's user profile.
$env:LLAMA_CACHE = Join-Path $Root "models"
New-Item -ItemType Directory -Force -Path $env:LLAMA_CACHE | Out-Null

# Prefer a portable llama.cpp on the drive (setup -Portable), else the one installed with winget.
$server = Get-ChildItem -Path (Join-Path $Root "bin") -Filter "llama-server.exe" -Recurse -ErrorAction SilentlyContinue |
          Select-Object -First 1 -ExpandProperty FullName
if (-not $server) {
  $cmd = Get-Command llama-server -ErrorAction SilentlyContinue
  if ($cmd) { $server = $cmd.Source }
}
if (-not $server) {
  Write-Host ""
  Write-Host "llama-server was not found." -ForegroundColor Red
  Write-Host "Install it once with:   winget install llama.cpp"
  Write-Host "then close PowerShell, reopen it, and run this again."
  Write-Host "Or run SETUP-Windows.bat -Portable to put llama.cpp on the USB drive itself."
  exit 1
}

if ($LowMemory -and $Context -eq 0) { $Context = 8192 }

$llamaArgs = @("-hf", $Model, "--jinja", "-c", "$Context", "--host", $BindHost, "--port", "$Port")
if ($Threads -gt 0)   { $llamaArgs += @("-t", "$Threads") }
if ($GpuLayers -ge 0) { $llamaArgs += @("-ngl", "$GpuLayers") }
if ($NoMmap)          { $llamaArgs += "--no-mmap" }

Write-Host ""
Write-Host "Starting the LLM (Qwen2.5-7B-Instruct, Q4_K_M)" -ForegroundColor Cyan
Write-Host "  server : $server"
Write-Host "  models : $env:LLAMA_CACHE"
Write-Host "  command: llama-server $($llamaArgs -join ' ')"
if ($BindHost -eq "0.0.0.0") {
  Write-Host "  note   : --host 0.0.0.0 lets other devices on this network use the model. Use -BindHost 127.0.0.1 on public Wi-Fi." -ForegroundColor Yellow
}
Write-Host "  First run downloads about 4.7 GB. Leave this window open; close it to stop the model."
Write-Host ""

& $server @llamaArgs
