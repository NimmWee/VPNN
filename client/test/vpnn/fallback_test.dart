import 'dart:async';

import 'package:fl_clash/vpnn/contract.dart';
import 'package:fl_clash/vpnn/controller.dart';
import 'package:flutter_test/flutter_test.dart';

import 'controller_test.dart' show StubConnection, StubRepository;

StubRepository repositoryWithDNS() {
  final repository = StubRepository();
  final previous = repository.configuration!;
  repository.configuration = ManagedConfiguration(
    version: previous.version,
    expiresAt: previous.expiresAt,
    profiles: [
      ...previous.profiles,
      const ManagedProfile(id: 'dns', name: 'DNS', config: '{}'),
    ],
  );
  return repository;
}

class FallbackConnection extends StubConnection {
  final states = <String, String>{};
  final reachable = <String, bool>{};
  Completer<bool?>? healthWait;
  bool? _internet;

  @override
  bool? get internet => _internet;

  @override
  Future<bool?> checkInternet() async {
    _internet = healthWait != null
        ? await healthWait!.future
        : reachable[mode] ?? true;
    return _internet;
  }

  @override
  Future<Map<String, dynamic>> transportStatus() async => {
    'mode': mode,
    'state': states[mode] ?? 'ready',
    'captureReady': true,
  };
}

class DeclinedConnection extends FallbackConnection {
  @override
  Future<bool> setRunning(bool value) async {
    if (!value) return super.setRunning(value);
    events.add('declined');
    return false;
  }
}

void main() {
  test('declined owner startup does not retry other profiles', () async {
    final connection = DeclinedConnection();
    final controller = VpnnController(
      repository: repositoryWithDNS(),
      connection: connection,
      poll: false,
    );
    addTearDown(controller.dispose);
    await controller.initialize();
    await controller.setAutomaticFallback(true);
    expect(await controller.connect(), isFalse);
    expect(connection.events.where((e) => e == 'declined').length, 1);
  });
  test('on-demand suspension never starts another transport', () async {
    final connection = FallbackConnection()..suspended = true;
    final controller = VpnnController(
      repository: repositoryWithDNS(),
      connection: connection,
      poll: false,
    );
    addTearDown(controller.dispose);
    await controller.initialize();
    await controller.setAutomaticFallback(true);
    await controller.selectMode('vk');
    expect(await controller.connect(), isTrue);
    connection.states['vk'] = 'error';
    await controller.refreshTransportStatus();
    expect(connection.mode, 'vk');
    expect(connection.events.where((e) => e == 'start').length, 1);
    expect(controller.failure, isNull);
  });

  test('exhausted runtime fallback stops the failed tunnel', () async {
    final repository = repositoryWithDNS();
    final previous = repository.configuration!;
    repository.configuration = ManagedConfiguration(
      version: previous.version,
      expiresAt: previous.expiresAt,
      profiles: previous.profiles.where((p) => p.id != 'direct').toList(),
    );
    final connection = FallbackConnection()..states['vk'] = 'captcha';
    final controller = VpnnController(
      repository: repository,
      connection: connection,
      poll: false,
    );
    addTearDown(controller.dispose);
    await controller.initialize();
    await controller.setAutomaticFallback(true);
    await controller.selectMode('vk');
    expect(await controller.connect(), isTrue);
    expect(connection.mode, 'dns');
    connection.states['dns'] = 'error';
    await controller.refreshTransportStatus();
    expect(connection.running, isFalse);
    expect(controller.failure, ConfigFailure.network);
  });

  test(
    'opt-in fallback skips a VK CAPTCHA and connects assigned direct mode',
    () async {
      final connection = FallbackConnection()..states['vk'] = 'captcha';
      final controller = VpnnController(
        repository: repositoryWithDNS(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.setAutomaticFallback(true);
      await controller.selectMode('vk');
      expect(await controller.connect(), isTrue);
      expect(controller.selectedMode, 'direct');
      expect(controller.usedFallback, isTrue);
      expect(
        connection.events,
        containsAllInOrder([
          'select:vk',
          'start',
          'stop',
          'select:direct',
          'start',
        ]),
      );
    },
  );

  test(
    'fallback uses DNS when it is the only remaining assigned mode',
    () async {
      final repository = repositoryWithDNS();
      final old = repository.configuration!;
      repository.configuration = ManagedConfiguration(
        version: old.version,
        expiresAt: old.expiresAt,
        profiles: old.profiles.where((item) => item.id != 'direct').toList(),
      );
      final connection = FallbackConnection()..states['vk'] = 'captcha';
      final controller = VpnnController(
        repository: repository,
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.setAutomaticFallback(true);
      await controller.selectMode('vk');
      expect(await controller.connect(), isTrue);
      expect(controller.selectedMode, 'dns');
      expect(connection.running, isTrue);
    },
  );

  test(
    'a failed HTTPS path is replaced even if its transport reports ready',
    () async {
      final connection = FallbackConnection()..reachable['direct'] = false;
      final controller = VpnnController(
        repository: repositoryWithDNS(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.setAutomaticFallback(true);
      expect(await controller.connect(), isTrue);
      expect(controller.selectedMode, 'vk');
    },
  );

  test(
    'manual mode preserves the CAPTCHA prompt without silently switching',
    () async {
      final connection = FallbackConnection()..states['vk'] = 'captcha';
      final controller = VpnnController(
        repository: repositoryWithDNS(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.selectMode('vk');
      expect(await controller.connect(), isTrue);
      expect(controller.selectedMode, 'vk');
      expect(controller.transport['state'], 'captcha');
      expect(connection.events, isNot(contains('select:dns')));
    },
  );

  test(
    'all failed modes are attempted once and leave no running tunnel',
    () async {
      final connection = FallbackConnection()
        ..states.addAll({'vk': 'error', 'dns': 'error'})
        ..reachable['direct'] = false;
      final controller = VpnnController(
        repository: repositoryWithDNS(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.setAutomaticFallback(true);
      expect(await controller.connect(), isFalse);
      expect(
        connection.events.where((event) => event == 'start'),
        hasLength(3),
      );
      expect(connection.running, isFalse);
    },
  );

  test(
    'disconnect during HTTPS checking cancels the pending fallback',
    () async {
      final connection = FallbackConnection()..healthWait = Completer<bool?>();
      final controller = VpnnController(
        repository: repositoryWithDNS(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.setAutomaticFallback(true);
      final connecting = controller.connect();
      await pumpEventQueue();
      await controller.disconnect();
      connection.healthWait!.complete(false);
      expect(await connecting, isFalse);
      expect(connection.events, isNot(contains('select:vk')));
      expect(connection.running, isFalse);
    },
  );

  test('automatic fallback preference survives a controller restart', () async {
    final repository = repositoryWithDNS();
    final first = VpnnController(
      repository: repository,
      connection: FallbackConnection(),
      poll: false,
    );
    await first.initialize();
    await first.setAutomaticFallback(true);
    first.dispose();
    final second = VpnnController(
      repository: repository,
      connection: FallbackConnection(),
      poll: false,
    );
    addTearDown(second.dispose);
    await second.initialize();
    expect(second.automaticFallback, isTrue);
  });
}
