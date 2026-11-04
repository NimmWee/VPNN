import 'dart:async';

import 'package:fl_clash/vpnn/contract.dart';
import 'package:fl_clash/vpnn/controller.dart';
import 'package:fl_clash/vpnn/repository.dart';
import 'package:flutter_test/flutter_test.dart';

import 'repository_test.dart' show MemoryCache, MemoryVault;

class StubRepository extends ConfigurationRepository {
  StubRepository() : super(vault: MemoryVault(), cache: MemoryCache()) {
    enrollment = Enrollment(
      endpoints: [Uri.parse('https://example.test')],
      token: 't' * 43,
      publicKey: List.filled(32, 0),
      deviceId: 'device',
    );
    configuration = ManagedConfiguration(
      version: 1,
      expiresAt: DateTime.now().add(const Duration(days: 1)),
      profiles: const [
        ManagedProfile(id: 'direct', name: 'Direct', config: '{}'),
        ManagedProfile(id: 'vk', name: 'VK', config: '{}'),
      ],
    );
  }
  Completer<void>? wait;
  bool revoked = false;
  int refreshCalls = 0;
  @override
  Future<void> load() async {
    if (revoked) throw const ConfigException(ConfigFailure.revoked);
  }

  @override
  Future<ManagedConfiguration> refresh({
    Future<void> Function(ManagedConfiguration)? validate,
  }) async {
    refreshCalls++;
    await wait?.future;
    if (revoked) {
      configuration = null;
      throw const ConfigException(ConfigFailure.revoked);
    }
    await validate?.call(configuration!);
    return configuration!;
  }
}

class StubConnection implements ManagedConnection {
  @override
  bool suspended = false;
  final events = <String>[];
  Map<String, dynamic> status = const {'state': 'ready', 'captureReady': true};
  @override
  bool? get internet => true;
  @override
  Future<bool?> checkInternet() async => true;
  @override
  bool running = false;
  String mode = 'direct';
  @override
  String? activeMode(Enrollment enrollment) => mode;
  @override
  Future<void> validate(ManagedConfiguration config) async {}
  @override
  Future<void> install(
    Enrollment enrollment,
    ManagedConfiguration config,
  ) async {
    events.add('install');
  }

  @override
  Future<void> select(Enrollment enrollment, String mode) async {
    events.add('select:$mode');
    this.mode = mode;
  }

  @override
  Future<bool> setRunning(bool value) async {
    events.add(value ? 'start' : 'stop');
    running = value;
    return true;
  }

  @override
  Future<void> remove(Enrollment enrollment) async {
    events.add('remove');
  }

  @override
  Future<Map<String, dynamic>> transportStatus() async => status;
}

class ExpiringConnection extends StubConnection
    implements ManagedProfileUpdates {
  @override
  Future<bool> needsReload(
    Enrollment enrollment,
    ManagedConfiguration config,
    String mode,
  ) async => true;
}

