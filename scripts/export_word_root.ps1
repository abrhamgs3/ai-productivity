$ErrorActionPreference = "Stop"

function Add-WordPageNumbers {
    param([string[]]$DocPaths)

    try {
        $word = New-Object -ComObject Word.Application
    }
    catch {
        Write-Warning "Microsoft Word COM automation is unavailable. Skipping page numbering in .docx exports."
        return
    }

    $word.Visible = $false

    foreach ($path in $DocPaths) {
        if (-not (Test-Path $path)) {
            continue
        }

        $fullPath = (Resolve-Path $path).Path
        $doc = $null
        try {
            $doc = $word.Documents.Open($fullPath)
            # 1 = wdHeaderFooterPrimary, 2 = wdAlignPageNumberRight, $true includes first page
            $doc.Sections.Item(1).Footers.Item(1).PageNumbers.Add(2, $true) | Out-Null
            $doc.Save()
            Write-Host "Added page numbers: $path"
        }
        catch {
            Write-Warning "Could not add page numbers to $path : $($_.Exception.Message)"
        }
        finally {
            if ($doc -ne $null) {
                $doc.Close()
            }
        }
    }

    $word.Quit()
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..")
$paperDir = Join-Path $root "paper"

Push-Location $paperDir
try {
    Write-Host "[1/3] Building root paper PDF..."
    pdflatex -interaction=nonstopmode -halt-on-error main.tex | Out-Null
    pdflatex -interaction=nonstopmode -halt-on-error main.tex | Out-Null

    Write-Host "[2/3] Exporting root paper to Word..."
    pandoc main.tex -o main.docx --resource-path=".;sections;../tables;../figures"

    if (Test-Path "main_submission.tex") {
        Write-Host "[3/3] Exporting submission split to Word..."
        pandoc main_submission.tex -o main_submission.docx --resource-path=".;sections_submission;../tables;../figures"
    }
    if (Test-Path "appendix_full.tex") {
        pandoc appendix_full.tex -o appendix_full.docx --resource-path=".;sections;../tables;../figures"
    }

    Add-WordPageNumbers @("main.docx", "main_submission.docx", "appendix_full.docx")

    Write-Host "Export completed."
    Write-Host "Created files (if source exists):"
    Write-Host " - paper/main.docx"
    Write-Host " - paper/main_submission.docx"
    Write-Host " - paper/appendix_full.docx"
}
finally {
    Pop-Location
}
