import 'dart:async';

import 'package:fl_clash/vpnn/contract.dart';
import 'package:fl_clash/vpnn/controller.dart';
import 'package:flutter_test/flutter_test.dart';

import 'controller_test.dart' show StubConnection, StubRepository;
import 'fallback_test.dart' show FallbackConnection, repositoryWithDNS;

class PendingStart extends StubConnection {
  final entered = Completer<void>();
  final release = Completer<void>();
  @override
  Future<bool> setRunning(bool value) async {
    if (value) {
      entered.complete();
      await release.future;
    }
    return super.setRunning(value);
  }
}

class PendingCapture extends StubConnection {
  int calls = 0;
  @override
  Future<Map<String, dynamic>> transportStatus() async => {
    'state': 'idle',
    'captureReady': ++calls > 1,
  };
}

void main() {
  test(
    'missing native status cannot confirm capture for a direct route',
    () async {
      final connection = StubConnection()..status = const {};
      final controller = VpnnController(
        repository: StubRepository(),
        connection: connection,
        poll: false,
        transportTimeout: const Duration(milliseconds: 40),
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      expect(await controller.connect(), isFalse);
      expect(connection.running, isFalse);
    },
  );

  test(
    'ordinary profile waits for native capture readiness before HTTPS',
    () async {
      final connection = PendingCapture();
      final controller = VpnnController(
        repository: StubRepository(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      expect(await controller.connect(), isTrue);
      expect(connection.calls, greaterThanOrEqualTo(2));
      expect(connection.running, isTrue);
    },
  );
  test(
    'Stop releases a pending health check without waiting for its answer',
    () async {
      final wait = Completer<bool?>();
      final connection = FallbackConnection()..healthWait = wait;
      final controller = VpnnController(
        repository: StubRepository(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      final connecting = controller.connect();
      while (!controller.checkingInternet) {
        await Future<void>.delayed(Duration.zero);
      }
      await controller.disconnect();
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(controller.busy, isFalse);
      expect(await connecting, isFalse);
      wait.complete(true);
      await Future<void>.delayed(Duration.zero);
      expect(connection.running, isFalse);
    },
  );
  test(
    'new user defaults to auto, preserves an explicit old fallback preference',
    () async {
      final repository = StubRepository();
      final controller = VpnnController(
        repository: repository,
        connection: StubConnection(),
        poll: false,
        defaultAutomatic: true,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      expect(controller.automaticSelection, isTrue);
      expect(controller.automaticFallback, isTrue);
      await controller.selectManualMode('vk');
      expect(controller.automaticSelection, isFalse);
      expect(controller.selectedMode, 'vk');
      final restored = VpnnController(
        repository: repository,
        connection: StubConnection(),
        poll: false,
        defaultAutomatic: true,
      );
      addTearDown(restored.dispose);
      await restored.initialize();
      expect(restored.automaticSelection, isFalse);
      expect(restored.selectedMode, 'vk');
    },
  );

  test('unknown HTTPS result never becomes a ready connection', () async {
    final connection = FallbackConnection()
      ..healthWait = (Completer<bool?>()..complete(null));
    final controller = VpnnController(
      repository: StubRepository(),
      connection: connection,
      poll: false,
    );
    addTearDown(controller.dispose);
    await controller.initialize();
    expect(await controller.connect(), isFalse);
    expect(connection.running, isFalse);
    expect(controller.routesExhausted, isTrue);
  });

  test(
    'Stop reconciles a delayed start and never revives on network change',
    () async {
      final connection = PendingStart();
      final controller = VpnnController(
        repository: StubRepository(),
        connection: connection,
        poll: false,
        defaultAutomatic: true,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      final connecting = controller.connect();
      await connection.entered.future;
      final stopping = controller.disconnect();
      connection.release.complete();
      await stopping;
      expect(await connecting, isFalse);
      expect(connection.running, isFalse);
      await controller.networkChanged(available: true);
      expect(connection.running, isFalse);
    },
  );

  test(
    'manual selection supersedes an in-flight probe through one executor',
    () async {
      final wait = Completer<bool?>();
      final connection = FallbackConnection()..healthWait = wait;
      final controller = VpnnController(
        repository: repositoryWithDNS(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      final first = controller.connect();
      while (!controller.checkingInternet) {
        await Future<void>.delayed(Duration.zero);
      }
      final next = controller.selectManualMode('vk');
      connection.healthWait = null;
      wait.complete(false);
      expect(await first, isFalse);
      expect(await next, isTrue);
      expect(controller.selectedMode, 'vk');
      expect(connection.running, isTrue);
      expect(connection.events.where((event) => event == 'start').length, 2);
    },
  );

  test(
    'automatic network recovery respects Stop and invalidates last good',
    () async {
      final connection = FallbackConnection();
      final controller = VpnnController(
        repository: repositoryWithDNS(),
        connection: connection,
        poll: false,
        defaultAutomatic: true,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      expect(await controller.connect(), isTrue);
      await controller.networkChanged(available: false);
      expect(connection.running, isFalse);
      expect(controller.networkAvailable, isFalse);
      await controller.networkChanged(available: true);
      expect(connection.running, isTrue);
      await controller.disconnect();
      final starts = connection.events
          .where((event) => event == 'start')
          .length;
      await controller.networkChanged(available: true);
      expect(
        connection.events.where((event) => event == 'start').length,
        starts,
      );
    },
  );

  test('one overall deadline bounds a connecting transport', () async {
    final connection = FallbackConnection()..states['vk'] = 'connecting';
    final repository = StubRepository();
    final old = repository.configuration!;
    repository.configuration = ManagedConfiguration(
      version: old.version,
      expiresAt: old.expiresAt,
      profiles: old.profiles.where((p) => p.id == 'vk').toList(),
    );
    final controller = VpnnController(
      repository: repository,
      connection: connection,
      poll: false,
      connectionTimeout: const Duration(milliseconds: 80),
    );
    addTearDown(controller.dispose);
    await controller.initialize();
    expect(
      await controller.connect().timeout(const Duration(seconds: 2)),
      isFalse,
    );
    expect(connection.running, isFalse);
  });
}
