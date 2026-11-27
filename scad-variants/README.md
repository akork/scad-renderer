# scad-variants

Движок рендеринга вариантов OpenSCAD и генератор локальной галереи.

Постоянного watcher больше нет. Каждый запуск обрабатывает **один выбранный
файл (или один указанный каталог) один раз** и завершается.

## Возможности

- поиск текстовых переключателей и построение вариантов;
- рендер PNG и STL за один запуск OpenSCAD;
- Manifold-сборка OpenSCAD с fallback на обычную;
- contact sheet и `manifest.json`;
- HTML-галерея с карточками;
- встроенный просмотр исходника с подсветкой;
- 3D-вьюер и 3D-модалка;
- локальный gallery server;
- слоты OrcaSlicer;
- запуск/фокусировка OrcaSlicer.

## Рендер одного файла

```powershell
python scad_variants.py --once --root "C:\path\to\folder" --only "model.scad"
```

Или через контекстное меню Проводника из `scad-drop`.

Результат:

```text
model.scad
model_renders/
  index.html
  manifest.json
  contact.png
  part-frame.png
  part-frame.stl
```

## Полезные параметры

```text
--once                 совместимость; рендер всегда один
--root PATH            каталог с .scad
--only GLOB            только выбранный файл
--force                перерендерить без кэша
--workers N            параллельные рендеры
--timeout SEC          таймаут одного варианта
--slow-timeout SEC     таймаут тяжёлых вариантов
--stl-mode MODE        printable | all | none
--no-mesh              только PNG
--no-auto-open         не открывать галерею
--no-notify            без Windows-уведомления
--openscad PATH        явный путь к OpenSCAD
```

## Галерея

`index.html` содержит:

- превью каждого варианта;
- клик по основной картинке — 3D;
- клик по иконке — картинка на весь экран;
- кнопки слотов Orca и отправку STL;
- выбор OrcaSlicer / Bambu Lab (Bambu пока заглушка);
- **«Открыть слайсер»**;
- копирование путей к PNG и STL;
- кнопку **«Код»**: слева 1/3 — варианты, справа 2/3 — исходник с подсветкой.

## Gallery server

Сервер:

```text
python -m scadvariants.gallery_server --serve --port 8765
```

Он нужен для:

- 3D-вьюера;
- отдачи STL;
- просмотра исходника;
- стабильного URL галереи.

Обычно запускается автоматически через `ensure_server()` и живёт на
`http://127.0.0.1:8765`.

## 3D

`viewer/viewer.html` — Three.js-вьюер:

- вращение, масштаб, сдвиг;
- кнопки сброса и авто-вращения;
- закрытие по `Esc`, кнопке или короткому клику без перетаскивания.

3D открывается в модальном окне внутри галереи. Из файловой системы
используется локальный сервер, чтобы браузер мог загрузить STL.

## Слоты и слайсер

- `slots.py` — реестр стабильных STL-слотов;
- `slot_action.py` — обработчик `scad-slot:`;
- `slicer_action.py` — фокусировка/запуск OrcaSlicer;
- `open_gallery.py --ensure` — запуск локального сервера для 3D из файловой галереи.

## Зависимости

- Python 3.10+;
- Pillow (`requirements.txt`);
- OpenSCAD;
- Microsoft Edge для превью.

## Тесты

```powershell
python -m unittest discover -s tests
```

## Состояние

`state/` содержит кэш, логи, профили браузера и временные файлы. В Git не
входит.
