Param(
    [switch]$SkipPdf
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot

try {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $pythonCmd = $venvPython
    } else {
        $pythonCmd = "python"
    }

    Write-Host "[1/2] Running econometrics pipeline..."
    & $pythonCmd "run_pipeline.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Pipeline execution failed with exit code $LASTEXITCODE"
    }

    if ($SkipPdf) {
        Write-Host "PDF build skipped (-SkipPdf)."
        exit 0
    }

    Write-Host "[2/2] Building paper PDF..."
    Push-Location "paper"
    try {
        $jobName = "main_build"
        $latexCmd = $null
        foreach ($candidate in @("pdflatex", "xelatex", "lualatex", "tectonic")) {
            if (Get-Command $candidate -ErrorAction SilentlyContinue) {
                $latexCmd = $candidate
                break
            }
        }

        if (-not $latexCmd) {
            Write-Warning "No LaTeX engine found (pdflatex/xelatex/lualatex/tectonic). Pipeline outputs are ready; install a TeX engine to build PDF."
            exit 0
        }

        if ($latexCmd -eq "tectonic") {
            & $latexCmd "main.tex"
            if ($LASTEXITCODE -ne 0) {
                throw "Tectonic build failed with exit code $LASTEXITCODE"
            }
        } else {
            & $latexCmd "-interaction=nonstopmode" "-jobname=$jobName" "main.tex" | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "First LaTeX pass returned exit code $LASTEXITCODE; continuing to second pass for reference resolution."
            }
            & $latexCmd "-interaction=nonstopmode" "-jobname=$jobName" "main.tex" | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Second LaTeX pass failed with exit code $LASTEXITCODE"
            }

            $builtPdf = Join-Path (Get-Location) "$jobName.pdf"
            $targetPdf = Join-Path (Get-Location) "main.pdf"
            if (Test-Path $builtPdf) {
                try {
                    Copy-Item -Path $builtPdf -Destination $targetPdf -Force
                    Write-Host "PDF build completed: paper/main.pdf"
                } catch {
                    Write-Warning "Built $jobName.pdf, but could not overwrite main.pdf (likely open/locked)."
                    Write-Host "PDF build completed: paper/$jobName.pdf"
                }
            }
        }

        if ($latexCmd -eq "tectonic") {
            Write-Host "PDF build completed: paper/main.pdf"
        }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
