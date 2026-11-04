# Обезличенная карточка приёмки, версия 1

Одна карточка на критерий, маршрут, среду, семейство IP и повтор. В сводку CSV включить поля `run_id,case_id,repeat,source,platform,network,route,ip_family,verdict,egress,reason,evidence_ref`. Для полного результата использовать JSON по образцу. Идентификаторы прогона, сети и доказательств назначать случайно или порядково в пределах кампании. `evidence_ref` указывает на запись в закрытом реестре владельца.

~~~json
{
  "schema": 1,
  "run_id": "demo-01",
  "case_id": "AUTO",
  "repeat": 1,
  "source": "synthetic",
  "platform": "android-emulator",
  "network": "lab-01",
  "capture": "tun",
  "build_sha256": null,
  "config_alias": "fixture-01",
  "route": "auto",
  "actual_route": "synthetic-socks",
  "ip_family": "ipv4",
  "verdict": "PASS",
  "field_verdict": "NOT TESTED",
  "reason": "fallback-confirmed",
  "evidence_ref": "demo-01-e01",
  "egress": "synthetic",
  "controls": {
    "direct_tcp_blocked": null,
    "direct_udp_blocked": null,
    "direct_baseline_differs": null,
    "independent_https_ok": null,
    "receiver_probe_matched": null,
    "receiver_peer_matches_vps": null,
    "vps_egress_gone_after_stop": null
  },
  "metrics": null
}
~~~

- `source` принимает `synthetic`, `emulator-real` или `field`. Fake resolver, искусственные профили и числовые фикстуры всегда synthetic. Реальный транспорт на AVD может подтвердить egress в этой среде. `field_verdict` для обеих неполевых категорий всегда NOT TESTED.
- `verdict` принимает PASS, FAIL или NOT TESTED для указанной среды. PASS требует все обязательные доказательства по критерию. FAIL — наблюдаемое нарушение. При пропуске или недостатке доказательств ставить NOT TESTED с категорией причины, например `owner-window-required`, `missing-egress-control` или `ipv6-unavailable`. Отдельно хранить все повторы, включая ошибки.
- `platform` принимает `windows`, `honor`, `android-emulator`, `lab` или `vps`. `capture` принимает `tun`, `socks` или `none`. `ip_family` принимает `ipv4`, `ipv6` или null. Для NET записывать наблюдения до/во время/после по каждому протоколу как отдельные подслучаи.
- `egress` принимает `synthetic`, `unverified` или `vps-confirmed`. Последнее требует реального источника и контролей из протокола измерения. Неизвестное наблюдение — null. Для реального прогона добавить версию клиента и ОС, вариант пакета и SHA артефакта, версию подписанных настроек или обезличенный alias, категорию сети, семейство peer и относительные времена. Для performance добавить направление, общий интервал в секундах, выданные и активные устройства, полезные байты по участникам, CPU/RAM по узлу и методу, p50/p95, счётчики ошибок и причину остановки.
- Экспортировать поля из списка разрешённых. Секреты, приглашения, подписи конфигураций, ссылки на звонок, домены, IP, имена хостов, SSID, учётные записи, device ID, сырые логи и скриншоты остаются вне результата. Для IP записывать только семейство и факт совпадения. SHA-256 используется для пакета. Не хешировать секреты и IP для публикации. Категории ошибок фиксировать без текста исключения. Перед передачей вручную проверить значения, особенно добавленные поля и ссылки на доказательства.

## Офлайн-проверка

Из корня рабочей копии, Python 3.10+.

~~~powershell
python -B -m unittest discover -s tools/acceptance -v
python -B tools/acceptance/report.py tools/acceptance/synthetic.json
~~~

Вторая команда выводит 3 Mbit/s, 0,5 ядра и 32 MiB прироста, с `source=synthetic` и `field_verdict=NOT TESTED`. Скрипт читает только числовую фикстуру, принимает фиксированный набор полей и выводит результат в stdout. Полевые карточки оформляются по формату выше.
