#Requires -Version 5.1
<#
.SYNOPSIS
    Installs the required Python environment for the project.
.DESCRIPTION
    This script checks for a compatible Python version (3.10+), creates a virtual
    environment (.venv) if one doesn't exist, and installs dependencies from requirements.txt.
#>

$ErrorActionPreference = 'Stop'
$minPythonVersion = [version]"3.10"
$pythonExe = $null

function Get-PythonVersion($exe) {
    try {
        $versionString = (& $exe --version 2>&1) -join " "
        if ($versionString -match "Python (\d+\.\d+\.\d+)") {
            return [version]$matches[1]
        }
    } catch {
        return [version]"0.0"
    }
    return [version]"0.0"
}

Write-Host ""
Write-Host "============================================="
Write-Host "  Python Environment Setup Script"
Write-Host "============================================="
Write-Host "Checking for a compatible Python version ($minPythonVersion+)..."
Write-Host ""

# --- 1. Locate Python ---
$systemPython = Get-Command python -ErrorAction SilentlyContinue
if ($systemPython) {
    $pythonVersion = Get-PythonVersion $systemPython.Source
    if ($pythonVersion -ge $minPythonVersion) {
        Write-Host "Found compatible system Python: $($systemPython.Source) (version $pythonVersion)"
        $pythonExe = $systemPython.Source
    }
}

# Ask user if not found
if (-not $pythonExe) {
    Write-Warning "No compatible Python found."
    while (-not $pythonExe) {
        $userPath = Read-Host "Enter the full path to Python $minPythonVersion+ (e.g., C:\Python310\python.exe)"
        if (Test-Path $userPath -PathType Leaf) {
            $userVersion = Get-PythonVersion $userPath
            if ($userVersion -ge $minPythonVersion) {
                Write-Host "Using: $userPath (version $userVersion)"
                $pythonExe = $userPath
            } else {
                Write-Warning "Version $userVersion is too old. Try again."
            }
        } else {
            Write-Warning "Invalid path. Try again."
        }
    }
}

# --- 2. Create virtual environment ---
$venvDir = ".venv"
$activatePath = Join-Path $venvDir "Scripts\activate"

if (Test-Path $activatePath) {
    Write-Host "Virtual environment already exists at '$venvDir'."
} else {
    Write-Host "Creating virtual environment at '$venvDir'..."
    try {
        & $pythonExe -m venv $venvDir
        Write-Host "Virtual environment created successfully."
    } catch {
        Write-Error "Failed to create virtual environment. $_"
        pause
        exit 1
    }
}

# --- 3. Install requirements ---
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirementsFile = "requirements.txt"

if (-not (Test-Path $requirementsFile)) {
    Write-Error "requirements.txt not found in the current directory."
    pause
    exit 1
}

Write-Host ""
Write-Host "Installing dependencies from requirements.txt..."
try {
    # Upgrade pip safely
    & $venvPython -m pip install --upgrade pip

    # Install requirements
    & $venvPython -m pip install -r $requirementsFile

    Write-Host ""
    Write-Host "============================================="
    Write-Host " Installation complete. Environment ready."
    Write-Host "=============================================" -ForegroundColor Green
}
catch {
    Write-Error "Failed to install requirements. $_"
    pause
    exit 1
}

Write-Host ""
pause
