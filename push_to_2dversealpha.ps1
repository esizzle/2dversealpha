# Pushes main2 to https://github.com/esizzle/2dversealpha.git without the
# 120 MB background.ogg blob that is buried in the old history.
#
# Run from the project folder (the one containing main.py):
#     powershell -ExecutionPolicy Bypass -File .\push_to_2dversealpha.ps1
#
# What it does (main is never touched or checked out):
#   1. saves main2's current history as branch backup-main2
#   2. points origin at 2dversealpha
#   3. squashes everything since 4da05b8 (the last commit WITHOUT the big
#      file) into one commit on main2 -- your files do not change
#   4. pushes main2 and sets it to track origin/main2
# Undo at any time:  git reset --hard backup-main2

$RemoteUrl = "https://github.com/esizzle/2dversealpha.git"
$CleanBase = "4da05b8f938950c16a362765bf7f7c32daed260e"
$Self      = "push_to_2dversealpha.ps1"
$Message   = "2dverse Alpha 0.0.1: audio, settings, journal, mitosis, build setup, attraction fixes"

Set-Location -Path $PSScriptRoot

function Step($text) { Write-Host "`n== $text ==" -ForegroundColor Cyan }
function Fail($text) {
    Write-Host "`nSTOPPED: $text" -ForegroundColor Red
    Write-Host "Nothing was pushed. Your files are untouched; main2 can be restored with: git reset --hard backup-main2" -ForegroundColor Yellow
    exit 1
}

Step "Checking branch"
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne "main2") { Fail "you are on '$branch', not main2. Switch to main2 and run again." }

Step "Saving backup branch backup-main2"
git rev-parse --verify --quiet backup-main2 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "backup-main2 already exists - leaving it as is"
} else {
    git branch backup-main2
    if ($LASTEXITCODE -ne 0) { Fail "could not create backup-main2" }
}

Step "Setting origin -> $RemoteUrl"
git remote get-url origin 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { git remote set-url origin $RemoteUrl } else { git remote add origin $RemoteUrl }
if ($LASTEXITCODE -ne 0) { Fail "could not set the remote" }

Step "Checking Git LFS"
git lfs install
if ($LASTEXITCODE -ne 0) { Fail "Git LFS is not installed (https://git-lfs.com), install it and run again" }

Step "Staging current files"
git add -A -- . ":(exclude)$Self"
if ($LASTEXITCODE -ne 0) { Fail "git add failed" }

$lfsFiles = git lfs ls-files
if (-not ($lfsFiles -match "background.ogg")) {
    Fail "background.ogg is not stored through LFS, so it would go up as a plain file"
}

Step "Squashing history since $($CleanBase.Substring(0,7)) into one commit"
git reset --soft $CleanBase
if ($LASTEXITCODE -ne 0) { Fail "git reset failed" }
git commit -m $Message
if ($LASTEXITCODE -ne 0) { Fail "git commit failed" }

Step "Pushing main2 to 2dversealpha (GitHub may ask you to sign in)"
git push -u origin main2
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nPush failed. Your squashed main2 is intact locally; copy the error above and send it to Claude." -ForegroundColor Red
    exit 1
}

Write-Host "`nDone. main2 is on GitHub and tracks origin/main2 - future pushes are just 'git push'." -ForegroundColor Green
Write-Host "Don't push main or backup-main2: they still contain the 120 MB file." -ForegroundColor Yellow
