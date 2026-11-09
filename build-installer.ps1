param(
    [string]$Python = "python",
    [string]$Version = "1.0.0",
    [switch]$SkipDependencies,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$WindowsBuildDir = Join-Path $ProjectRoot "build\windows"
$DistDir = Join-Path $ProjectRoot "dist"
$WorkDir = Join-Path $ProjectRoot "build\pyinstaller"
$SpecFile = Join-Path $WindowsBuildDir "FECArcade.spec"
$InstallerScript = Join-Path $WindowsBuildDir "installer.iss"
$Executable = Join-Path $DistDir "FECArcade\FECArcade.exe"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "O comando falhou com código $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

function Find-InnoCompiler {
    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }
    return $null
}

Push-Location $ProjectRoot
try {
    if (-not $SkipDependencies) {
        Invoke-Checked $Python @("-m", "pip", "install", "-r", "requirements.txt")
        Invoke-Checked $Python @("-m", "pip", "install", "-r", "requirements-build.txt")
    }

    Invoke-Checked $Python @("build\windows\make_icon.py")

    # Grava a versão no recurso do executável (Propriedades > Detalhes)
    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        throw "Versão inválida '$Version' (use o formato 1.2.3)."
    }
    $VersionFile = Join-Path $WindowsBuildDir "version_info.txt"
    $VersionTuple = ($Version.Split('.') + '0') -join ', '
    $VersionText = (Get-Content $VersionFile -Raw) `
        -replace '(filevers|prodvers)=\([^)]*\)', "`$1=($VersionTuple)" `
        -replace "StringStruct\('(FileVersion|ProductVersion)', '[^']*'\)", "StringStruct('`$1', '$Version')"
    [System.IO.File]::WriteAllText($VersionFile, $VersionText)  # UTF-8 sem BOM

    Remove-Item (Join-Path $DistDir "FECArcade") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $WorkDir -Recurse -Force -ErrorAction SilentlyContinue

    Invoke-Checked $Python @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath", $DistDir,
        "--workpath", $WorkDir,
        $SpecFile
    )

    if (-not (Test-Path $Executable)) {
        throw "O executável não foi criado: $Executable"
    }
    # O executável não tem console: Start-Process -Wait garante que o teste
    # termine e que o código de saída seja o dele.
    $SelfTest = Start-Process -FilePath $Executable -ArgumentList "--self-test" -Wait -PassThru -NoNewWindow
    if ($SelfTest.ExitCode -ne 0) {
        throw "O autoteste do executável falhou (código $($SelfTest.ExitCode))."
    }
    Write-Host "Executável validado: $Executable" -ForegroundColor Green

    if ($SkipInstaller) {
        Write-Host "Build concluído sem instalador (-SkipInstaller)." -ForegroundColor Yellow
        return
    }

    $InnoCompiler = Find-InnoCompiler
    if (-not $InnoCompiler) {
        throw "Inno Setup 6 não encontrado. Instale por https://jrsoftware.org/isdl.php e execute novamente."
    }

    $Installer = Join-Path $DistDir "installer\FECArcade-Setup-$Version.exe"
    $ChecksumFile = "$Installer.sha256"
    Remove-Item $Installer, $ChecksumFile -Force -ErrorAction SilentlyContinue

    Invoke-Checked $InnoCompiler @("/DAppVersion=$Version", $InstallerScript)

    if (-not (Test-Path $Installer)) {
        throw "O instalador não foi criado: $Installer"
    }
    $Hash = (Get-FileHash $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash *$(Split-Path $Installer -Leaf)" | Set-Content $ChecksumFile -Encoding ascii
    Write-Host "Instalador criado: $Installer" -ForegroundColor Green
    Write-Host "SHA-256: $Hash" -ForegroundColor Green
}
finally {
    Pop-Location
}
