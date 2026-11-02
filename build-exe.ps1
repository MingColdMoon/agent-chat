param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent $projectRoot
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $workspaceRoot ".uv-cache"
}
if (-not $env:UV_PYTHON_INSTALL_DIR) {
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $workspaceRoot ".uv-python"
}
if (-not $env:npm_config_cache) {
    $env:npm_config_cache = Join-Path $workspaceRoot ".npm-cache"
}

if (-not $SkipFrontend) {
    Push-Location $frontendDir
    try {
        if (-not (Test-Path "node_modules")) {
            npm install --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) {
                throw "前端依赖安装失败"
            }
        }
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "前端构建失败"
        }
    }
    finally {
        Pop-Location
    }
}

$frontendEntry = Join-Path $frontendDir "dist\index.html"
if (-not (Test-Path $frontendEntry)) {
    throw "找不到 frontend/dist/index.html，请先构建前端"
}

Push-Location $backendDir
try {
    uv sync --python 3.12 --group exe
    if ($LASTEXITCODE -ne 0) {
        throw "Python 依赖安装失败"
    }

    uv run pyinstaller `
        --noconfirm `
        --clean `
        --distpath (Join-Path $projectRoot "dist") `
        --workpath (Join-Path $projectRoot "build") `
        (Join-Path $projectRoot "agent_chat.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "EXE 构建失败"
    }
}
finally {
    Pop-Location
}

$exePath = Join-Path $projectRoot "dist\AgentChat.exe"
if (-not (Test-Path $exePath)) {
    throw "构建结束但未找到 AgentChat.exe"
}

$sizeMb = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
Write-Host ""
Write-Host "构建完成: $exePath ($sizeMb MB)" -ForegroundColor Green

