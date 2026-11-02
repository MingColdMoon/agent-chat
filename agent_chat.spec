# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH)
datas = [
    (str(project_root / "frontend" / "dist"), "frontend_dist"),
]
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

for package_name in (
    "argon2",
    "asyncpg",
    "fastapi",
    "greenlet",
    "httpx",
    "jwt",
    "langchain_core",
    "langchain_openai",
    "openai",
    "pydantic",
    "pydantic_settings",
    "pwdlib",
    "redis",
    "sqlalchemy",
    "tiktoken",
    "uvicorn",
):
    package_data, package_binaries, package_hiddenimports = collect_all(
        package_name
    )
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_hiddenimports


a = Analysis(
    [str(project_root / "backend" / "agent_launcher.py")],
    pathex=[str(project_root / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AgentChat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

