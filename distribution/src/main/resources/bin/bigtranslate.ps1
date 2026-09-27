# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0.

[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('setup', 'start', 'stop', 'restart', 'status', 'translate',
        'reset', 'help')]
    [string] $Command,

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]] $Arguments,

    [string] $BigTranslateHome = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$BigTranslateHome = [IO.Path]::GetFullPath($BigTranslateHome)
$portableHome = $BigTranslateHome -replace '\\', '/'

function Resolve-Uv {
    $uv = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($uv) { return $uv.Source }
    $winget = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') `
        -Filter uv.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($winget) { return $winget.FullName }
    throw 'uv was not found. Install it with: winget install astral-sh.uv'
}

function Invoke-Setup {
    $uv = Resolve-Uv
    $env:Path = @(
        [Environment]::GetEnvironmentVariable('Path', 'Machine'),
        [Environment]::GetEnvironmentVariable('Path', 'User'),
        $env:Path) -join ';'
    $venv = Join-Path $BigTranslateHome '.venv'
    if (-not (Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
        & $uv venv $venv --python 3.11
        if ($LASTEXITCODE -ne 0) { throw 'Unable to create the BigTranslate virtual environment.' }
    }
    # The POSIX pipeline scripts use /usr/bin/env python3. Windows virtual
    # environments provide python.exe only, so expose the conventional name
    # inside the same Scripts directory Git Bash already receives on PATH.
    $python = Join-Path $venv 'Scripts\python.exe'
    $python3 = Join-Path $venv 'Scripts\python3.exe'
    if (-not (Test-Path -LiteralPath $python3)) {
        Copy-Item -LiteralPath $python -Destination $python3
    }
    & $uv pip install --python (Join-Path $venv 'Scripts\python.exe') `
        -r (Join-Path $BigTranslateHome 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install BigTranslate Python dependencies.' }

    $pantoglossSource = if ($env:PANTOGLOSS_SOURCE) {
        $env:PANTOGLOSS_SOURCE
    } elseif (Test-Path -LiteralPath (Join-Path (Split-Path $BigTranslateHome -Parent) 'pantogloss\pyproject.toml')) {
        (Join-Path (Split-Path $BigTranslateHome -Parent) 'pantogloss') + '[server]'
    } else { 'pantogloss[server]>=1.0.0rc1' }
    # The floor is in the specifier, not a --prerelease flag, because that is
    # what makes uv accept it: a bare name resolves to the newest *final*
    # release, which is 0.25.0 while 1.0.0rc1 is the newest thing on PyPI, and
    # 0.25.0 imports the Unix-only resource module and does not start here at
    # all. A constraint that names a pre-release admits pre-releases for that
    # requirement -- measured with uv 0.11.30: '>=0.19' resolves 0.25.0 and
    # '>=1.0.0rc1' resolves 1.0.0rc1.
    & $uv pip install --python (Join-Path $venv 'Scripts\python.exe') $pantoglossSource
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install Pantogloss with its server dependencies.' }
    Write-Host "BigTranslate setup complete: $venv"
}

function Invoke-PosixCommand {
    $gitBin = Join-Path $env:ProgramFiles 'Git\bin'
    $sh = Join-Path $gitBin 'sh.exe'
    if (-not (Test-Path -LiteralPath $sh)) {
        throw 'Git Bash is required for BigTranslate pipeline commands.'
    }
    $env:Path = "$gitBin;$(Join-Path $env:ProgramFiles 'Git\usr\bin');$env:Path"
    foreach ($javaHome in @(
        $env:JAVA_HOME,
        [Environment]::GetEnvironmentVariable('JAVA_HOME', 'User'),
        [Environment]::GetEnvironmentVariable('JAVA_HOME', 'Machine'))) {
        if ($javaHome -and (Test-Path -LiteralPath (Join-Path $javaHome 'bin\java.exe'))) {
            $env:JAVA_HOME = $javaHome
            $env:JRE_HOME = $javaHome
            $env:Path = "$(Join-Path $javaHome 'bin');$($env:Path)"
            break
        }
    }
    if (-not $env:JAVA_HOME) {
        throw 'Java was not found. Set JAVA_HOME to a JDK installation.'
    }
    $env:BIGTRANSLATE_HOME = $portableHome
    $env:OODT_HOME = $portableHome
    $env:OODT_BASE = $portableHome
    $env:PYTHON = "$portableHome/.venv/Scripts/python.exe"
    $env:PYTHON_EXECUTABLE = $env:PYTHON
    $script = "$portableHome/bin/bigtranslate"
    & $sh $script $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "BigTranslate $Command failed with exit code $LASTEXITCODE." }
}

$oodt = Join-Path $PSScriptRoot 'oodt.ps1'
switch ($Command) {
    'setup' { Invoke-Setup }
    'start' { & $oodt start -OodtHome $BigTranslateHome }
    'stop' { & $oodt stop -OodtHome $BigTranslateHome }
    'restart' { & $oodt restart -OodtHome $BigTranslateHome }
    'status' { & $oodt status -OodtHome $BigTranslateHome }
    'help' { Write-Host 'Use: bigtranslate.ps1 setup|start|stop|restart|status|translate|reset|help' }
    default { Invoke-PosixCommand }
}
