# Публикация в GitHub — Evrasia2050_game

Целевой репозиторий: https://github.com/AntonDozhdikov/Evrasia2050_game

Структура первой рабочей версии находится **в корне** пакета `EURASIA_2050_STAGE3_GITHUB_READY.zip`. Все папки загружаются с сохранением вложенности, особенно `.github/workflows/`.

## Если используется GitHub Desktop

1. Клонировать репозиторий `AntonDozhdikov/Evrasia2050_game` на компьютер.
2. Распаковать `EURASIA_2050_STAGE3_GITHUB_READY.zip` в папку клонированного репозитория с сохранением каталогов, без удаления уже имеющихся пользовательских файлов.
3. Проверить список изменений в GitHub Desktop и создать коммит `Stage 3: browser replay of V4.7`.
4. Выполнить `Push origin`.
5. В Settings → Pages выбрать GitHub Actions. После успешного выполнения workflow открыть https://antondozhdikov.github.io/Evrasia2050_game/.

## Если используется командная строка Git

```bash
git clone https://github.com/AntonDozhdikov/Evrasia2050_game.git
cd Evrasia2050_game
# распаковать ZIP в этот каталог, сохранив .github/workflows
git add .
git commit -m "Stage 3: V4.7 browser replay and frozen scientific data"
git push origin HEAD:main
```

Не выполнять `git push --force`: текущая история репозитория должна сохраняться.

## Проверка после публикации

- GitHub Actions → `Validate and deploy Eurasia 2050` — успешный запуск.
- Страница загружается, доступны 20 сценариев, четыре стратегии и три начальных числа.
- `node tests/verify_data.cjs` и `python tests/verify_archive.py` завершаются без ошибок.

## Статус

Пакет подготовлен и локально закоммичен; **прямой push в удаленный репозиторий этой среды не подтвержден**. URL GitHub Pages указан как предполагаемый адрес и станет действующим только после публикации и активации Pages.
