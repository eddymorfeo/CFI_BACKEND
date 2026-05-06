param(
    [switch]$SkipTests,
    [switch]$SkipFrontendBuild,
    [switch]$SkipPm2Save,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$BackendPath = Resolve-Path (Join-Path $PSScriptRoot "..")
$ProjectPath = Resolve-Path (Join-Path $BackendPath "..")
$FrontendPath = Join-Path $ProjectPath "CFI_FRONTEND"
$BackendEnvPath = Join-Path $BackendPath ".env"
$FrontendDevEnvPath = Join-Path $FrontendPath ".env.development"
$FrontendProdEnvPath = Join-Path $FrontendPath ".env.production"
$EcosystemPath = Join-Path $BackendPath "ecosystem.config.cjs"

function Assert-FileContains {
    param(
        [string]$Path,
        [string]$Expected,
        [string]$Description
    )

    $Content = Get-Content -Raw -Path $Path
    if ($Content -notlike "*$Expected*") {
        throw "Configuracion invalida: $Description. Se esperaba encontrar '$Expected' en $Path."
    }
}

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "==> $Title" -ForegroundColor Cyan
    & $Command
}

Invoke-Step "Validando separacion dev/prod" {
    Assert-FileContains -Path $BackendEnvPath -Expected "POSTGRES_DB=CFI_DEV" -Description "backend dev debe apuntar a CFI_DEV"
    Assert-FileContains -Path $EcosystemPath -Expected 'POSTGRES_DB: "CFI"' -Description "backend prod PM2 debe apuntar a CFI"
    Assert-FileContains -Path $EcosystemPath -Expected "--port 8000" -Description "backend prod debe usar puerto 8000"
    Assert-FileContains -Path $EcosystemPath -Expected '"5173"' -Description "frontend prod debe usar puerto 5173"
    Assert-FileContains -Path $FrontendDevEnvPath -Expected "VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1" -Description "frontend dev debe apuntar al backend dev"
    Assert-FileContains -Path $FrontendProdEnvPath -Expected "VITE_API_BASE_URL=http://172.17.208.51:8000/api/v1" -Description "frontend prod debe apuntar al backend prod"
}

if ($ValidateOnly) {
    Write-Host ""
    Write-Host "Validacion completada. No se ejecutaron tests, build ni PM2." -ForegroundColor Green
    return
}

if (-not $SkipTests) {
    Invoke-Step "Ejecutando tests backend" {
        Push-Location $BackendPath
        try {
            .\venv\Scripts\python.exe -m pytest
        }
        finally {
            Pop-Location
        }
    }
}

if (-not $SkipFrontendBuild) {
    Invoke-Step "Compilando frontend para produccion" {
        Push-Location $FrontendPath
        try {
            npm run build
        }
        finally {
            Pop-Location
        }
    }
}

Invoke-Step "Recargando servicios CFI en PM2" {
    Push-Location $BackendPath
    try {
        pm2 startOrReload $EcosystemPath --update-env
    }
    finally {
        Pop-Location
    }
}

if (-not $SkipPm2Save) {
    Invoke-Step "Guardando estado PM2" {
        pm2 save
    }
}

Write-Host ""
Write-Host "Despliegue CFI completado." -ForegroundColor Green
Write-Host "Frontend prod: http://172.17.208.51:5173/"
Write-Host "Backend prod:  http://172.17.208.51:8000/api/v1"
Write-Host "Backend prod usa POSTGRES_DB=CFI via ecosystem.config.cjs."
Write-Host "Backend dev conserva POSTGRES_DB=CFI_DEV via .env."
