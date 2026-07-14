$ErrorActionPreference = "Stop"

$serverIp = "192.168.10.49"
$gateway = "192.168.10.1"
$clientSubnet = "192.168.13.0"
$clientMask = "255.255.255.0"
$port = 8000

Write-Host "Fixing route/firewall for Raspberry Machine clients on 192.168.13.x..." -ForegroundColor Cyan

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    Write-Host "Please run this script in PowerShell as Administrator." -ForegroundColor Red
    exit 1
}

Write-Host "Adding route: $clientSubnet/$clientMask via $gateway"
route delete $clientSubnet 2>$null | Out-Null
route add $clientSubnet mask $clientMask $gateway metric 1

Write-Host "Allowing inbound TCP port $port in Windows Firewall"
netsh advfirewall firewall delete rule name="Raspberry Machine Dashboard Server 8000" 2>$null | Out-Null
netsh advfirewall firewall add rule name="Raspberry Machine Dashboard Server 8000" dir=in action=allow protocol=TCP localport=$port

Write-Host ""
Write-Host "Current listener:"
Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess |
    Format-Table -AutoSize

Write-Host ""
Write-Host "Current route for 192.168.13.x:"
route print 192.168.13.11

Write-Host ""
Write-Host "Done. Restart the Raspberry client app on 192.168.13.11." -ForegroundColor Green
