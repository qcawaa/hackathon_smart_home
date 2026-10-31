# Ujin Smart Lab

Ujin Smart Lab — локальный симулятор умного здания для демо Ujin. В нём можно смотреть на устройства из starter pack, менять их writable-сигналы, собирать виртуальные устройства из деклараций и связывать устройства сценариями. Основной сценарий демонстрации — датчик протечки включает свет.

LOCAL режим работает без сети и учётных данных Ujin. LIVE использует существующий клиент из `emulators/ujin_client.py`; учётные данные хранятся только в backend `.env`. React Flow служит редактором сценария, а исполнение ограничено нормализованной моделью триггера, условий и действий.

## Архитектура

```text
React + Vite + React Flow
        │ REST / WebSocket
        ▼
FastAPI ─ DeviceManager ─ emulators/ (ядро starter pack)
        │        │
        │        └─ EventBus ─ ScenarioEngine ─ DeviceManager
        ├─ JSON Storage (data/*.json)
        └─ UjinAdapter ─ emulators/ujin_client.py
```

## Запуск backend

Нужен Python 3.10 или новее.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --app-dir .
```

Backend доступен на `http://localhost:8000`; проверка: `http://localhost:8000/api/health`.

## Запуск frontend

Нужен Node.js 20 или новее.

```powershell
cd frontend
npm install
npm run dev
```

Откройте `http://localhost:5173`.

## Демо «Протечка → Свет»

1. Откройте **Сценарии** и создайте сценарий: событие `Датчик протечки / leak = 1`, действие `Светильник / lamp = 1`.
2. Сохраните и включите сценарий.
3. Откройте **Устройства → Датчик протечки** и нажмите **Сымитировать протечку**.
4. Свет включится, а в журнале появятся триггер, действие и успешное выполнение. Состояние обновляется по WebSocket.

Созданные через **Конструктор** устройства и сценарии записываются в `data/generic_devices.json` и `data/scenarios.json` атомарной заменой временного файла.

## LIVE

Реализация пункта 5, запуск, контракты и обнаруженные ограничения живого стенда: [P5-UJIN-INTEGRATION.md](P5-UJIN-INTEGRATION.md).
Панель **Ujin OS** показывает подтверждённый обмен, привязки устройств и ошибки доставки.

Скопируйте `backend/.env.example` в `backend/.env` и задайте `UJIN_UST`, `UJIN_APARTMENT_ID` и при необходимости `UJIN_BASE_URL`. Перезапустите backend. Секреты остаются на backend. Совместимый сценарий отправляется в **Сценарии → В LIVE**.

Стендовые ограничения, описанные в starter pack: WS-подталкивание команд, writable-словари и автосценарии могли быть отключены на стороне организаторов; назначение квартиры и доступность production-контура также зависят от стенда. Они не затрагивают LOCAL режим.

## Проверки

```powershell
cd emulators
python -m unittest discover -s tests
cd ..\backend
python -m pytest
cd ..\frontend
npm run build
```

Проект переиспользует устройства, Signal/Device, публикации, WebSocket-клиент и Ujin API-контракт из starter pack. Токены и PDF с доступами не входят в репозиторий.
