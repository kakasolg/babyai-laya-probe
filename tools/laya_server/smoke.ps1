# Starts the packaged Laya server on a spare port, plays one step of the first room over HTTP, and quits it.
param([string]$Dir = "D:\dev\tools\laya-server-dist\laya_server", [int]$Port = 18798)
$log = "$env:TEMP\laya_smoke_log.jsonl"; $err = "$env:TEMP\laya_smoke_err.txt"; $t = Get-Date
$p = Start-Process "$Dir\laya_server.exe" -PassThru -WindowStyle Hidden -RedirectStandardError $err `
    -ArgumentList "--onnx", "$Dir\model\laya_fp32.onnx", "--model", "$Dir\model", "--root", $Dir, "--log", $log, "--port", "$Port"
$base = "http://127.0.0.1:$Port"; $s = $null
for ($i = 0; $i -lt 180 -and -not $p.HasExited; $i++) {
    try { $s = Invoke-RestMethod "$base/seeds" -TimeoutSec 2; break } catch { Start-Sleep 1 }
}
if ($null -eq $s) { "server did not answer (exited: $($p.HasExited))"; Get-Content $err -Tail 15; if (-not $p.HasExited) { Stop-Process $p -Force }; exit 1 }
"ready after {0:N0} s, seeds: {1}" -f ((Get-Date) - $t).TotalSeconds, ($s.seeds.seed -join ",")
$r = Invoke-RestMethod "$base/reset?seed=$($s.seeds[0].seed)"
"reset ok=$($r.ok) choice=$($r.choice) bot=$($r.bot)"
$t2 = Get-Date
$st = Invoke-RestMethod "$base/step?action=$([uri]::EscapeDataString($r.choice))"
"step ok=$($st.ok) step=$($st.step) next=$($st.choice) in {0:N2} s" -f ((Get-Date) - $t2).TotalSeconds
Invoke-RestMethod "$base/quit" | Out-Null
Start-Sleep 2; "server exited after /quit: $($p.HasExited)"
