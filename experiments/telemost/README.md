# Эксперимент Telemost для P6

Изолированный Go-модуль и аудит провайдера. `Probe(ctx, payload)` выполняет один бинарный обмен с эхом по надёжному упорядоченному DataChannel между двумя локальными Pion-пирами. Вызов принимает от 1 до 16 КиБ и владеет обеими PeerConnection до их закрытия. Передавайте контекст с дедлайном. Пиры используют выделенные ОС UDP-порты на `127.0.0.1` и обмениваются SDP в памяти. Отдельный тест проверяет получение синтетического RTP-пакета на согласованном треке VP8. Локальная схема использует прямой ICE между пирами.

## Закреплённый upstream

| Поле | Значение |
| --- | --- |
| Репозиторий | [kulikov0/whitelist-bypass](https://github.com/kulikov0/whitelist-bypass) |
| Ревизия | [a46e58d060dde2ad2caed99231f896fd7c6f075c](https://github.com/kulikov0/whitelist-bypass/commit/a46e58d060dde2ad2caed99231f896fd7c6f075c) |
| Лицензия | [MIT, Copyright (c) 2026](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/LICENSE) |
| Git blob LICENSE | `14fac913ccf80234b1848540089a3bbcb6e5283d` |
| SHA-256 LICENSE в исходном архиве | `1126322e2cc8d165adc4c792eeb195717de2bcc7b39be1ce77959d78e87ef685` |

Сверка в отдельном клоне upstream:

~~~powershell
git clone --depth 1 https://github.com/kulikov0/whitelist-bypass.git C:/VPNN-telemost-upstream
Set-Location C:/VPNN-telemost-upstream
git fetch --depth 1 origin a46e58d060dde2ad2caed99231f896fd7c6f075c
git switch --detach a46e58d060dde2ad2caed99231f896fd7c6f075c
git rev-parse HEAD
git rev-parse HEAD:LICENSE
git show HEAD:LICENSE
~~~

Локальная реализация написана отдельно. Её зависимости зафиксированы в `go.mod` и `go.sum`. В upstream WebRTC берётся через `github.com/kulikov0/headless-client v0.1.0`. Локальный стенд использует `github.com/pion/webrtc/v4 v4.2.11`.

## Вход и передача по исходникам

- **Создание комнаты.** В штатном браузере владелец выделенного Яндекс ID входит вручную и создаёт новую встречу. Любой запрос CAPTCHA или MFA обрабатывает владелец в штатном интерфейсе. Публичный REST API документирует создание встречи через OAuth и возврат `join_url`. В обзоре доступ ограничен Яндекс 360 для бизнеса, а страница создания допускает личный Яндекс ID для обычной публичной встречи. Доступ конкретной учётной записи к REST API предстоит проверить. Документация описывает управление встречей, но не предоставляет контракт для WebRTC media join. [Обзор API](https://yandex.ru/dev/telemost/doc/ru/) · [OAuth](https://yandex.ru/dev/telemost/doc/ru/access) · [Создание встречи](https://yandex.ru/dev/telemost/doc/ru/conferences/conference-create)
- **Headless Creator.** Upstream требует существующую браузерную сессию с `Session_id` даже с флагом `--tm-link`. Он загружает cookies и вызывает внутренний веб-API `telemost_front/v2/telemost`. При создании использует `POST /conferences`, затем запрашивает `/connection` для получения `peer_id`, `room_id`, media credentials, ICE servers и URL WebSocket. Это клиентский путь из исходников, стабильность и разрешённость автоматизации надо подтвердить до внешнего запуска. OAuth-токен публичного API и cookie веб-сессии имеют разные назначения. Creator также умеет допускать участников и удалять других участников, поэтому использовать только выделенную встречу. [Creator](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/headless/telemost/main.go) · [HTTP API](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/relay/telemost/api.go)
- **Headless Joiner.** Путь из исходников предусматривает гостевой запрос `/connection` по ссылке, ожидание допуска в `WAITING_ROOM`, затем сигналинг WebSocket и отдельные PeerConnection publisher/subscriber. Поддержка гостевого режима зависит от политики выделенной встречи. [Joiner](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/relay/pion/headless-joiner-common/telemost_joiner.go)
- **DataChannel.** В Creator `AddSharingDataChannel` открывает неупорядоченный `sharing`. В него отправляются RTP-пакеты с VP8 для дополнительного экрана, а обработчик входа реагирует на RTCP. Это часть пути дополнительного видеотрека. В Telemost CLI Joiner нет переключателя отдельного двустороннего DC-туннеля, а основной тракт Joiner строится на VP8. Поддержка произвольных DC-сообщений на реальном SFU остаётся непроверенной. [Релей Creator](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/headless/telemost/tunnel_relay.go) · [CLI Joiner](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/headless/telemost-joiner/main.go)
- **VP8/RTP.** Creator публикует VP8, Joiner ждёт привязки слота и строит `VP8DataTunnel`. Поверх него Joiner поднимает SOCKS5. Первый внешний прогон следует проводить с одним треком. Исходники подтверждают наличие механизма. Стабильность привязки слота и обратного пути измеряется отдельно. [Joiner](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/relay/pion/headless-joiner-common/telemost_joiner.go) · [Сообщение upstream о сбое обратного пути на v0.3.6](https://github.com/kulikov0/whitelist-bypass/issues/150)

## Локальный запуск

PowerShell, Go 1.24+.

~~~powershell
Set-Location C:/VPNN-telemost/experiments/telemost
$telemostRun = Join-Path $env:TEMP ('vpnn-telemost-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $telemostRun | Out-Null
go test -mod=readonly -v -count=5 -timeout=60s ./... 2>&1 | Tee-Object -FilePath (Join-Path $telemostRun 'local.log')
if ($LASTEXITCODE -ne 0) { throw 'Telemost local tests failed' }
go vet -mod=readonly ./...
go mod verify
~~~

Порты локального стенда выдаёт ОС. Логи каждого прогона хранятся отдельно. Остановка теста освобождает сокеты, процесс завершается штатно.

## Результаты 2026-11-04

| Проверка | Статус | Доказательство |
| --- | --- | --- |
| Ревизия и лицензия upstream | PASS | HEAD и Git blob LICENSE сверены с закреплёнными значениями |
| Сборка Creator и Joiner из upstream | PASS | Windows/amd64, Go 1.26.2, CGO_ENABLED=0. Команда `go build -mod=readonly ./headless/telemost ./headless/telemost-joiner` завершилась с кодом 0 |
| Публичный вызов Probe и двусторонний бинарный обмен | PASS | `TestProbe` и `TestDataChannelRoundTripAndCleanup`, по 5 успешных прогонов. Эхо 16 384 байт сверено целиком |
| Отмена и освобождение ресурсов | PASS | До сигналинга и после доставки запроса без ответа возвращается `context.Canceled`. В обоих сценариях и после нормального обмена два UDP-сокета закрыты и их порты повторно заняты |
| Локальный RTP на VP8 | PASS | `TestLocalVP8RTP`, 5 прогонов. Получены `video/VP8`, marker и все 16 байт синтетической нагрузки |
| Отдельный режим DataChannel в Telemost CLI upstream | FAIL | В проверенной ревизии такого режима нет. `sharing` обслуживает дополнительный экран, а основной туннель Joiner использует VP8 |
| Headless вход, допуск гостя, DC или VP8 через реальный SFU | NOT TESTED | Нет выделенной авторизованной комнаты и согласованного стенда |
| Блокировка прямого маршрута, полезный трафик через публичный egress VPS, лимиты и операторская сеть | NOT TESTED | Нужен внешний прогон с изолированным Joiner и независимым HTTPS-стендом |

Локальный прогон на Windows/386 с Go 1.26.2 завершился с кодом 0, 25 успешных запусков тестов за 8,338 с. `go vet` завершился с кодом 0, `go mod verify` вернул `all modules verified`. Сохранён отдельный `local.log`. Первый вызов `go get` завершился ошибкой тайм-аута `proxy.golang.org`. Для загрузки зависимостей с сохранением стандартной проверки Go checksum database использовалась настройка только для процесса PowerShell `https://goproxy.io|https://goproxy.cn|https://proxy.golang.org` в `GOPROXY`. Итоговый прогон с заполненным кэшем выполнен со штатными настройками.

## Внешний прогон после предоставления доступа

Понадобятся выделенная встреча, авторизованная владельцем браузерная сессия тестового Creator и разрешённый экспериментальный стенд с известным публичным IP. Гостя допускает владелец встречи. Для внутреннего веб-API необходимо подтверждение допустимости автоматизированного подключения. Хранить экспорт cookies только в ограниченном каталоге аккаунта запуска. Файл, комнату, токены, ICE credentials и сырые ответы HTTP/SDP исключить из Git и публикуемых логов. Upstream пишет ссылку комнаты и может писать тела ответов, поэтому сырые журналы хранить с теми же ограничениями, что и credentials. По завершении закрыть встречу и отозвать тестовую браузерную сессию.

Заготовка для согласованного стенда. Собирать из закреплённого upstream. У Creator и Joiner свои закрытые каталоги запуска и логи. Использовать выделенный SOCKS-порт `127.0.0.1:18761`, заранее проверить его доступность.

~~~sh
# В корне whitelist-bypass, на каждой стороне в своём каталоге запуска
go build -mod=readonly -o "$TM_RUN/creator" ./headless/telemost
go build -mod=readonly -o "$TM_RUN/joiner" ./headless/telemost-joiner

# Creator на тестовой VPS, без --upstream-socks
"$TM_RUN/creator" --cookies "$TM_COOKIE_FILE" --tm-link "$TM_ROOM" >"$TM_RUN/creator.log" 2>&1

# Joiner из отдельной ограниченной сети
"$TM_RUN/joiner" --tm-link "$TM_ROOM" --socks-host 127.0.0.1 --socks-port 18761 >"$TM_RUN/joiner.log" 2>&1

# Отдельный терминал Joiner. URL содержит уникальный несекретный run ID.
curl --fail --show-error --max-time 30 --socks5-hostname 127.0.0.1:18761 \
  --data-binary "@$TM_RUN/upload.bin" --output "$TM_RUN/download.bin" "$TM_HTTPS_PROBE"
~~~

В тестовой сети заранее заблокировать прямой TCP/UDP к адресам VPS по IPv4 и IPv6, оставить нужные адреса Telemost. Счётчики политики и захват трафика Joiner должны подтверждать отсутствие прямого пути. На независимом HTTPS-стенде сравнить IP запроса с исходящим IP VPS. Использовать известные тела запроса и ответа, сверить SHA-256 обоих направлений и связать события по run ID. Контрольный запрос после Stop Creator должен завершиться ошибкой через тот же SOCKS. Протокол прогона должен содержать версию, режим, маскированный идентификатор стенда, статус блокировки, время входа и готовности, байты и goodput по направлениям, RTT, CPU/RSS, коды ошибок и время Stop. Останавливать только свои процессы, завершить тестовую встречу и удалить её секреты.

## Контракт для интегратора

- Владелец жизненного цикла — существующий `engine.Manager`. Адаптеру предложен интерфейс `Start(ctx, verifiedSession, protect) → Session`, у сессии есть локальный `SOCKSAddr`, события, `Done` и идемпотентный `Stop(ctx)`. Локальный `Probe` служит стендом для транспорта. Интеграционный интерфейс здесь только описан.
- Control доставляет подписанные параметры через существующий envelope и кэш. Минимальные поля — версия схемы, device ID, session ID, generation/revision, срок действия, provider и режим, ссылка выделенной комнаты, ожидаемый идентификатор VPS и материал аутентификации устройства. Creator cookies остаются только у серверного оператора. Просрочка, отзыв, неверная подпись или поколение закрывают сессию и её локальный SOCKS.
- Ссылка на встречу допускает участника. Для доступа к egress требуется отдельное взаимно аутентифицированное шифрование между устройством и VPS поверх SFU с защитой от replay. Upstream выводит секрет обфускации из ссылки комнаты, поэтому знание ссылки даёт возможность его воспроизвести. Разрешать только авторизованный трафик, ограничивать адреса назначения, сессии, буферы и параллельные проверки. [Вывод секрета upstream](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/relay/tunnel/obfuscator.go)
- `connecting` включает HTTP, допуск, WebSocket, ICE и согласование канала. `ready` требует рабочего SOCKS и успешного HTTPS через аутентифицированный VPS. При ошибке различать `auth_required`, `signaling_failed`, `ice_failed`, `carrier_failed` и `egress_failed`. Существующая Auto policy владеет backoff и выбором маршрута, Manager отбрасывает устаревшие события по generation. Все внешние сокеты адаптера должны поддерживать Android Protect и исключение из TUN на соответствующей платформе.
- Stop отменяет HTTP, WS, ICE, relay и активные SOCKS-потоки, затем ожидает закрытия сессии. Пока старый экземпляр не завершился, Manager отклоняет новый старт. При недоступности, отзыве или откате отключается экспериментальный transport kind и управление возвращается существующей политике.
