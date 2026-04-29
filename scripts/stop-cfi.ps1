$ErrorActionPreference = "SilentlyContinue"

$Ports = @(5173, 8000)

foreach ($Port in $Ports) {
    $Connections = Get-NetTCPConnection -LocalPort $Port -State Listen

    foreach ($Connection in $Connections) {
        $ProcessId = $Connection.OwningProcess
        if ($ProcessId) {
            Stop-Process -Id $ProcessId -Force
            Write-Host "Proceso detenido en puerto $Port. PID: $ProcessId"
        }
    }
}

Write-Host "CFI detenido."
