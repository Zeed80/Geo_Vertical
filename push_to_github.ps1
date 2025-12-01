# -*- coding: utf-8 -*-
# Скрипт для загрузки проекта на GitHub
# Использование: .\push_to_github.ps1

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Загрузка проекта GEO_Vertical на GitHub" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Проверка наличия git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ОШИБКА: Git не установлен или не найден в PATH" -ForegroundColor Red
    exit 1
}

# Запрос URL репозитория GitHub
Write-Host "Введите URL вашего репозитория на GitHub" -ForegroundColor Yellow
Write-Host "Пример: https://github.com/ваш-username/GEO_Vertical.git" -ForegroundColor Gray
Write-Host "Или: git@github.com:ваш-username/GEO_Vertical.git" -ForegroundColor Gray
$repoUrl = Read-Host "URL репозитория"

if ([string]::IsNullOrWhiteSpace($repoUrl)) {
    Write-Host "ОШИБКА: URL репозитория не может быть пустым" -ForegroundColor Red
    exit 1
}

# Проверка текущего состояния
Write-Host ""
Write-Host "Проверка текущего состояния репозитория..." -ForegroundColor Cyan
$currentBranch = git branch --show-current
if ($LASTEXITCODE -ne 0) {
    Write-Host "ОШИБКА: Не удалось определить текущую ветку" -ForegroundColor Red
    exit 1
}

Write-Host "Текущая ветка: $currentBranch" -ForegroundColor Green

# Проверка наличия удаленного репозитория
$existingRemote = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "ВНИМАНИЕ: Удаленный репозиторий уже настроен: $existingRemote" -ForegroundColor Yellow
    $update = Read-Host "Заменить его на новый? (y/n)"
    if ($update -eq "y" -or $update -eq "Y") {
        git remote set-url origin $repoUrl
        Write-Host "URL удаленного репозитория обновлен" -ForegroundColor Green
    } else {
        Write-Host "Используется существующий репозиторий" -ForegroundColor Gray
        $repoUrl = $existingRemote
    }
} else {
    git remote add origin $repoUrl
    Write-Host "Удаленный репозиторий добавлен" -ForegroundColor Green
}

# Переименование ветки в main (если используется master)
if ($currentBranch -eq "master") {
    Write-Host ""
    $rename = Read-Host "Использовать ветку 'main' вместо 'master'? (y/n)"
    if ($rename -eq "y" -or $rename -eq "Y") {
        git branch -M main
        $currentBranch = "main"
        Write-Host "Ветка переименована в 'main'" -ForegroundColor Green
    }
}

# Проверка наличия незакоммиченных изменений
Write-Host ""
Write-Host "Проверка изменений..." -ForegroundColor Cyan
$status = git status --porcelain
if ($status) {
    Write-Host "Обнаружены незакоммиченные изменения:" -ForegroundColor Yellow
    git status --short
    $commit = Read-Host "Закоммитить их перед отправкой? (y/n)"
    if ($commit -eq "y" -or $commit -eq "Y") {
        $commitMessage = Read-Host "Введите сообщение коммита (или нажмите Enter для сообщения по умолчанию)"
        if ([string]::IsNullOrWhiteSpace($commitMessage)) {
            $commitMessage = "Update: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        }
        git add .
        git commit -m $commitMessage
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ОШИБКА: Не удалось создать коммит" -ForegroundColor Red
            exit 1
        }
        Write-Host "Изменения закоммичены" -ForegroundColor Green
    }
}

# Отправка на GitHub
Write-Host ""
Write-Host "Отправка кода на GitHub..." -ForegroundColor Cyan
Write-Host "Используется ветка: $currentBranch" -ForegroundColor Gray
Write-Host "Репозиторий: $repoUrl" -ForegroundColor Gray
Write-Host ""

git push -u origin $currentBranch

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "Проект успешно загружен на GitHub!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Ваш репозиторий доступен по адресу:" -ForegroundColor Cyan
    $displayUrl = $repoUrl -replace "\.git$", ""
    $displayUrl = $displayUrl -replace "git@github\.com:", "https://github.com/"
    $displayUrl = $displayUrl -replace "https://github\.com/", "https://github.com/"
    Write-Host $displayUrl -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "ОШИБКА при отправке на GitHub" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Возможные причины:" -ForegroundColor Yellow
    Write-Host "1. Репозиторий еще не создан на GitHub" -ForegroundColor Gray
    Write-Host "2. Неправильный URL репозитория" -ForegroundColor Gray
    Write-Host "3. Проблемы с аутентификацией" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Инструкция:" -ForegroundColor Yellow
    Write-Host "1. Создайте новый репозиторий на https://github.com/new" -ForegroundColor White
    Write-Host "2. НЕ инициализируйте его с README, .gitignore или лицензией" -ForegroundColor White
    Write-Host "3. Запустите этот скрипт снова с правильным URL" -ForegroundColor White
    Write-Host ""
    exit 1
}
