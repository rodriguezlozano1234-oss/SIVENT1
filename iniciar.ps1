# Inicia SIVENT con Docker en Windows. Crea el archivo .env con una clave secreta si falta.
# Uso: clic derecho > "Ejecutar con PowerShell", o doble clic en iniciar.bat
Set-Location -Path $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker no esta instalado o no esta en el PATH. Instale Docker Desktop." -ForegroundColor Red
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop no esta iniciado. Abralo y espere a que indique 'Engine running'." -ForegroundColor Red
    exit 1
}

$tieneClave = (Test-Path ".env") -and ((Get-Content ".env" -Raw) -match "SIVENT_SECRET_KEY=\S+")
if (-not $tieneClave) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $clave = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
    Set-Content -Path ".env" -Value "SIVENT_SECRET_KEY=$clave" -Encoding ascii
    Write-Host "Se creo el archivo .env con una clave secreta nueva." -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path "data" | Out-Null

docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nNo se pudo iniciar. Revise el mensaje de arriba o ejecute: docker compose logs sivent" -ForegroundColor Red
    exit 1
}

Write-Host "`nSIVENT esta en marcha." -ForegroundColor Green
Write-Host "  En esta PC:  http://localhost:5000/login"
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    ForEach-Object { Write-Host ("  En la red:   http://{0}:5000/login  (para celulares y otras PC)" -f $_.IPAddress) }
Start-Process "http://localhost:5000/login"
