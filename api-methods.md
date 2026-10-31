# API-методы Ujin для хакатона — справочник (15.10.2026)

> **Твой стенд: тест-ОАЭ** (API `https://api-uae-test.ujin.tech/api`). Все адреса в этом документе уже переведены на него; где осталось слово «preprod» (история прогонов) — читай «тест-ОАЭ». Устройства: команда запуска в брошюре (`--ust-auth`), dev-токен не нужен.

База: `https://api-uae-test.ujin.tech/api`. Ответ везде:
`{command, error, error_code, message, data, token, connection}`.
Статусы: ✅ проверено живьём · 📖 код/сваггер · 🎙 найдено в alice/bms/ujin-ios.
Токены: **ust** — пользователь; **dev-** — якорь-шлюз интеграции; **cos-** —
consumer (для import_device от имени компании).

## 1. Аутентификация и пользователи
| Метод | Сигнатура | Что делает | Ст. |
|---|---|---|---|
| auth/authenticate | POST `login`,`password` → `data.token` (ust) | вход пользователя УК/BMS/резидента | ✅ |
| auth/registry-step-1/2 | POST `phone` (+`code`,`name`) | самомрегистрация резидента по SMS-коду; на тестовых номерах код `1234` (functions.php:2208) | ✅ 20.10 |
| auth/registry | POST `phone`,`password`(`≥8`),`name`,`surname`,`patronymic`,`app`,`apart=<apt_id>` | регистрация сразу с паролем; `apart` — привязка к квартире без модерации (auth.php:839) | ✅ 20.10 |
| user/update-user | POST `token=ust`,`user_name/user_surname/user_patronymic` | ФИО профиля | ✅ 20.10 |
| meta-platform get_instance_for_user | GET `?login=` | по телефону — инстанс/адрес API юзера | 🎙alice |
| v1/pub/admin/users/search | POST | поиск пользователя (админ) | 🎙alice |

## 1а. Админки (не для команд, но важны)
- **Розовая админка (platform-api, Laravel)**:
  `https://api-uae-test.ujin.tech/api/v1/pub/admin/login` — страница 200;
  доступ: логин/пароль `internal_admin_users` (создаётся только artisan
  `admin-user:create`) — ждём от орг-ов. Внутри: создание УК, ЖК, привязка
  квартир.
- **admin_meta (ihome)**: `/api/admin_meta/<кейс>/?phone=&hash=md5(phone)` —
  CRUD моделей/классов/словарей, ручные сигналы; соль пустая (дыра, fix
  п.12); на api-uae-test точка 500. Полный разбор: `admin-meta.md`.
- **ЛК Разработчика** (meta-platform, cos-токен): `consumer/tags/list`,
  `consumer/model` GET/POST, `consumer/model/signal`,
  `consumer/model/moderation` — легальное описание модели интегратором.

## 2. Жизненный цикл устройства (import_device, dev-token; cos — от компании)
| Метод | Сигнатура | Что делает | Ст. |
|---|---|---|---|
| import_device/create-update-device | POST form: `device-token`,`model`,`device_ext_id` + привязка: `path`+`separator=_`+`mask=building_title`+`area_guid=apt_<id>` (проверено 20.10, error=0, serial в `data.new_serialnumber`). **Без `path`+`area_guid` — серверный PHP-fatal `Device::getBySerial(): null`** (500, не валидация) | создать/апдейт устройства | ✅ 20.10 |
| import_device/update-device-signal | POST: `device-token`,`model`,`serialnumber`,`signal`,`value` | записать ОДИН сигнал (сигналы mgmt=r не примутся в task) | 📖⚠ тихо теряет значения, если задан serial_sw |
| import_device/group-update-device-signal | POST JSON `{"data":[{sn,s,v,c}]}` (sn=device_ext_guid, **c=класс модели**, иначе lupsl тихо фильтрует) | пакетная запись сигналов; основной рабочий путь | ✅ |
| import_device/hide-device | POST: `device-token`,`model`,`serialnumber` | мягкое удаление (device_del=ts, serial→0) | ✅ |

## 3. Чтение кабинета (BMS/API, ust)
| Метод | Сигнатура | Что делает | Ст. |
|---|---|---|---|
| bmsdevice/get-devices | GET `token`,`state`,`limit`,`tag` | реестр устройств BMS (судейские видны) | ✅ |
| bmsdevice/get-device-info | GET `token`,`serialnumber`,`mts=1` | карточка: сигналы, флаги словарей, `task` (только mgmt≠r) | ✅ |
| bmsdevice/get-device-type | GET `token` | справочник типов | 🎙bms |
| bmsdevice/get-rooms | GET `token` | комнаты | 🎙bms |
| bmsdevice/get-widgets / get-widgets-data | GET `token`,`id` | виджеты экрана консьержа и их данные | 🎙bms |
| devices/main | GET `token` | витрина умного дома МП (устройства+комнаты) | 🎙ios/alice |
| apartment/get-device-signals | GET `token` | сигналы устройств квартиры (ассистентский вид) | 🎙alice |
| chip/get-state | GET `token` | состояние устройств для ассистентов | 🎙alice |
| user/get-json-data | GET `token` | настройки пользователя | 🎙alice |

