import 'dart:convert';

import 'package:fl_clash/vpnn/controller.dart';
import 'package:fl_clash/vpnn/diagnostics.dart';
import 'package:flutter_test/flutter_test.dart';

import 'controller_test.dart' show StubConnection, StubRepository;
import 'fallback_test.dart' show FallbackConnection;

void main() {
  test('manual CAPTCHA completion clears the waiting stage', () async {
    final connection = FallbackConnection()..states['vk'] = 'captcha';
    final controller = VpnnController(
      repository: StubRepository(),
      connection: connection,
      poll: false,
    );
    addTearDown(controller.dispose);
    await controller.selectMode('vk');
    expect(await controller.connect(), isTrue);
    expect(controller.stage, ConnectionStage.captcha);
    connection.states['vk'] = 'ready';
    await controller.refreshTransportStatus();
    expect(controller.stage, ConnectionStage.ready);
  });
  test(
    'connection reports ordered stages and disconnect returns to idle',
    () async {
      final controller = VpnnController(
        repository: StubRepository(),
        connection: StubConnection(),
        poll: false,
      );
      addTearDown(controller.dispose);
      final stages = <ConnectionStage>[];
      controller.addListener(() => stages.add(controller.stage));
      expect(await controller.connect(), isTrue);
      expect(
        stages,
        containsAllInOrder([
          ConnectionStage.selecting,
          ConnectionStage.systemTunnel,
          ConnectionStage.transport,
          ConnectionStage.checking,
          ConnectionStage.ready,
        ]),
      );
      await controller.disconnect();
      expect(controller.stage, ConnectionStage.idle);
    },
  );

  test(
    'diagnostic export uses an allowlist and bounds event history',
    () async {
      final connection = StubConnection()
        ..status = {
          'state': 'ready',
          'captureReady': true,
          'captchaUrl': 'https://vk.com/secret',
          'error': 'cookie=secret',
          'counters': {
            'dnsTxBytes': 123,
            'dnsRxDropped': 2,
            'token': 'secret',
            'vkRxBytes': 'secret',
          },
        };
      final controller = VpnnController(
        repository: StubRepository(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      for (var i = 0; i < 12; i++) {
        await controller.connect();
        await controller.disconnect();
      }
      await controller.connect();
      final report = controller.diagnosticReport(version: '0.1.3+4');
      final encoded = jsonEncode(report);
      expect(encoded, isNot(contains('secret')));
      expect(encoded, isNot(contains('device')));
      expect(encoded, isNot(contains('example.test')));
      expect((report['events'] as List).length, lessThanOrEqualTo(32));
      expect((report['counters'] as Map)['dnsTxBytes'], 123);
      expect(report['systemEgressVerified'], isFalse);
    },
  );
}
