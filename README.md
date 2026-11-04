# VPNN для Android и Windows

Актуальный локальный кандидат — **0.1.6+7**. В пользовательской сборке видны назначенные маршруты, Auto и фактический маршрут. Администрирование и подписанные настройки обслуживает существующая VPS.

- [Пакеты 0.1.6+7 и SHA-256](artifacts/p2-local/MANIFEST.json).
- [Результаты P2 и оставшиеся проверки](docs/specs/2026-11-03/11-P2-SPRINT-RESULT.md).
- [Спецификации и план следующих фаз](docs/specs/2026-11-03/README.md).
- [Инструкция владельца](docs/OPERATOR-GUIDE.md), [восстановление](deploy/README.md).

Для локальной приёмки Windows распакуйте весь ZIP 0.1.6 и вручную запустите VPNN.exe из распакованной папки. Действующий комплект 0.1.2+3 для возврата указан в [LATEST.json](artifacts/LATEST.json). Start-VPNN-Release.cmd относится к этому комплекту. Start-VPNN.cmd запускает локальную отладочную сборку SAFE_MODE.

## Сборка

В PowerShell из корня проекта загрузите окружение командой `. .\tools\env.ps1`. Для подписанных Android APK выполните `.\tools\build-android-release.ps1 -Version 0.1.6 -BuildNumber 7`. Для Windows из каталога client выполните `flutter build windows --release --no-pub --build-name=0.1.6 --build-number=7 --dart-define=SAFE_MODE=false`. Расширенный интерфейс доступен при `--dart-define=VPNN_ADMIN=true`.

Сборки и Flutter-тесты запускайте последовательно: нативные сборочные шаги используют общие каталоги. Версии инструментов и исходников закреплены в файлах lock. Уведомления о лицензиях находятся в [NOTICES.md](NOTICES.md).
