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

    Write-Host "[1/3] Running econometrics pipeline..."
    & $pythonCmd "run_pipeline.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Pipeline execution failed with exit code $LASTEXITCODE"
    }

    if ($SkipPdf) {
        Write-Host "PDF build skipped (-SkipPdf)."
        exit 0
    }

    Push-Location "paper"
    try {
        $latexCmd = $null
        foreach ($candidate in @("pdflatex", "xelatex", "lualatex", "tectonic")) {
            if (Get-Command $candidate -ErrorAction SilentlyContinue) {
                $latexCmd = $candidate
                break
            }
        }

        if (-not $latexCmd) {
            Write-Warning "No LaTeX engine found."
            exit 0
        }

        if ($latexCmd -eq "tectonic") {
            Write-Host "[2/3] Building submission manuscript PDF..."
            & $latexCmd "main_submission.tex"
            if ($LASTEXITCODE -ne 0) { throw "Submission build failed with exit code $LASTEXITCODE" }

            Write-Host "[3/3] Building full appendix PDF..."
            & $latexCmd "appendix_full.tex"
            if ($LASTEXITCODE -ne 0) { throw "Appendix build failed with exit code $LASTEXITCODE" }
        } else {
            Write-Host "[2/3] Building submission manuscript PDF..."
            & $latexCmd "-interaction=nonstopmode" "-jobname=main_submission_build" "main_submission.tex" | Out-Null
            & $latexCmd "-interaction=nonstopmode" "-jobname=main_submission_build" "main_submission.tex" | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Submission build failed with exit code $LASTEXITCODE" }

            Write-Host "[3/3] Building full appendix PDF..."
            & $latexCmd "-interaction=nonstopmode" "-jobname=appendix_full_build" "appendix_full.tex" | Out-Null
            & $latexCmd "-interaction=nonstopmode" "-jobname=appendix_full_build" "appendix_full.tex" | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Appendix build failed with exit code $LASTEXITCODE" }

            if (Test-Path ".\main_submission_build.pdf") {
                Copy-Item ".\main_submission_build.pdf" ".\main_submission.pdf" -Force
            }
            if (Test-Path ".\appendix_full_build.pdf") {
                Copy-Item ".\appendix_full_build.pdf" ".\appendix_full.pdf" -Force
            }
        }

        Write-Host "Submission build completed: paper/main_submission.pdf"
        Write-Host "Appendix build completed: paper/appendix_full.pdf"
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
