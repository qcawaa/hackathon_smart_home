# Сценарии и виджеты — IKEA (BMS и МП)

> **Твой стенд: тест-ОАЭ** (API `https://api-uae-test.ujin.tech/api`). Все адреса в этом документе уже переведены на него; где осталось слово «preprod» (история прогонов) — читай «тест-ОАЭ». Устройства: команда запуска в брошюре (`--ust-auth`), dev-токен не нужен.

Контракт прочитан из кода (`ujin_client.py`, ujin-ios, bms) и сваггера.
**Обновление 20.10:** резидентская часть проверена живьём — аккаунт получен
саморегистрацией через API (доказательства:
`research/ujin-hackathon/preprod-evidence/2026-10-20-resident-and-admin.md`),
`autoscripts/list` и `autoscripts/signals` → error=0. Осталось
непроверенным: срабатывание сценария — **авто-словари не участвуют в
сценариях** (флаг `signal_dict_scenario=0`, organizer-fixes п.14).
Пометка «📖» = по коду.

## 1. Автосценарии «если — то» (autoscripts, токен резидента)

Ручки (все `/api/...`, ответ обычный):

| Ручка | Параметры | Что делает | Ст. |
|---|---|---|---|
| `autoscripts/signals/` | `token=ust` | справочник: triggers, buttons, actions, capabilities — **отсюда брать имена для условий** | 📖 |
| `autoscripts/edit/` | `token`, `id`, `scenario_type`, `condition`, `set_signal`, `schedule`, `execution_interval`, `title` | создать (id=0)/править сценарий | 📖 |
| `autoscripts/activate/` | `token`, `id` | вкл/выкл | 📖 |
| `autoscripts/list/` | `token` | список | 📖 |
| `autoscripts/mode/` | `token` | режимы (для «сценариев-режимов» МП) | 🎙 ujin-ios |

`scenario_type`: `trigger` | `schedule` | `press` | `mode`.

Формат строк (главное, остальное додумает UI):
- условие: `when:device-<serialnumber>:<signal>=<значение>`
- действие: `device-<serialnumber>:<signal>:<значение>[:hold]`
  (`hold` — секунд до возврата)

Пример «протечка → сирена» (клиент `UjinClient`):

```python
cli.autoscripts_edit(ust, 0, "trigger",
    condition="when:device-17399301610001807:integrations_devices_leak=1",
    set_signal="device-17399301610001808:siren:1:60",
    title="Протечка=>сирена 60с")
cli.autoscripts_activate(ust, scenario_id)   # id взять из list/ответа edit
```

Проверка без резидента: список сигналов + свой сценарий наjudge-устройствах
не пройдут (autoscripts — зона резидента, у BMS-роли «ошибка авторизации»).
Это и есть доказательство границ: фиксируй ответ, не чини.

## 2. Сценарии в интерфейсах (что показывать жюри)

- **МП (резидент)**: экран «Сценарии» → создать: выбор устройства-триггера,
  значения, действие; есть «режимы» (`autoscripts/mode/`).
- **BMS (concierge/УК)**: сценарные кнопки + виджеты (см. п.3); активация
  сценариев по-старому и через `devices/scenario-activate/?token&id&state=1`
  (🎙 alice).

## 3. Контракт виджетов консьержа (BMS)

Данные экрана — две ручки (якорь: bms `features/widgets/widget-signals`):

| Ручка | Параметры | Ответ |
|---|---|---|
| `bmsdevice/get-widgets/` | `token=ust` | список плиток: id, название, тип, позиции |
| `bmsdevice/get-widgets-data/` | `token`, `id` | данные одной плитки: устройства+значения |
| `bmsdevice/get-devices/` | `token` | реестр для виджета «устройства» |
| `scud/client/management/pass/*` | `token` | пропуска (виджет «открыть двери» — `widget-open-doors`) |

Свои плитки в БД консьержа не плоди (общая среда) — демо достаточно
штатных виджетов на judge-устройствах; для своих данных показывай
`get-widgets-data` JSON + свою страницу-дашборд.

## 4. Мини-приёмка сценарной части (когда дадут резидента)

1. `autoscripts/signals` содержит сигнал judge-устройства.
2. Созданный сценарий виден в `list`, `activate` переключает состояние.
3. Эмулятор публикует триггер → `task` действия появляется в
   `get-device-info` (или WS-событие, когда cast заведут) ≤ 5 с.
4. Выключенный сценарий не дергает устройство.
