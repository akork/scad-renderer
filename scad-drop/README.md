# scad-drop

Windows-обвязка для рендерера `scad-variants`: пункт в контекстном меню
Проводника и трей **SCAD Render**.

Постоянного watcher папок нет. Ни `Downloads`, ни `SCAD` не отслеживаются.
Рендер запускается только для выбранного файла.

## Контекстное меню

Установка:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-context-menu.ps1
```

В Проводнике появляется пункт:

```text
Отрендерить SCAD (PNG + STL)
```

Он вызывает:

```text
pythonw scad_drop.py --render-file "<path>"
```

`scad_drop.py` запускает движок:

```text
scad-variants/scad_variants.py --once --root "<parent>" --only "<file>"
```

Результат создаётся рядом с исходником:

```text
<name>_renders/index.html
```

После рендера галерея открывается в браузере. Никакого копирования в `SCAD`
и никакого автоматического рендера других файлов нет.

## Трей

Установка автозапуска:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-tray-autostart.ps1
```

Трей запускается через `tray-launch.vbs` → `tray-host.ps1`, без видимого окна
терминала. Host перезапускает дочерний процесс трея по команде
**«Перезагрузить программу»**.

В меню трея:

- **Активные задачи** — прогресс текущих рендеров.
- **Автоматически открывать результаты в отдельном браузере** — открытие
  готовой галереи.
- **Недавние рендеры** — имя рендера и дата/время.
  - клик по названию — превью в Edge;
  - клик по иконке папки — открыть папку рендера.
- **Сервер: ...** — состояние локального gallery server.
- **Перезагрузить программу**, **Выход**.

Превью открывается в отдельном профиле Edge:

```text
scad-variants/state/edge-preview-profile
```

Контроллер ищет уже открытую вкладку рендера, переключается на неё и выводит
окно Edge на передний план. Если вкладки нет — открывает новую вкладку в том же
окне.

## Файлы

```text
scad_drop.py              контекстный запуск и ожидание галереи
scad-tray.ps1             WinForms-трей
tray-host.ps1             скрытый host и перезапуск
tray-launch.vbs           скрытый запуск host
start-scad-tray.vbs       ручной запуск трея
install-context-menu.ps1  установка пункта Проводника
install-tray-autostart.ps1 установка задачи автозапуска
render-scad.cmd           ручной запуск для отладки
```

## Протоколы

Контекстный запуск и трей используют протоколы, которые ставит
`scad-variants/install-viewer-protocol.ps1`:

- `scad-gallery:`;
- `scad-slot:`;
- `scad-slicer:`;
- `scad-embed:`.

## Тесты

```powershell
python -m unittest discover -s tests
```

## Состояние

`state/` содержит логи, состояние трея и кэш протоколов. В Git он не входит.
