# Paperloom을 Docker로 띄운다(Windows). NVIDIA GPU가 있으면 GPU 이미지로(문서 레이아웃 모델을 CUDA로), 없거나 GPU로
# 띄우지 못하면 CPU 이미지로 띄운다. 데이터 volume은 같다.
# 실행: powershell -ExecutionPolicy Bypass -File ops\start.ps1
$compose = Join-Path $PSScriptRoot "compose"
$base = Join-Path $compose "compose.yaml"
$gpu = $false
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi -L | Out-Null
    $gpu = $LASTEXITCODE -eq 0
}
if ($gpu) {
    Write-Host "NVIDIA GPU를 찾았습니다. GPU 이미지로 띄웁니다."
    docker compose -f $base -f (Join-Path $compose "compose.gpu.yaml") up -d --build
    if ($LASTEXITCODE -eq 0) { exit 0 }
    Write-Warning "GPU로 띄우지 못해 CPU 이미지로 띄웁니다."
}
docker compose -f $base up -d --build
exit $LASTEXITCODE
