# Install Nocek, or update it, on Windows. In a PowerShell window:
#
#   irm https://raw.githubusercontent.com/kazek/nocek/main/install.ps1 | iex
#
# or from the Start menu's search box, the Run box (Win+R) or a command prompt:
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/kazek/nocek/main/install.ps1 | iex"
#
# Installs uv if it is missing (it brings the Python Nocek needs), then Nocek with the
# build of PyTorch that suits this computer, puts Nocek in the Start menu and starts it.
# For testing: NOCEK_PACKAGE installs something else in Nocek's place, such as a wheel;
# NOCEK_NO_START leaves Nocek unstarted.

# No "Stop" for errors throughout: Windows PowerShell 5.1 would then take uv's progress
# messages, which it writes to stderr, for errors. Each step's outcome is checked instead.

$package = if ($env:NOCEK_PACKAGE) { $env:NOCEK_PACKAGE } else { "nocek" }

function Say($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Cyan
}

# Where uv's installer puts it; a window opened before then does not know of it yet.
function Find-Uv {
    @(
        (Get-Command uv -ErrorAction SilentlyContinue).Source,
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

$uv = Find-Uv
if (-not $uv) {
    Say "Installing uv, which installs Nocek and the Python it needs"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 -ErrorAction Stop | Invoke-Expression
    $uv = Find-Uv
    if (-not $uv) {
        throw "uv was installed, but not where expected; open a new PowerShell window and run this again."
    }
}

Say "Installing Nocek (the first time this downloads about 1 GB)"
& $uv tool install --upgrade --python 3.13 --torch-backend auto $package
if ($LASTEXITCODE -ne 0) { throw "Nocek could not be installed." }
# Lets new windows find `nocek`.
& $uv tool update-shell | Out-Null

$nocek = Join-Path (& $uv tool dir --bin).Trim() "nocek.exe"
& $nocek shortcut
if ($LASTEXITCODE -ne 0) { throw "The Start menu shortcut could not be made." }

if (-not $env:NOCEK_NO_START) {
    Say "Starting Nocek; it opens in your browser"
    Start-Process -FilePath $nocek -WindowStyle Hidden
}

Say "Done. Start Nocek from the Start menu from now on."
Write-Host "If an older Nocek was running, quit it (Quit, top right) and start it again."
