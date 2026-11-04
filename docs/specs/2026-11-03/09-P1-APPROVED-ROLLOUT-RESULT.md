# P1 — результат согласованного серверного этапа

Дата: 2026-11-03. Владелец явно разрешил оба пункта: обновление только control и отзыв существующего тестового доступа эмулятора. Публикация не разрешалась и не выполнялась. Субагентов не было.

## Применено на VPS

- Заменён только `/opt/vpnn-control/vpnn-control`, SHA-256 `c76c8f6c3ad6a0e33e752d6c829be5e0f4644db00a5f04bd464ffa546c30e456`.
- Прежний бинарник и защитные копии state/signing находятся в root-only `/var/backups/vpnn-control/p1-20261103-130952`.
- Ключ подписи не менялся. Unit, nginx, DNS/VK/Xray код, legacy/iPhone контур и node-sync код не менялись.
- Перезапуск control и сходимость node заняли около 9,5 секунды. Это длительность операции, не точный замер недоступности API.
- При замене control InvocationID восьми остальных проверенных общих/legacy-служб не изменились. Новый config version: `1793711392677`, прежний: `1793659544595`.
- Затем через штатный admin API отозван **только** `Android Emulator · transports`, fingerprint `7b11359b3e73`. Версия отзыва: `1793711751461`. Остальные права устройств и групп не изменились.
- При отзыве reconciler выполнил согласованные перезапуски `vpnn-vk` и `vpnn-egress`; остальные проверенные общие/legacy InvocationID сохранились. DNS backend тестового доступа отключён, его DNS target, VK allowlist entry и Xray client удалены. Остаётся один включённый доступ с DNS/VK.
- Итог: девять проверенных общих/legacy служб active, node healthy, appliedVersion соответствует отзыву. Это не нагрузочная проверка и не подтверждение ёмкости 8 клиентов.

Обычный откат: вернуть прежний control-бинарник из backup, сохранив актуальные state/signing, затем перезапустить только control. Старый state поверх актуального не восстанавливать: клиенты могли запомнить более высокий version floor. Откат не понадобился.

## Реальная проверка нового клиента

Отдельный AVD `VPNN_P1_API35`, debug package `space.chichy.vpnn.dev`, Android x64 0.1.5+6, SAFE_MODE=false. Системный VPN Windows не запускался; пользовательские VPN-процессы Windows не останавливались.

| Сценарий | Результат |
| --- | --- |
| Новый signed config через настоящий VK при гостевом REJECT direct IP VPS | PASS: version `1793711392677`, route vk, stage ready, failure null |
| Отдельно настоящий DNS с тем же direct block | PASS: та же новая версия, route dns, stage ready, failure null |
| Независимый HTTPS egress до отзыва | PASS в обоих режимах, ожидаемый IP VPS; direct TCP к VPS запрещён |
| Force-stop/перезапуск собственного debug-приложения с blocked direct | PASS: новая версия восстановлена из verified cache, usingCache true; DNS снова подключился |
| HTTPS после применения отзыва при прежнем direct block | FAIL ожидаемо: EOF, код 1; ранее этот же запрос проходил |
| Серверное применение отзыва | PASS: отдельный DNS backend inactive, DNS target и VK/Xray разрешения удалены |
| Подписанный отзыв клиенту | PASS: failure revoked, соединение остановлено, configuration null, кэш и pending journal отсутствуют |
| Перезапуск после подтверждённого отзыва | PASS: revoked marker сохраняется |
| Повтор старого signed bootstrap | PASS: доступ и кэш не восстановлены |

**Маршрут receipt:** после подтверждения сетевого прекращения доступа гостевой VPN был явно отключён, собственное правило direct block удалено, Update settings выполнен напрямую. Подписанный отзыв проверен на настоящем API этим путём. Это не автоматический direct fallback: сервер уже отключил VK/DNS-путь отозванного устройства, поэтому доставка receipt через закрытый транспорт не заявляется. Пока receipt не получен, сетевое прекращение доступа обеспечивается сервером; подтверждённый receipt дополнительно фиксирует локальный запрет replay.

## Исправление, найденное при проверке

После первого успешного signed revocation реальный кэш уже удалялся, но controller оставлял usingCache=true. Это показывало неверную плашку сохранённой копии. В `controller.dart` отзыв теперь сбрасывает usingCache вместе с configuration. Regression assertion воспроизвёл ошибку до исправления и прошёл после.

Финальный APK пересобран. На нём повторно проверены запуск с сохранённым отзывом и импорт старого bootstrap: failure revoked, usingCache false, configuration null, running false, кэш и журнал отсутствуют. Полные VK/DNS-сетевые сценарии выполнялись перед этим небольшим исправлением состояния; hash того APK сохранён в manifest как `transportFlowTestedApkSha256BeforeBannerFix`. Тестовый доступ не включался обратно ради повторения сетевого сценария.

Финальные проверки: 59 Flutter tests PASS (`logs/p1-flutter-tests-final.txt`), `flutter analyze --no-fatal-infos` — No issues found, control `go test ./...` и `go vet ./...` PASS. Android debug build PASS. SHA финального APK и Linux control — `artifacts/p1-local/MANIFEST.json`. Финальный APK не является опубликованным релизом.

## Доказательства и оставшиеся границы

- `logs/p1-control-rollout.json`: замена, backup, подпись, версии, неизменные запуски остальных служб.
- `logs/p1-approved-{vk,dns}-diagnostics.json`: новая версия через настоящие транспорты.
- `logs/p1-approved-cache-restart-diagnostics.json`: восстановление новой версии и соединение из кэша.
- `logs/p1-production-test-revocation.json`, `p1-production-revocation-enforcement.json`, `p1-revoked-egress.txt`: применение и прекращение доступа.
- `logs/p1-approved-final-revoked-startup.json`, `p1-approved-final-replay-rejected.json`: финальная сборка с постоянным отзывом и без кэша.
- `logs/p1-final-production-inventory.json`: здоровье и состав оставшихся backend после операции.
- `logs/p1-approved-validation.json`: сводка.

Основной P1 gate новой версии через VK/DNS и реального отзыва подтверждён в эмуляторе. Windows/физический Honor/операторские сети отложены владельцем. Длительный сон/Doze/смена сети, реальные неверные часы и длительные фоновые интервалы не заявляются как проверенные новым прогоном. Смена endpoints и отрицательные security/deadline сценарии подтверждены локальными тестами, не отдельной миграцией рабочего домена. Готовность к массовому выпуску этим отчётом не утверждается.

Созданные гостевые правила и копия bootstrap удалены. Завершение только собственной новой AVD-сессии подтверждено, SSH-сессия закрыта. Тестовый доступ оставлен отозванным; старое тестовое приглашение больше не даёт доступа. Активные release manifests не менялись, автоматической публикации не было.
