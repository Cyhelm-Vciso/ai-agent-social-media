<#
  Starts everything: the LLM (in its own window), waits until the model is loaded, then starts the
  SocialAgent web app and opens it in the browser.

  LLM parameters are passed through to start-llm.ps1, e.g.:
    START-SocialAgent.bat -LowMemory
    START-SocialAgent.bat -BindHost 127.0.0.1
#>
param(
  [string]$Model = "",
  [int]$Context = -1,
  [string]$BindHost = "",
  [int]$Port = 0,
  [int]$Threads = 0,
  [int]$GpuLayers = -1,
  [switch]$LowMemory,
  [switch]$NoMmap
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$settings = Get-Content (Join-Path $Root "config\settings.json") -Raw | ConvertFrom-Json
$llmUrl = $settings.llm_url.TrimEnd("/")
$uiPort = $settings.ui_port

function Find-Python {
  $portable = Join-Path $Root "runtime\python\python.exe"
  if (Test-Path $portable) { return @($portable) }
  foreach ($c in @("py", "python", "python3")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike "*WindowsApps*") {
      if ($c -eq "py") { return @($cmd.Source, "-3") } else { return @($cmd.Source) }
    }
  }
  return $null
}

function Test-Llm {
  try { $r = Invoke-WebRequest -UseBasicParsing -Uri "$llmUrl/health" -TimeoutSec 3; return $r.StatusCode -eq 200 }
  catch { return $false }
}

$python = @(Find-Python | Where-Object { $_ })
if ($python.Count -eq 0) {
  Write-Host "Python was not found. Run SETUP-Windows.bat once to put a portable Python on the drive." -ForegroundColor Red
  exit 1
}

# 1) start the LLM unless it's already running
if (-not (Test-Llm)) {
  $llmScript = Join-Path $PSScriptRoot "start-llm.ps1"
  $argLine = "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$llmScript`""
  if ($Model)          { $argLine += " -Model `"$Model`"" }
  if ($Context -ge 0)  { $argLine += " -Context $Context" }
  if ($BindHost)       { $argLine += " -BindHost $BindHost" }
  if ($Port -gt 0)     { $argLine += " -Port $Port" }
  if ($Threads -gt 0)  { $argLine += " -Threads $Threads" }
  if ($GpuLayers -ge 0){ $argLine += " -GpuLayers $GpuLayers" }
  if ($LowMemory)      { $argLine += " -LowMemory" }
  if ($NoMmap)         { $argLine += " -NoMmap" }
  Start-Process powershell -ArgumentList $argLine -WindowStyle Normal | Out-Null
  Write-Host "Waiting for the model to load (the first run downloads ~4.7 GB, so this can take a while)..." -ForegroundColor Cyan
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while (-not (Test-Llm)) {
    Start-Sleep -Seconds 3
    Write-Host -NoNewline "."
    if ($sw.Elapsed.TotalMinutes -gt 120) { Write-Host "`nThe model did not start. Check the LLM window for errors."; exit 1 }
  }
  Write-Host "`nModel ready after $([int]$sw.Elapsed.TotalSeconds) s." -ForegroundColor Green
} else {
  Write-Host "LLM already running at $llmUrl" -ForegroundColor Green
}

# 2) open the browser, then run the agent in this window
Start-Process "http://localhost:$uiPort" | Out-Null
$exe = $python[0]
$pyArgs = @()
if ($python.Count -gt 1) { $pyArgs += $python[1..($python.Count - 1)] }
$pyArgs += @((Join-Path $Root "run_agent.py"), "serve")
& $exe @pyArgs
