# Лаборатория DNS-туннелей

[Сводка замеров и сырые данные](RESULTS.md)

## Baseline

- VPNN base commit `f2f6d6fb79dfac4b5f91f44deff02202d458c394`. Дерево `transports/masterdns` имеет Git ID `224ba988310d85f4d7ab6ceef10035e7f517850a`. В `sources.lock.json` исходным upstream указан `4144e544d220681a8e8fe808855ac09dcd07c31c`. Измерялась встроенная версия VPNN с локальными изменениями.
- MasterDnsVPN собран Go 1.27.3 windows/amd64. Клиент использует обычный `vpnn.New`, AES-256-GCM и один resolver. Сервер использует профиль рабочих очередей из `deploy/node_sync.py` (1 reader, 1 request worker, 1 deferred worker, 512 concurrent, 256 deferred, socket buffer 524288), внешний SOCKS5 направлен на заглушку. Заглушка принимает только `target.example.test` и свой порт, без DNS lookup. Остальные настройки транспорта оставлены по умолчанию.
- [EndPositive/slipstream protocol](https://github.com/EndPositive/slipstream/blob/e158a681f1cc5cb000a92274371e67237d2a6493/docs/protocol.md) описывает QUIC multipath, Base32 в QNAME и TXT на обратном пути. Измерена [отдельная Rust-реализация v0.1.1](https://github.com/Mygod/slipstream-rust/releases/tag/v0.1.1), tag commit `c7b265c11dd13d6dfd601bc81d54d61ee9bdde23`. Использован опубликованный x86-64 ZIP для Windows, SHA-256 `7efc45bafab08aebacba10aa19562793de29dcd67e89f75ce8a3942b8da1e59e` совпал с upstream. Upstream Rust архивирован. Клиент работает в режиме `--resolver` с проверкой локального сертификата. Сервер проксирует в один заданный TCP target.
- Сценарии взяты из [P3 и P6-C](../../docs/specs/2026-11-03/06-IMPLEMENTATION-PLAN.md) и [DNS-01–06](../../docs/specs/2026-11-03/04-CAPACITY-PERFORMANCE.md). Это синтетический стенд одной сессии на Windows (i5-12400F, 6 ядер, 12 логических CPU). Используются `127.0.0.1`, динамические высокие порты и зона `lab.example.test`. Стенд пересылает DNS-пакеты с заменой ID и восстановлением исходного ID при ответе.

## Методика

| Профиль | Задержка на каждом плече | Пропуск на каждом плече | Дополнительная задержка на каждом плече | Лимит запросов |
|---|---:|---|---|---:|
| clean | 0 мс | нет | нет | 1500/с |
| delay | 25 мс | нет | нет | 1500/с |
| impaired | 25 мс | каждый 23-й | 75 мс на каждом 11-м | 1500/с |
| capped | 25 мс | нет | нет | 300/с |

Потери и задержка привязаны к порядковому номеру пакета на соответствующем плече. Лимит отбрасывает превышение в скользящем окне 1 с. Настройки одинаковы для пары, а номера полезных байтов, затронутых потерями, зависят от пакетизации. Резолвер запускается заново на каждый прогон.

Каждый прогон открывает один TCP-поток, делает 2 разминочных и 10 измеряемых пингов приложения, затем передаёт по 65 536 детерминированных псевдослучайных байт в обе стороны. При загрузке на сервер проверяется SHA-256, в обратном направлении проверяются байты. Порядок пары и направлений меняется во втором повторе. Тайминг каждой передачи включает запрос приложения или подтверждение SHA-256. Старт сессии исключён из goodput. DNS-запросы за этот интервал включают payload, ACK и polling, в том числе запросы, впоследствии отброшенные резолвером. 1 МБ = 1 000 000 байт.

`dns_rtt_p95_ms` измеряет доставленные DNS-ответы от входа запроса до выхода ответа из резолвера. Ответы учитываются по времени выхода и могут относиться к запросу предыдущей фазы. `app_rtt_p95_ms` — p95 из 10 пингов после прогрева. `question_repeat` считает повтор QNAME/QTYPE/QCLASS за прогон независимо от ID и регистра. Повтор ARQ или QUIC может иметь новый QNAME. `master_client_resend_frames` считает успешные записи клиентских DNS-кадров `STREAM_RESEND`, включая возможные копии по путям. Часть ARQ-повторов выходит как `STREAM_DATA` и в этот счётчик не входит. Серверные повторы MasterDnsVPN и QUIC retransmit в выбранном бинарнике недоступны. `null` в этой колонке означает отсутствие метрики.

CPU записан в процессорных секундах user + system, RAM — максимальный из замеров RSS с интервалом 25 мс и замеров на границах фазы, отдельно по процессам. Короткая фаза может дать CPU 0 из-за дискретности учёта Windows. Резолвер и нагрузочный процесс исключены из CPU/RAM пары. `results.json` и `results-capped.json` содержат отдельные фазы и прогоны, хеши бинарников и фактические настройки.

## Воспроизведение

В PowerShell из корня отдельной копии VPNN. Нужны Go 1.27.3, Python 3.10 с psutil 7.2.2 и OpenSSL в PATH. Каталог результата должен быть новым. Тестовый сертификат и бинарники создаются в отдельном временном каталоге.

```powershell
$lab = Join-Path ([System.IO.Path]::GetTempPath()) ("vpnn-dns-" + [guid]::NewGuid())
New-Item -ItemType Directory $lab | Out-Null

Push-Location transports/masterdns
go test ./...
go build -trimpath -o "$lab/lab-server.exe" ./cmd/server
Pop-Location

Push-Location experiments/dns
go build -trimpath -o "$lab/lab-master.exe" .
python -B -m unittest -v

$asset = 'https://github.com/Mygod/slipstream-rust/releases/download/v0.1.1/slipstream-windows-x86_64.zip'
Invoke-WebRequest $asset -OutFile "$lab/slip.zip"
if ((Get-FileHash "$lab/slip.zip").Hash -ne '7efc45bafab08aebacba10aa19562793de29dcd67e89f75ce8a3942b8da1e59e') {
    throw 'Slipstream archive SHA-256 mismatch'
}
Expand-Archive "$lab/slip.zip" "$lab/slip"
openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj /CN=lab.example.test -addext subjectAltName=DNS:lab.example.test -keyout "$lab/key.pem" -out "$lab/cert.pem"

$bench = @(
    '--master-client', "$lab/lab-master.exe",
    '--master-server', "$lab/lab-server.exe",
    '--slip-client', "$lab/slip/slipstream-client.exe",
    '--slip-server', "$lab/slip/slipstream-server.exe",
    '--cert', "$lab/cert.pem", '--key', "$lab/key.pem"
)
python -B bench.py @bench --output "$lab/run" --profile clean --profile delay --profile impaired
python -B bench.py @bench --output "$lab/capped" --profile capped
Pop-Location
```

## MasterDnsVPN по текущим исходникам

- `internal/arq/arq.go`: selective repeat на 16-битном номере сегмента. ACK снимает конкретную запись из `sndBuf`. Приёмник держит данные впереди `rcvNxt` в `rcvBuf`, повторно подтверждает уже доставленный номер, выдаёт TCP только непрерывную последовательность. При переполнении RX-очереди или выходе за окно приёмник может отбросить кадр. Ограниченный NACK на ближайшие дыры может инициировать ранний повтор.
- Конфигурационные окна по умолчанию 600 у клиента и 800 у сервера. ARQ берёт минимум 300, порог backpressure отправителя составляет 80% окна (480 и 640 при штатных значениях), окно приёма 2× (1200 и 1600). Это сегменты, а не байты. `SESSION_ACCEPT` может ограничить клиентское окно, MTU, NACK, RTO и другие параметры серверной политикой. Клиентский `dnsWindow` показывает итоговое конфигурационное окно.
- Базовые пределы RTO на обеих сторонах 1–5 с для данных и 0,5–3 с для control. По пригодным ACK ARQ ведёт отдельные оценки SRTT и RTTVAR, использует SRTT + 4×RTTVAR с ограничениями. Повтор исключает сегмент из RTT-выборки. Backoff на повторе 1,35× для данных, 1,25× для control, 1,15× для setup-control. Отдельно работают TTL, пределы попыток (1200 data / 400 control по умолчанию, есть специальная обработка setup и завершения), inactivity watchdog и drain timers. Клиентский UDP timeout 10 с в `async_runtime.go` относится к DNS I/O и наблюдению за запросами, поэтому его нельзя трактовать как RTO потока.
- `internal/client/async_runtime.go` и `balancer.go`: дублирование клиента запрашивает до 2 разных пар домен/резолвер по умолчанию. Для SYN, packed control и закрытия может действовать отдельный setup-count. Выбор ограничен числом активных пар. С одной парой значение `dnsDuplication=2` не означает две копии DATA. Повтор ARQ, гонка SESSION_INIT и повтор последнего packed control на сервере (`PACKET_BLOCK_CONTROL_DUPLICATION=1` по умолчанию) — отдельные механизмы.

## Предложения правок MasterDnsVPN

1. Добавить симметричные счётчики клиента и сервера для новых DATA, повторов по RTO/NACK, повторов control, отправленных копий, повторно полученных номеров и доставленных TCP-байтов. Считать ARQ-решение на уровне сегмента и отдельно DNS-кадры на записи. Проверить повторы, помеченные `STREAM_DATA`, заполнение RX и обёртку 16-битного номера regression-тестами.
2. Добавить гистограммы DNS RTT и времени в очередях, максимум занятости ARQ/worker-очередей, счётчики пустых poll-ответов и загрузку лимита запросов. Разделять эффективное окно, согласованный MTU и фактическое число путей, чтобы отличить дефицит polling от переполнения очереди. Использовать обезличенные числовые метрики.
3. После появления счётчиков проверить адаптивный polling с верхней границей QPS и спадом в idle. Затем отдельными A/B/A проверить число серверных workers и пороги NACK/RTO. Для проверки дублирования нужны как минимум два независимых пути и сравнение 1/2/1 копии. Сохранить текущие defaults до подтверждения выигрыша.

Для интеграции Slipstream нужны отдельный клиентский адаптер, изолированная авторитетная зона или явная маршрутизация запросов до отдельного backend и проверка эквивалентности выдачи и отзыва доступа. Текущий сервер Slipstream с фиксированным TCP target не обеспечивает сам по себе интерфейс managed SOCKS5 и модель ключей на устройство VPNN. Прогон проверяет DNS-обмен через fake resolver. Делегирование, кэширование, TC/EDNS реального рекурсора, смена сети, multipath, оригинальный C-бинарник и нагрузка 1/2/4/8 сессий остаются за пределами замера.