void main() {
  test(
    'refresh applies renewed access deadline through existing owner',
    () async {
      final connection = ExpiringConnection();
      final controller = VpnnController(
        repository: StubRepository(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      connection.running = true;
      connection.events.clear();
      expect(await controller.refresh(), isTrue);
      expect(
        connection.events,
        containsAllInOrder(['stop', 'install', 'select:direct', 'start']),
      );
    },
  );
  test(
    'lost system capture stops an established tunnel without protocol retries',
    () async {
      final connection = StubConnection();
      final controller = VpnnController(
        repository: StubRepository(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.setAutomaticFallback(true);
      expect(await controller.connect(), isTrue);
      connection.status = {'state': 'ready', 'captureReady': false};
      await controller.refreshTransportStatus();
      expect(connection.running, isFalse);
      expect(controller.failure?.name, 'capture');
      expect(connection.events, isNot(contains('select:vk')));
    },
  );

  test('ready transport without system capture is stopped', () async {
    final connection = StubConnection()
      ..status = {'state': 'ready', 'captureReady': false};
    final controller = VpnnController(
      repository: StubRepository(),
      connection: connection,
      poll: false,
    );
    addTearDown(controller.dispose);
    await controller.initialize();
    expect(await controller.connect(), isFalse);
    expect(connection.running, isFalse);
    expect(controller.failure?.name, 'capture');
  });

  test(
    'transport failure stops the tunnel through its existing owner',
    () async {
      final connection = StubConnection();
      final controller = VpnnController(
        repository: StubRepository(),
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.selectMode('vk');
      connection.running = true;
      connection.status = {'mode': 'vk', 'state': 'error'};
      await controller.refreshTransportStatus();
      expect(connection.running, isFalse);
      expect(connection.events.last, 'stop');
      expect(controller.failure, ConfigFailure.network);
      expect(controller.transport['state'], 'error');
    },
  );

  test(
    'switch requests stop before profile selection and restart through the owner',
    () async {
      final repository = StubRepository();
      final connection = StubConnection();
      final controller = VpnnController(
        repository: repository,
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      connection.events.clear();
      connection.running = true;
      expect(await controller.selectMode('vk'), isTrue);
      expect(
        connection.events,
        containsAllInOrder(['stop', 'select:vk', 'start']),
      );
      expect(controller.selectedMode, 'vk');
    },
  );

  test(
    'disconnect during refresh cancels the pending connect intent',
    () async {
      final repository = StubRepository();
      final connection = StubConnection();
      final controller = VpnnController(
        repository: repository,
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      connection.events.clear();
      repository.configuration = ManagedConfiguration(
        version: 1,
        expiresAt: DateTime.now().subtract(const Duration(seconds: 1)),
        profiles: repository.configuration!.profiles,
      );
      repository.wait = Completer<void>();
      final connecting = controller.connect();
      await Future<void>.delayed(Duration.zero);
      await controller.disconnect();
      repository.wait!.complete();
      expect(await connecting, isFalse);
      expect(connection.events, isNot(contains('start')));
      expect(connection.running, isFalse);
    },
  );

  test(
    'confirmed revocation stops the connection and removes managed profiles',
    () async {
      final repository = StubRepository();
      final connection = StubConnection();
      final controller = VpnnController(
        repository: repository,
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      connection.events.clear();
      connection.running = true;
      repository.revoked = true;
      expect(await controller.refresh(), isFalse);
      expect(connection.events, containsAllInOrder(['stop', 'remove']));
      expect(controller.failure, ConfigFailure.revoked);
      expect(connection.running, isFalse);
      expect(controller.usingCache, isFalse);
    },
  );

  test(
    'valid cached access connects without waiting for configuration delivery',
    () async {
      final repository = StubRepository();
      final connection = StubConnection();
      final controller = VpnnController(
        repository: repository,
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      repository.wait = Completer<void>();
      final connecting = controller.connect();
      await Future<void>.delayed(Duration.zero);
      final requestsBeforeConnection = repository.refreshCalls;
      repository.wait!.complete();
      expect(await connecting, isTrue);
      expect(requestsBeforeConnection, 0);
      expect(connection.running, isTrue);
    },
  );

  test(
    'startup with a valid cache does not wait for the configuration server',
    () async {
      final repository = StubRepository()..wait = Completer<void>();
      final controller = VpnnController(
        repository: repository,
        connection: StubConnection(),
      );
      addTearDown(controller.dispose);
      final initializing = controller.initialize();
      await Future<void>.delayed(Duration.zero);
      final requestsAtStartup = repository.refreshCalls;
      repository.wait!.complete();
      await initializing;
      expect(requestsAtStartup, 0);
      expect(controller.initialized, isTrue);
    },
  );

  test(
    'confirmed revocation on startup removes any in-memory cached configuration',
    () async {
      final repository = StubRepository()..revoked = true;
      final connection = StubConnection();
      final controller = VpnnController(
        repository: repository,
        connection: connection,
        poll: false,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      expect(controller.configuration, isNull);
      expect(await controller.connect(), isFalse);
      expect(connection.events, isNot(contains('start')));
    },
  );
}
