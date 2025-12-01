# Simple script to push to GitHub
# Usage: .\push_to_github_simple.ps1

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Push GEO_Vertical project to GitHub" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Git not found" -ForegroundColor Red
    exit 1
}

# Get repository URL
Write-Host "Enter your GitHub repository URL" -ForegroundColor Yellow
Write-Host "Example: https://github.com/username/GEO_Vertical.git" -ForegroundColor Gray
$repoUrl = Read-Host "Repository URL"

if ([string]::IsNullOrWhiteSpace($repoUrl)) {
    Write-Host "ERROR: URL cannot be empty" -ForegroundColor Red
    exit 1
}

# Check current branch
$currentBranch = git branch --show-current
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Cannot determine current branch" -ForegroundColor Red
    exit 1
}

Write-Host "Current branch: $currentBranch" -ForegroundColor Green

# Check existing remote
try {
    $existingRemote = git remote get-url origin 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "WARNING: Remote already exists: $existingRemote" -ForegroundColor Yellow
        $update = Read-Host "Replace it? (y/n)"
        if ($update -eq "y" -or $update -eq "Y") {
            git remote set-url origin $repoUrl
            Write-Host "Remote URL updated" -ForegroundColor Green
        } else {
            $repoUrl = $existingRemote
        }
    }
} catch {
    git remote add origin $repoUrl
    Write-Host "Remote added" -ForegroundColor Green
}

# Rename branch to main if needed
if ($currentBranch -eq "master") {
    Write-Host ""
    $rename = Read-Host "Rename branch to 'main'? (y/n)"
    if ($rename -eq "y" -or $rename -eq "Y") {
        git branch -M main
        $currentBranch = "main"
        Write-Host "Branch renamed to 'main'" -ForegroundColor Green
    }
}

# Check for uncommitted changes
Write-Host ""
Write-Host "Checking for changes..." -ForegroundColor Cyan
$status = git status --porcelain
if ($status) {
    Write-Host "Uncommitted changes found:" -ForegroundColor Yellow
    git status --short
    $commit = Read-Host "Commit before push? (y/n)"
    if ($commit -eq "y" -or $commit -eq "Y") {
        $commitMessage = Read-Host "Enter commit message (or press Enter for default)"
        if ([string]::IsNullOrWhiteSpace($commitMessage)) {
            $commitMessage = "Update: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        }
        git add .
        git commit -m $commitMessage
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Commit failed" -ForegroundColor Red
            exit 1
        }
        Write-Host "Changes committed" -ForegroundColor Green
    }
}

# Push to GitHub
Write-Host ""
Write-Host "Pushing to GitHub..." -ForegroundColor Cyan
Write-Host "Branch: $currentBranch" -ForegroundColor Gray
Write-Host "Repository: $repoUrl" -ForegroundColor Gray
Write-Host ""

git push -u origin $currentBranch

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "Successfully pushed to GitHub!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Repository URL:" -ForegroundColor Cyan
    $displayUrl = $repoUrl -replace "\.git$", ""
    $displayUrl = $displayUrl -replace "git@github\.com:", "https://github.com/"
    Write-Host $displayUrl -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "ERROR: Push failed" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possible reasons:" -ForegroundColor Yellow
    Write-Host "1. Repository not created on GitHub" -ForegroundColor Gray
    Write-Host "2. Wrong repository URL" -ForegroundColor Gray
    Write-Host "3. Authentication issues" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Instructions:" -ForegroundColor Yellow
    Write-Host "1. Create new repository at https://github.com/new" -ForegroundColor White
    Write-Host "2. Do NOT initialize with README, .gitignore or license" -ForegroundColor White
    Write-Host "3. Run this script again with correct URL" -ForegroundColor White
    Write-Host ""
    exit 1
}
