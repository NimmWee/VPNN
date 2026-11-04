# P6-B · WB Stream

## Наблюдения и границы

Проверена ревизия [whitelist-bypass a46e58d](https://github.com/kulikov0/whitelist-bypass/tree/a46e58d060dde2ad2caed99231f896fd7c6f075c), [лицензия MIT](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/LICENSE). Прототип написан на Go SDK LiveKit, код whitelist-bypass не включён.

- Creator использует выданный WB токен аккаунта `wb_access_token`. Upstream открывает официальный экран входа и передаёт полученный токен headless-процессу. Creator создаёт выделенную комнату или входит в существующую. Joiner регистрируется как гость и входит по ID комнаты, если гостевой доступ разрешён. Оба запрашивают `connection-details` и получают собственный `roomToken` и `serverUrl`. Токен аккаунта и комнатный токен имеют разные назначения. ID комнаты или ссылка-приглашение сами по себе не являются токеном. [Creator](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/headless/wbstream/main.go) · [Joiner](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/headless/wbstream-joiner/main.go) · [WB API в upstream](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/relay/wbstream/api.go)
- Upstream подключается к выданному SFU по WebSocket `/rtc` с бинарным protobuf-сигналингом LiveKit (protocol 15). У каждой стороны отдельные publisher и subscriber PeerConnection с SDP/ICE через SFU. Режим DC использует упорядоченный `_reliable` и protobuf DataPacket. Режим Video переносит данные в VP8/RTP и поддерживает опциональный KCP. [Сигналинг](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/relay/livekit/codec.go) · [Сессия](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/relay/wbstream/session.go)
- В обоих режимах upstream публикует send-only VP8 `videochannel`, 90 кГц, source Camera, с заявленными 1280×720. Второй ScreenShare опционален. Это поведение клиента. Требования сервера к наличию трека, разрешению, cadence и правам гостя остаются гипотезами до проверки в выделенной комнате WB. [Публикация в upstream](https://github.com/kulikov0/whitelist-bypass/blob/a46e58d060dde2ad2caed99231f896fd7c6f075c/relay/wbstream/session.go#L172)
- 4 ноября 2026 года обычный HEAD к публичному сайту WB Stream получил HTTP 498. В этом прогоне отсутствовали выделенный аккаунт и разрешённая комната. Для проверки нужны штатный вход владельца, ручное прохождение CAPTCHA при запросе, выделенная комната, два разрешённых участника и доступ к выданному WSS/ICE. Записать обезличенные стадии авторизации, SDP/ICE, публикации и передачи. Не сохранять токены, cookies, полные URL сигналинга или SDP в общих логах. [WB Stream](https://stream.wb.ru/)

## Локальный прогон

Windows amd64, Go 1.27.3, LiveKit 1.13.11 и Go SDK v2.19.0. Загрузить архив Windows amd64 и сверить SHA-256 `5d071ea43339f0140d24a66f0b2ff8a7bf6c4d0dceb19b30abca835670213667`. [Релиз LiveKit](https://github.com/livekit/livekit/releases/tag/v1.13.11) · [SDK](https://github.com/livekit/server-sdk-go/tree/v2.19.0)

```powershell
Set-Location C:/VPNN-wb-stream/experiments/wb-stream
$go = 'C:/VPNN/.toolchains/go/bin/go.exe'
& $go vet ./...
./lab.ps1 -Go $go -LiveKit "$env:TEMP/vpnn-wb-p6/server/livekit-server.exe"
```

Скрипт создаёт временную конфигурацию, случайный секрет, отдельную комнату на каждый прогон и файлы `test.log`, `sfu.err.log`, `sfu.out.log` в каталоге, указанном в `Lab logs`. Сигналинг слушает loopback TCP 28760, ICE использует UDP 28762 с loopback-кандидатом, тестовый STUN слушает loopback UDP 28763. Параметр `-Port` смещает все порты. Скрипт завершает собственный процесс SFU и удаляет конфигурацию. Логи SFU могут содержать локальные ICE-адреса. Обычный `go test ./...` пропускает сценарий без стенда.

Критерии локального прогона — отказ при неверной подписи JWT, точное совпадение синтетического VP8-кадра в обе стороны, передача 32 × 1024 байт в каждую сторону с побайтовой проверкой, разрыв обеих сторон после удаления Creator через API SFU, повторный вход, отмена, явный и повторный Close, пустой список участников. Служебный 16×16 VP8-кадр сгенерирован через FFmpeg/libvpx, полезная нагрузка идёт через DataChannel. Совместимость формата с upstream, перенос полезной нагрузки внутри VP8, физическая потеря сети, egress VPS при блокировке прямого IP и доступность из операторской сети требуют отдельных прогонов.

## Контракт адаптера

- `Open(ctx, Config{URL, Token, Room, Identity, PeerIdentity})` принимает уже авторизованные параметры. Для каждого участника нужен короткоживущий токен одной комнаты с правами join, subscribe, publish camera и publish data. Identity различаются. URL берётся из доверенного источника и использует WSS вне локального теста. Владелец сессии отвечает за проверку подписанных параметров, допустимого хоста и срока жизни, получение и обновление токенов. [LiveKit grants](https://docs.livekit.io/home/server/generating-tokens)
- `WaitReady(ctx)` ждёт точный VP8 probe от ожидаемого участника. Перед выставлением общего health нужен двусторонний обмен данными, а для полевой приёмки P6 — независимая HTTPS-проверка публичного egress через Creator при заблокированном прямом маршруте.
- `Send([]byte)` и `Receive(ctx)` передают сообщения длиной 1–1024 байт. Отправка адресована ожидаемому участнику. Receive фильтрует идентификатор отправителя и topic. Очередь на 32 сообщения при переполнении завершает сессию. Send подтверждает приём SDK, доставку проверяет вызывающий код. Шифрование между участниками, мультиплексирование, backpressure отправителя и egress относятся к следующему уровню.
- `Done()` закрывается после освобождения локальных ресурсов. `Err()` возвращает причину. `Close()` идемпотентен и ждёт очистки. Потеря ожидаемого участника или начало reconnect завершают попытку. Внешний владелец задаёт backoff и открывает новую сессию с актуальными параметрами. Контекст владеет сессией, а отдельная стадия публикации ограничена собственным таймаутом SDK до 10 секунд.
