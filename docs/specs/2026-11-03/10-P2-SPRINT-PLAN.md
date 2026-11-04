# P2 — реализация спринта

Основание: владелец разрешил реализацию P2 в текущем спринте. Работать последовательно, без субагентов. VPS, доступы, публикация и Windows VPN не входят в это разрешение.

1. Зафиксировать текущие пользовательские изменения (`logs/p2-source-baseline.json`), исходники затронутых файлов сохранить локально для сравнения. Не очищать git.
2. Tests first: signed profile metadata (kind, priority, enabled, minimumClientVersion), неизвестный kind пропускается безопасно; policy сортирует доступные назначения, last-good текущей сети и cooldown, исключает повторы.
3. Выделить user/admin build variant. User оставляет только VPNN dashboard и помощь на нём; скрытые старые PageLabel возвращают dashboard. Закрыть advanced button, subscription deep links, tray/hotkey обходы. Существующие profiles/settings/secure storage сохраняются. Admin использует то же ядро, отдельный ID пока не вводится без необходимости параллельной установки.
4. Ввести auto-selection с явным фактическим способом и миграцией старой fallback-настройки. Реализовать bounded последовательное выполнение, latest-intent для ручного выбора/Stop/сети, cooldown, очистку network-scoped last-good при смене сети. Не принимать неизвестный HTTPS health за успех.
5. Generalize platform lookup/registry для нескольких назначенных профилей, сохранить один владелец TUN. Сохранённый registry содержит только идентификаторы профилей и позволяет удалять именно managed-профили при отзыве.
6. User UI: только назначенные способы, Auto рекомендован, статусы нет сети/устаревшие настройки/исчерпанные пути/отзыв, сообщение о возможном обычном интернете после Stop. Помощь: refresh, безопасный report, версия, удаление доступа. Локализация во всех ARB с штатной генерацией.
7. Прогнать controller/policy/navigation/link/widget/health/l10n tests, pub get/analyze. Собрать локальный candidate и проверить UI в собственном AVD, крупный текст/тёмную тему, Stop/перезапуск/фон без заявления, что UI timer обеспечивает Android Doze.
8. Сохранить отчёт реализация/локальная проверка/эмулятор/внешний gate. Реальный сетевой тест требует отдельного согласования тестового доступа: прежний доступ оставлен отозванным. Windows и Honor остаются ручной приёмкой. Не публиковать.

Файлы: новые `client/lib/vpnn/{build_variant,connection_policy}.dart`, изменения contract/controller/provider/view, navigation/application/link/tray/hotkey и ARB. Новые тесты в `client/test/vpnn`, дополнения соседних suites. Дизайн следует существующим компонентам; новый UI-фреймворк не вводится.
