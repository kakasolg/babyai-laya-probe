# Builds the Windows Laya server: one folder with laya_server.exe, the model (ONNX fp32) and reports/stage3_5.
# Needs: D:\dev\tools\laya-win-venv (torch cpu, laya 0.4.31, onnxruntime 1.25.1, minigrid, pyinstaller) and the
# ONNX export in WSL ~/babyai-laya-web/laya_fp32.onnx. Output goes outside the repo (default D:\dev\tools\laya-server-dist).
param([string]$Out = "D:\dev\tools\laya-server-dist", [string]$Wsl = "\\wsl.localhost\Ubuntu\home\moka", [switch]$FilesOnly)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$py = "D:\dev\tools\laya-win-venv\Scripts\python.exe"
if (-not $FilesOnly) {
    & $py -m PyInstaller --noconfirm --name laya_server --distpath $Out --workpath "$Out\_work" --specpath "$Out\_work" `
        --paths $repo --collect-all laya --collect-all minigrid --collect-submodules transformers --collect-data transformers `
        --exclude-module tensorflow --exclude-module matplotlib "$PSScriptRoot\entry.py"
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }
}
$dst = "$Out\laya_server"
$ck = "$Wsl\babyai-laya-ft\gotolocal-s0"
New-Item -ItemType Directory -Force "$dst\model\encoder", "$dst\reports\stage3_5" | Out-Null
Copy-Item "$ck\rl_agent_config.json", "$ck\questions.json" "$dst\model\"
Copy-Item "$ck\encoder\config.json" "$dst\model\encoder\"
Copy-Item -Recurse -Force "$ck\tokenizer" "$dst\model\"
if (-not (Test-Path "$dst\model\laya_fp32.onnx")) { Copy-Item "$Wsl\babyai-laya-web\laya_fp32.onnx" "$dst\model\" }
foreach ($s in 0..2) { Copy-Item "$repo\reports\stage3_5\model-s$s.json" "$dst\reports\stage3_5\" }
"built $dst"
