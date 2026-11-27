# SCAD Renderer

Текущая версия: **1.1.2-dev.6** (`VERSION` 1.1.2, `BUILD` 6) · [История изменений](CHANGELOG.md) · [GitHub](https://github.com/akork/scad-renderer)

Локальный рендерер вариантов OpenSCAD для Windows: контекстное меню Проводника,
галерея результатов, 3D-просмотр, просмотр исходного кода, слоты OrcaSlicer и
трей-панель.

Проект не отслеживает папки. Рендер запускается **из контекстного меню для
любого `.scad` файла в любом месте файловой системы**. Результат создаётся
рядом с исходником:

```text
C:\Любая\Папка\
  my_model.scad
  my_model_renders\
    index.html          ← галерея
    manifest.json
    contact.png
    part-frame.png
    part-frame.stl
```

## Что умеет

- Находит текстовые переключатели в `.scad` и рендерит все варианты.
- Делает PNG-превью и STL за один запуск OpenSCAD.
- Собирает HTML-галерею с карточками вариантов.
- Показывает исходный `.scad` в галерее с подсветкой синтаксиса.
- Открывает 3D-просмотр во всплывающем окне прямо в галерее.
- Позволяет отправить STL в стабильный слот OrcaSlicer.
- Открывает OrcaSlicer: переключает уже запущенное окно или запускает его.
- Открывает превью рендера в отдельном Edge-профиле, переиспользуя вкладку.
- Показывает прогресс рендера и список недавних рендеров в трее.

## Два компонента

### `scad-variants`

Движок:

- анализ `.scad`;
- запуск OpenSCAD и рендер PNG/STL;
- галерея, contact sheet, `manifest.json`;
- локальный HTTP-сервер на `127.0.0.1:8765`;
- 3D-вьюер;
- просмотр кода;
- слоты OrcaSlicer;
- тесты.

### `scad-drop`

Windows-обвязка:

- пункт **«Отрендерить SCAD (PNG + STL)»** в контекстном меню;
- запуск движка для выбранного файла;
- трей **SCAD Render**;
- недавние рендеры, открытие папки и превью;
- скрытый автозапуск;
- установка контекстного меню, протоколов и ярлыка.

## Как это работает

```text
Проводник
  → scad-drop/scad_drop.py --render-file <файл>
    → scad-variants/scad_variants.py --once --root <папка> --only <файл>
      → <файл>_renders/
        → галерея, 3D, код, слоты
```

`scad-drop` не рендерит сам и не знает деталей OpenSCAD.
`scad-variants` не знает про Проводник и трей.

## Требования

- Windows 11;
- Python 3.10+ с Pillow;
- OpenSCAD (желательно Manifold-сборка; обычная установка тоже поддерживается);
- Microsoft Edge.

На текущей машине используется Python из DeepSeek Harness:

```text
%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe
```

## Установка

Клонировать репозиторий так, чтобы `scad-variants/` и `scad-drop/` были
соседними папками:

```powershell
git clone https://github.com/akork/scad-renderer.git
```

Установить контекстное меню:

```powershell
powershell -ExecutionPolicy Bypass -File .\scad-drop\install-context-menu.ps1
```

Установить локальные протоколы:

```powershell
powershell -ExecutionPolicy Bypass -File .\scad-variants\install-viewer-protocol.ps1
```

Установить автозапуск трея:

```powershell
powershell -ExecutionPolicy Bypass -File .\scad-drop\install-tray-autostart.ps1
```

При необходимости пересоздать ярлык и AUMID уведомлений:

```powershell
powershell -ExecutionPolicy Bypass -File .\scad-variants\install-notifications.ps1
```

## Использование

1. Нажать правой кнопкой на `.scad` в Проводнике.
2. Выбрать **«Отрендерить SCAD (PNG + STL)»**.
3. Дождаться галереи.
4. В галерее:
   - клик по основной части картинки — 3D;
   - клик по иконке в правом верхнем углу — картинка на весь экран;
   - кнопка **«Код»** — исходник с подсветкой;
   - кнопки слотов — отправка STL в OrcaSlicer;
   - **«Открыть слайсер»** — фокус на OrcaSlicer или его запуск.

## Структура репозитория

```text
.
├─ scad-variants/       движок, галерея, сервер, 3D, тесты
├─ scad-drop/           контекстное меню, трей, Edge-превью
├─ CHANGELOG.md         полная история изменений
├─ VERSION              текущая версия
├─ AGENTS.md            правила проекта для агента
└─ README.md
```

`scad-variants/state/`, `scad-drop/state/`, профили браузеров, сгенерированные
рендеры, `SCAD/`, `orca-slots/`, `tools/` и `deliverables/` в Git не входят.

## Тесты

```powershell
cd scad-variants
python -m unittest discover -s tests

cd ..\scad-drop
python -m unittest discover -s tests
```

## Git и версии

- версия хранится в `VERSION`;
- подробная история — в `CHANGELOG.md`;
- коммиты короткие, вида `vX.Y.Z: ...`;
- облако обновляется пакетно: после 5 версий или 14 дней, либо по запросу;
- перед push локальные minor-коммиты схлопываются в один релизный коммит;
- тег ставится только на релизный коммит.

Репозиторий: <https://github.com/akork/scad-renderer> (private).

## Документация компонентов

- [`scad-variants/README.md`](scad-variants/README.md) — движок, CLI, галерея, сервер.
- [`scad-drop/README.md`](scad-drop/README.md) — контекстное меню, трей, Edge.
- [`CHANGELOG.md`](CHANGELOG.md) — история версий.
