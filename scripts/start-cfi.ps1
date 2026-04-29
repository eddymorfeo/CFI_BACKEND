param(
    [switch]$BuildFrontend
)

$ErrorActionPreference = "Stop"

$BackendPath = Resolve-Path (Join-Path $PSScriptRoot "..")
$ProjectPath = Resolve-Path (Join-Path $BackendPath "..")
$FrontendPath = Join-Path $ProjectPath "CFI_FRONTEND"
$LogsPath = Join-Path $BackendPath "logs"

New-Item -ItemType Directory -Force -Path $LogsPath | Out-Null

function Test-LocalPortListening {
    param([int]$Port)

    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Client.Connect("127.0.0.1", $Port)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $Client.Close()
    }
}

if ($BuildFrontend) {
    Push-Location $FrontendPath
    npm run build
    Pop-Location
}

$BackendCommand = @"
Set-Location '$BackendPath'
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 *> '$LogsPath\backend.log'
"@

$FrontendCommand = @"
Set-Location '$FrontendPath'
npm start *> '$LogsPath\frontend.log'
"@

$BackendProcessId = "ya estaba activo"
$FrontendProcessId = "ya estaba activo"

if (-not (Test-LocalPortListening -Port 8000)) {
    $BackendProcess = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $BackendCommand `
        -WindowStyle Hidden `
        -PassThru
    $BackendProcessId = $BackendProcess.Id
}

if (-not (Test-LocalPortListening -Port 5173)) {
    $FrontendProcess = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $FrontendCommand `
        -WindowStyle Hidden `
        -PassThru
    $FrontendProcessId = $FrontendProcess.Id
}

@"
CFI iniciado.

Frontend: http://172.17.208.51:5173/
Backend:  http://172.17.208.51:8000/api/v1

PID Backend:  $BackendProcessId
PID Frontend: $FrontendProcessId

Logs:
- $LogsPath\backend.log
- $LogsPath\frontend.log
"@ | Tee-Object -FilePath (Join-Path $LogsPath "startup.log")