## 4. Команды «вниз» через UI/ассистента (ust)
| Метод | Сигнатура | Что делает | Ст. |
|---|---|---|---|
| apartment/send-signal | GET/POST `token`,`serialnumber`,`signal`,`value` (+uniq) | штатная команда устройству (BMS Uniremote, МП) | 🎙bms/ios |
| apartment/send-group-signal | GET `token`,`assistant=1`,`command=…` | групповая команда текстом (Яндекс-стиль) | 🎙alice ⚠ Jira UE-360 «не работает» |
| devices/scenario-activate | GET `token`,`id`,`state=1` | активировать сценарий | 🎙alice |
| scenario/activate-scenario | GET `token`,`id`,`state` | то же (старый префикс) | 🎙alice |
| autoscripts/mode | GET `token` | режимы сценариев | 🎙ios |

## 5. Команды платформы → устройство (pull) + WS
| Метод | Сигнатура | Что делает | Ст. |
|---|---|---|---|
| devices/difference | GET `token`,`dt` (unix) | дельта значений с момента dt (основной pull МП) | ✅ (12.10) |
| bmsdevice/get-device-info → `signal_task_value` | см. п.3 | очередь task-команд; видно ТОЛЬКО для mgmt≠r | ✅ |
| devices/wss | GET `token` | список wss-адресов (cast v8); на preprod `[""]` (нет привязки+WSS_URL) | ✅ |
| WS протокол | open→`{"token","event":"authenticate","signals":true}`; `setValue{id,sn:int,signals:[{name,value}]}`; эхо по id | команды/подписка как в МП | ✅ handshake (сервер жив, auth=Access denied без регистрации sn) |
| HTTP-сервер опроса (устройство) | GET на device_first_server `?data={"recv":[{"command":"management","id","<signal>":v}]}` | платформа зовёт устройство само | 📖 |

## 6. Сценарии (autoscripts, ust резидента)
| Метод | Сигнатура | Что делает | Ст. |
|---|---|---|---|
| autoscripts/signals | GET `token` | словарь сигналов для условий | 📖 (для BMS-роли — «ошибка авторизации») |
| autoscripts/edit | POST `token`,`scenario_id`,`scenario_type`,`when`,`do` | создать/править сценарий «условие+действие» | 📖 |
| autoscripts/activate | POST `token`,`scenario_id` | включить/выключить | 📖 |
| autoscripts/list | GET `token` | список сценариев | 📖 |

## 7. Потребители/доступы (ust)
| Метод | Сигнатура | Что делает | Ст. |
|---|---|---|---|
| consumer/new-consumer | POST `name`,`ips`,`start`,`finish`,`user_token=ust(опц.)` | выдать cos-токен; без `user_token` — потребитель «ничей», ips=IP просящего (дыра, fix п.13) | ✅ |
| consumer/new-compl | POST `token=cos`,`entity_type=12`,`entity_guid=<класс>`,`rules_type=2` | компл класса устройств; verify=-1 уже даёт запись (дыра/особенность) | ✅ |
| consumer/get-token, get-compl, new-subscribe… | `token=cos` | листинг/токены/подписки потребителя | 📖 |

## 7а. admin/* — без авторизации (fix п.13, использовать только на своих)

| Метод | Сигнатура | Что делает | Ст. |
|---|---|---|---|
| admin/connect-device-apartment | GET `serialnumber`,`apartment` | привязка устройства к квартире (пишет `device.apartment_id`) | ✅ 20.10 |
| admin/disconnect-device-apartment | GET `serialnumber` | отвязка (apartment_id=0) | 📖 |
| admin/update-pass-from-email | GET `login=email`,`password` | **смена пароля юзера по email** — не трогать, только риск | 📖 код |

## 8. Без API — только БД/панель (для орг-ов и rw-доводки)
- `signal_dict.signal_management` (r/rw/w), `signal_show_window` — без них нет
  команды вниз и витрины (панель: `/act/dict/<id>`).
- `signal_dict_rus` — переводы (панель показывает; `tools/seed_rus.py --apply`).
- `signal.signal_task_value/_dt` — ручная task (панель `/act/task/<sid>`).
- `signal_archive_float` — история (панель `/history/<sid>`).
- Привязка устройства к квартире: `device.apartment_id` (API `apartment/update-device-room`
  требует apartment_id>0 уже сейчас).

## 9. Якоря контрактов в коде (для портирования)
- Эмуляторы-клиент: `emulators/ujin_client.py` (все п.2/5/6), `ws_client.py` (п.5).
- МП-клиент: `ujin-ios/Common/Services/Network/Params/APIManagerEndpoint.swift`.
- BMS-клиент: `bms/src/features/fabrics/devices/detail/api`, `widget-signals`.
- Ассистент: `alice/docs/alice_action.wsd`, `alice/src/alice_facade.py`
  (Yandex Smart Home `/v1.0/user/devices/query|action`), маппинг
  capability↔signal: `alice/src/api/{capabilities,properties}` + `signals/`.
