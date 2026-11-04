import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:cryptography/cryptography.dart';
import 'package:fl_clash/vpnn/bootstrap.dart';
import 'package:fl_clash/vpnn/config_transport.dart';
import 'package:fl_clash/vpnn/contract.dart';
import 'package:fl_clash/vpnn/repository.dart';
import 'package:flutter_test/flutter_test.dart';

import 'bootstrap_test.dart' show bundle, failure;
import 'repository_test.dart' show MemoryCache, MemoryVault;

void main() {
  test(
    'refresh deadline also bounds validation and rejects its late result',
    () async {
      final key = await Ed25519().newKeyPair();
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() => server.close(force: true));
      final next = await decodeOfflineBootstrap(await bundle(key, version: 8));
      server.listen((request) async {
        request.response.write(jsonEncode(next.configuration));
        await request.response.close();
      });
      final repository = ConfigurationRepository(
        vault: MemoryVault(),
        cache: MemoryCache(),
        refreshTimeout: const Duration(milliseconds: 100),
      );
      await repository.importBootstrap(
        await bundle(key, endpoint: 'http://127.0.0.1:${server.port}'),
      );
      final release = Completer<void>();
      final pending = repository.refresh(validate: (_) => release.future);
      await expectLater(
        pending.timeout(const Duration(seconds: 2)),
        throwsA(failure(ConfigFailure.network)),
      );
      release.complete();
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(repository.configuration?.version, 7);
    },
  );
  test(
    'one refresh deadline bounds a stalled API and retains the cache',
    () async {
      final key = await Ed25519().newKeyPair();
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() => server.close(force: true));
      server.listen((request) {});
      final repository = ConfigurationRepository(
        vault: MemoryVault(),
        cache: MemoryCache(),
        refreshTimeout: const Duration(milliseconds: 100),
      );
      await repository.importBootstrap(
        await bundle(key, endpoint: 'http://127.0.0.1:${server.port}'),
      );
      await expectLater(
        repository.refresh().timeout(const Duration(seconds: 2)),
        throwsA(failure(ConfigFailure.network)),
      );
      expect(repository.configuration?.version, 7);
    },
  );
  for (final mode in ['vk', 'dns']) {
    test(
      'signed update uses selected $mode proxy with direct API unavailable',
      () async {
        final key = await Ed25519().newKeyPair();
        final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
        final unavailable = 'http://127.0.0.1:${socket.port}';
        await socket.close();
        final proxy = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(proxy.close);
        final next = await decodeOfflineBootstrap(
          await bundle(key, version: 8),
        );
        var status = 200;
        proxy.listen((request) async {
          request.response.statusCode = status;
          if (status == 200) {
            request.response.write(jsonEncode(next.configuration));
          }
          await request.response.close();
        });
        final repository = ConfigurationRepository(
          vault: MemoryVault(),
          cache: MemoryCache(),
          transport: () => ConfigTransport.core(port: proxy.port, mode: mode),
        );
        await repository.importBootstrap(
          await bundle(key, endpoint: unavailable),
        );
        expect((await repository.refresh()).version, 8);
        expect(repository.lastRefreshMode, mode);
        status = 407;
        await expectLater(
          repository.refresh(),
          throwsA(failure(ConfigFailure.network)),
        );
        expect(repository.configuration?.version, 8);
        status = 403;
        await expectLater(
          repository.refresh(),
          throwsA(failure(ConfigFailure.network)),
        );
        expect(repository.configuration?.version, 8);
      },
    );
  }

  test('Stop during validation prevents a late configuration commit', () async {
    final key = await Ed25519().newKeyPair();
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(server.close);
    final next = await decodeOfflineBootstrap(await bundle(key, version: 8));
    server.listen((request) async {
      request.response.write(jsonEncode(next.configuration));
      await request.response.close();
    });
    final cache = MemoryCache();
    final repository = ConfigurationRepository(
      vault: MemoryVault(),
      cache: cache,
    );
    await repository.importBootstrap(
      await bundle(key, endpoint: 'http://127.0.0.1:${server.port}'),
    );
    final previous = cache.text;
    final entered = Completer<void>();
    final release = Completer<void>();
    final update = repository.refresh(
      validate: (_) async {
        entered.complete();
        await release.future;
      },
    );
    await entered.future;
    repository.cancelPending();
    release.complete();
    await expectLater(update, throwsA(failure(ConfigFailure.network)));
    expect(cache.text, previous);
    expect(repository.configuration?.version, 7);
  });
}
