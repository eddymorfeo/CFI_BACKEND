$ErrorActionPreference = "Stop"

$TaskName = "CFI PM2 Resurrect"
$Pm2Command = (Get-Command pm2.cmd -ErrorAction Stop).Source
$Action = New-ScheduledTaskAction `
    -Execute $Pm2Command `
    -Argument "resurrect"

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Force | Out-Null

Write-Host "Tarea programada instalada: $TaskName"
Write-Host "Comando: $Pm2Command resurrect"
