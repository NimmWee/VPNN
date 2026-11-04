import 'dart:convert';
import 'dart:io';

import 'package:cryptography/cryptography.dart';
import 'package:fl_clash/vpnn/contract.dart';
import 'package:fl_clash/vpnn/repository.dart';
import 'package:flutter_test/flutter_test.dart';

import 'repository_test.dart' show MemoryCache, MemoryVault, signedRevocation;

class FailingCache extends MemoryCache {
  bool fail = false;
  @override
  Future<void> write(String value) async {
    if (fail) throw const FileSystemException('simulated interrupted write');
    await super.write(value);
  }
}

Future<List<int>> bundle(
  SimpleKeyPair key, {
  int version = 7,
  String device = 'device-a',
  String configDevice = 'device-a',
  String endpoint = 'https://unreachable.example.test',
  bool expired = false,
  List<String>? controlEndpoints,
  int? refreshAfter,
  List<Map<String, dynamic>>? profiles,
}) async {
  final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
  final public = await key.extractPublicKey();
  Future<Map<String, dynamic>> sign(Object value) async {
    final data = utf8.encode(jsonEncode(value));
    return {
      'payload': base64UrlEncode(data),
      'signature': base64UrlEncode(
        (await Ed25519().sign(data, keyPair: key)).bytes,
      ),
    };
  }

  final config = await sign({
    'schema': 1,
    'deviceId': configDevice,
    'version': version,
    'issuedAt': now - 60,
    'expiresAt': expired ? now - 1 : now + 3600,
    'controlEndpoints': ?controlEndpoints,
    'refreshAfter': ?refreshAfter,
    'profiles':
        profiles ??
        [
          {
            'id': 'dns',
            'name': 'DNS',
            'config': '{"proxies":[],"private":"profile-secret"}',
          },
        ],
  });
  final envelope = await sign({
    'schema': 1,
    'kind': 'bootstrap',
    'enrollment': {
      'endpoints': [endpoint],
      'token': 't' * 43,
      'key': base64UrlEncode(public.bytes),
      'device': device,
    },
    'configuration': config,
  });
  return utf8.encode(
    jsonEncode({'format': 'vpnn-bootstrap-v1', 'envelope': envelope}),
  );
}

Matcher failure(ConfigFailure value) =>
    isA<ConfigException>().having((error) => error.failure, 'failure', value);

