# Инструкция по загрузке проекта на GitHub

## Быстрый способ (рекомендуется)

Запустите скрипт `push_to_github.ps1`:

```powershell
.\push_to_github.ps1
```

Скрипт проведет вас через весь процесс загрузки.

## Ручной способ

### Шаг 1: Создайте репозиторий на GitHub

1. Перейдите на https://github.com/new
2. Введите имя репозитория (например, `GEO_Vertical`)
3. **НЕ** инициализируйте репозиторий с README, .gitignore или лицензией (они уже есть в проекте)
4. Нажмите "Create repository"

### Шаг 2: Настройте удаленный репозиторий

Выполните команду (замените `ваш-username` на ваш GitHub username):

```powershell
git remote add origin https://github.com/ваш-username/GEO_Vertical.git
```

Если репозиторий уже был добавлен ранее, обновите URL:

```powershell
git remote set-url origin https://github.com/ваш-username/GEO_Vertical.git
```

### Шаг 3: Переименуйте ветку (опционально)

GitHub по умолчанию использует ветку `main` вместо `master`:

```powershell
git branch -M main
```

### Шаг 4: Отправьте код на GitHub

```powershell
git push -u origin main
```

(или `git push -u origin master`, если не переименовывали ветку)

### Шаг 5: Проверьте результат

Откройте в браузере: `https://github.com/ваш-username/GEO_Vertical`

## Настройка аутентификации

### Вариант 1: Personal Access Token (HTTPS)

1. Перейдите в GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Создайте новый token с правами `repo`
3. При запросе пароля используйте токен вместо пароля

### Вариант 2: SSH ключи

1. Сгенерируйте SSH ключ (если еще нет):
   ```powershell
   ssh-keygen -t ed25519 -C "your_email@example.com"
   ```

2. Добавьте публичный ключ в GitHub:
   - Settings → SSH and GPG keys → New SSH key
   - Скопируйте содержимое файла `~/.ssh/id_ed25519.pub`

3. Используйте SSH URL вместо HTTPS:
   ```powershell
   git remote set-url origin git@github.com:ваш-username/GEO_Vertical.git
   ```

## Важные замечания

### Файлы, которые не попадут в репозиторий

Благодаря `.gitignore`, следующие файлы будут исключены:
- `__pycache__/` - кэш Python
- `*.pyc`, `*.pyo` - скомпилированные файлы Python
- `venv/`, `.venv/` - виртуальные окружения
- `.vscode/`, `.idea/` - настройки IDE
- `*.log` - файлы логов
- Версионные папки вида `0.13.0`, `1.0.0` и т.д.

### Файлы, которые попадут в репозиторий

- Все исходные коды (`.py` файлы)
- Конфигурационные файлы (`requirements.txt`, `.gitignore`)
- Документация (`.md` файлы)
- Шаблоны (`templates/`)
- Тесты (`tests/`)
- База данных `core/db/profiles.db` (если нужно исключить, добавьте в `.gitignore`)

## Дальнейшая работа

После первого пуша, для отправки изменений используйте:

```powershell
git add .
git commit -m "Описание изменений"
git push
```

## Получение последних изменений

Если проект редактируется на нескольких компьютерах:

```powershell
git pull
```

## Полезные команды

- Посмотреть статус: `git status`
- Посмотреть историю коммитов: `git log`
- Посмотреть удаленные репозитории: `git remote -v`
- Посмотреть разницу: `git diff`
