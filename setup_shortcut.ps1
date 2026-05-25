# 바탕화면 단축 아이콘 설치 스크립트
# 실행: PowerShell에서 .\setup_shortcut.ps1

$BotDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LaunchBat = Join-Path $BotDir "launch.bat"
$IcoFile   = Join-Path $BotDir "bot.ico"
$Desktop   = [Environment]::GetFolderPath("Desktop")
$Shortcut  = Join-Path $Desktop "오토선물봇.lnk"

Write-Host ""
Write-Host " ================================================" -ForegroundColor Cyan
Write-Host "   오토 선물봇 바탕화면 아이콘 설치" -ForegroundColor Cyan
Write-Host " ================================================" -ForegroundColor Cyan
Write-Host ""

# 1) Pillow 설치 확인 후 아이콘 생성
Write-Host " [1/3] 아이콘 생성 중..." -ForegroundColor Yellow
$pillowCheck = python -c "import PIL" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "       Pillow 설치 중..."
    pip install Pillow --quiet
}
python (Join-Path $BotDir "icon_gen.py")

if (-not (Test-Path $IcoFile)) {
    Write-Host " [경고] bot.ico 생성 실패 — 기본 아이콘 사용" -ForegroundColor Yellow
    $IcoFile = ""
}

# 2) 단축 아이콘 생성
Write-Host " [2/3] 바탕화면 단축 아이콘 생성 중..." -ForegroundColor Yellow

$Shell = New-Object -ComObject WScript.Shell
$Lnk   = $Shell.CreateShortcut($Shortcut)
$Lnk.TargetPath       = $LaunchBat
$Lnk.WorkingDirectory = $BotDir
$Lnk.Description      = "바이비트 자동 선물 봇 (EMA+OB+Fib)"
$Lnk.WindowStyle      = 1   # 일반 창

if ($IcoFile -ne "") {
    $Lnk.IconLocation = "$IcoFile,0"
}

$Lnk.Save()

# 3) 완료
Write-Host " [3/3] 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "  바탕화면에 '오토선물봇' 아이콘이 생성됐습니다." -ForegroundColor White
Write-Host "  더블클릭하면 봇이 실행됩니다." -ForegroundColor White
Write-Host ""
Write-Host "  ⚠️  실행 전 .env 파일에 API 키를 반드시 입력하세요!" -ForegroundColor Red
Write-Host ""

Read-Host "  Enter를 누르면 종료"