void main() {
  test(
    'signed metadata retains multiple routes and skips future kinds safely',
    () async {
      final repository = ConfigurationRepository(
        vault: MemoryVault(),
        cache: MemoryCache(),
      );
      final key = await Ed25519().newKeyPair();
      final config = await repository.importBootstrap(
        await bundle(
          key,
          profiles: [
            {
              'id': 'first',
              'kind': 'direct',
              'priority': 5,
              'capabilities': ['tcp'],
              'minimumClientVersion': '0.1.6',
              'name': 'First',
              'config': '{}',
            },
            {
              'id': 'second',
              'kind': 'direct',
              'priority': 10,
              'name': 'Second',
              'config': '{}',
            },
            {
              'id': 'future',
              'kind': 'new-relay',
              'name': 'Future',
              'config': '{}',
            },
            {
              'id': 'disabled',
              'kind': 'vk',
              'enabled': false,
              'name': 'Disabled',
              'config': '{}',
            },
          ],
        ),
      );
      expect(config.profiles.length, 4);
      expect(config.profiles.where((p) => p.available).map((p) => p.id), [
        'first',
        'second',
      ]);
      expect(config.profiles.first.capabilities, ['tcp']);
      expect(config.profiles.first.connectionPriority, 5);
      final restored = ConfigurationRepository(
        vault: repository.vault,
        cache: repository.cache,
      );
      await restored.load();
      expect(restored.configuration?.profiles.length, 4);
    },
  );
  test(
    'wall clock rollback cannot extend cached access after restart',
    () async {
      final key = await Ed25519().newKeyPair();
      final vault = MemoryVault();
      final cache = MemoryCache();
      final now = DateTime.now();
      await ConfigurationRepository(
        vault: vault,
        cache: cache,
        now: () => now.add(const Duration(minutes: 20)),
      ).importBootstrap(await bundle(key));
      await expectLater(
        ConfigurationRepository(
          vault: vault,
          cache: cache,
          now: () => now,
        ).load(),
        throwsA(failure(ConfigFailure.expired)),
      );
    },
  );
  test(
    'signed endpoints migrate and survive restart with the same pinned identity',
    () async {
      final key = await Ed25519().newKeyPair();
      final vault = MemoryVault();
      final cache = MemoryCache();
      final repository = ConfigurationRepository(vault: vault, cache: cache);
      await repository.importBootstrap(
        await bundle(key, controlEndpoints: ['https://next.example.test']),
      );
      expect(repository.enrollment?.endpoints.single.host, 'next.example.test');
      final restored = ConfigurationRepository(vault: vault, cache: cache);
      await restored.load();
      expect(restored.enrollment?.endpoints.single.host, 'next.example.test');
      await expectLater(
        restored.importBootstrap(
          await bundle(
            key,
            version: 8,
            controlEndpoints: ['http://attacker.example.test'],
          ),
        ),
        throwsA(failure(ConfigFailure.malformed)),
      );
      expect(restored.enrollment?.endpoints.single.host, 'next.example.test');
    },
  );

  test(
    'interrupted cache commit recovers accepted version after restart',
    () async {
      final key = await Ed25519().newKeyPair();
      final vault = MemoryVault();
      final cache = FailingCache();
      final repository = ConfigurationRepository(vault: vault, cache: cache);
      await repository.importBootstrap(await bundle(key));
      cache.fail = true;
      await expectLater(
        repository.importBootstrap(await bundle(key, version: 8)),
        throwsA(isA<FileSystemException>()),
      );
      cache.fail = false;
      final restored = ConfigurationRepository(vault: vault, cache: cache);
      await restored.load();
      expect(restored.configuration?.version, 8);
    },
  );

  test(
    'offline bootstrap installs a verified encrypted cache without API access',
    () async {
      final key = await Ed25519().newKeyPair();
      final vault = MemoryVault();
      final cache = MemoryCache();
      final repository = ConfigurationRepository(vault: vault, cache: cache);
      var validated = false;
      final config = await repository.importBootstrap(
        await bundle(key),
        validate: (_) async {
          validated = true;
        },
      );
      expect(config.version, 7);
      expect(validated, isTrue);
      expect(repository.enrollment?.deviceId, 'device-a');
      expect(cache.text, isNot(contains('profile-secret')));
      expect(cache.text, isNot(contains('t' * 43)));
      final restored = ConfigurationRepository(vault: vault, cache: cache);
      await restored.load();
      expect(restored.configuration?.version, 7);
    },
  );

  test(
    'tampered invitation endpoint is rejected before changing stored access',
    () async {
      final key = await Ed25519().newKeyPair();
      final vault = MemoryVault();
      final cache = MemoryCache();
      final repository = ConfigurationRepository(vault: vault, cache: cache);
      final bytes = await bundle(key);
      await repository.importBootstrap(bytes);
      final previous = Map.of(vault.values);
      final cached = cache.text;
      final data = jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
      final envelope = data['envelope'] as Map<String, dynamic>;
      final payload =
          jsonDecode(utf8.decode(decode64(envelope['payload'] as String)))
              as Map<String, dynamic>;
      (payload['enrollment'] as Map<String, dynamic>)['endpoints'] = [
        'https://attacker.example.test',
      ];
      envelope['payload'] = base64UrlEncode(utf8.encode(jsonEncode(payload)));
      await expectLater(
        repository.importBootstrap(utf8.encode(jsonEncode(data))),
        throwsA(failure(ConfigFailure.signature)),
      );
      expect(vault.values, previous);
      expect(cache.text, cached);
    },
  );

  test(
    'offline import preserves rollback protection even before load is called',
    () async {
      final key = await Ed25519().newKeyPair();
      final vault = MemoryVault();
      final cache = MemoryCache();
      await ConfigurationRepository(
        vault: vault,
        cache: cache,
      ).importBootstrap(await bundle(key, version: 8));
      final restored = ConfigurationRepository(vault: vault, cache: cache);
      await expectLater(
        restored.importBootstrap(await bundle(key)),
        throwsA(failure(ConfigFailure.rollback)),
      );
    },
  );

  test('expired and wrong-device offline files are rejected', () async {
    final key = await Ed25519().newKeyPair();
    final repository = ConfigurationRepository(
      vault: MemoryVault(),
      cache: MemoryCache(),
    );
    await expectLater(
      repository.importBootstrap(await bundle(key, expired: true)),
      throwsA(failure(ConfigFailure.expired)),
    );
    await expectLater(
      repository.importBootstrap(await bundle(key, configDevice: 'device-b')),
      throwsA(failure(ConfigFailure.device)),
    );
    expect(repository.enrollment, isNull);
  });

  test('offline file cannot resurrect a confirmed revoked identity', () async {
    final key = await Ed25519().newKeyPair();
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(server.close);
    server.listen((request) async {
      request.response.statusCode = 403;
      request.response.write(
        await signedRevocation(
          key,
          'device-a',
          request.headers.value('X-VPNN-Nonce')!,
        ),
      );
      await request.response.close();
    });
    final bytes = await bundle(
      key,
      endpoint: 'http://127.0.0.1:${server.port}',
    );
    final vault = MemoryVault();
    final cache = MemoryCache();
    final repository = ConfigurationRepository(vault: vault, cache: cache);
    await repository.importBootstrap(bytes);
    await expectLater(
      repository.refresh(),
      throwsA(failure(ConfigFailure.revoked)),
    );
    final restored = ConfigurationRepository(vault: vault, cache: cache);
    await expectLater(
      restored.importBootstrap(bytes),
      throwsA(failure(ConfigFailure.revoked)),
    );
    expect(cache.text, isNull);
  });
}
