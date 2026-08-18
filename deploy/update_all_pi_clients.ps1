param(
    [string]$PiUser = "pi",
    [string]$ServerUrl = "http://192.168.10.49:8000",
    [string]$ScannerPort = "/dev/ttyACM0"
)

$ErrorActionPreference = "Continue"

$PiAddresses = @(
    "192.168.13.11",
    "192.168.13.12",
    "192.168.13.13",
    "192.168.13.14",
    "192.168.13.15",
    "192.168.13.16",
    "192.168.13.25",
    "192.168.13.26",
    "192.168.13.35"
)

$RemoteCommand = @"
set -e
cd "`$HOME/Raspberry_Machine/client"
./update_pi_client.sh --pull --server-url '$ServerUrl' --scanner-port '$ScannerPort' --skip-system-setup --no-start
sudo reboot
"@

$Succeeded = @()
$Failed = @()

foreach ($Address in $PiAddresses) {
    Write-Host ""
    Write-Host "Updating $Address..." -ForegroundColor Cyan

    # A pseudo-terminal permits sudo to request a password when passwordless
    # reboot permission has not yet been configured on a client.
    & ssh -t "$PiUser@$Address" $RemoteCommand

    if ($LASTEXITCODE -eq 0) {
        $Succeeded += $Address
        Write-Host "$Address updated; reboot command sent." -ForegroundColor Green
    }
    else {
        $Failed += $Address
        Write-Host "$Address failed. Its data was not deleted." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Deployment summary" -ForegroundColor Cyan
Write-Host "Succeeded ($($Succeeded.Count)): $($Succeeded -join ', ')" -ForegroundColor Green
if ($Failed.Count -gt 0) {
    Write-Host "Failed ($($Failed.Count)): $($Failed -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "Failed (0): none" -ForegroundColor Green
