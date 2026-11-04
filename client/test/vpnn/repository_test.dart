import 'dart:convert';
import 'dart:io';

import 'package:cryptography/cryptography.dart';
import 'package:fl_clash/vpnn/contract.dart';
import 'package:fl_clash/vpnn/repository.dart';
import 'package:flutter_test/flutter_test.dart';

Future<String> signedRevocation(
  SimpleKeyPair key,
  String device,
  String nonce,
) async {
  final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
  final data = utf8.encode(
    jsonEncode({
      'schema': 1,
      'kind': 'revocation',
      'deviceId': device,
      'nonce': nonce,
      'version': 100,
      'issuedAt': now,
      'expiresAt': now + 300,
    }),
  );
  return jsonEncode({
    'payload': base64UrlEncode(data),
    'signature': base64UrlEncode(
      (await Ed25519().sign(data, keyPair: key)).bytes,
    ),
  });
}

class MemoryVault implements SecretVault {
  final values = <String, String>{};
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }
}

class MemoryCache implements ConfigurationCache {
  String? text;
  String? pending;
  @override
  Future<String?> readPending() async => pending;
  @override
  Future<void> writePending(String value) async {
    pending = value;
  }

  @override
  Future<void> clearPending() async {
    pending = null;
  }

  @override
  Future<String?> read() async => text;
  @override
  Future<void> write(String value) async {
    text = value;
  }

  @override
  Future<void> clear() async {
    text = null;
  }
}

void main() {
  test('revocation signature is bound to nonce, device and version', () async {
    final key = await Ed25519().newKeyPair();
    final enrollment = Enrollment(
      endpoints: [Uri.parse('https://example.test')],
      token: 't' * 43,
      publicKey: (await key.extractPublicKey()).bytes,
      deviceId: 'device',
    );
    final bytes = utf8.encode(
      await signedRevocation(key, 'device', 'current-nonce'),
    );
    expect(
      await verifyRevocation(
        bytes,
        enrollment,
        nonce: 'current-nonce',
        minimumVersion: 1,
      ),
      isTrue,
    );
    expect(
      await verifyRevocation(
        bytes,
        enrollment,
        nonce: 'previous-nonce',
        minimumVersion: 1,
      ),
      isFalse,
    );
    expect(
      await verifyRevocation(
        bytes,
        enrollment,
        nonce: 'current-nonce',
        minimumVersion: 101,
      ),
      isFalse,
    );
    expect(
      await verifyRevocation(
        utf8.encode(
          await signedRevocation(key, 'other-device', 'current-nonce'),
        ),
        enrollment,
        nonce: 'current-nonce',
        minimumVersion: 1,
      ),
      isFalse,
    );
    expect(
      await verifyRevocation(
        utf8.encode('{}'),
        enrollment,
        nonce: 'current-nonce',
        minimumVersion: 1,
      ),
      isFalse,
    );
  });
  test(
    'authenticated signed updates encrypt cache, resist rollback and erase it on revoke',
    () async {
      final algorithm = Ed25519();
      final key = await algorithm.newKeyPair();
      final public = await key.extractPublicKey();
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(server.close);
      var version = 2;
      var revoked = false;
      final requests = <String?>[];
      server.listen((request) async {
        requests.add(request.headers.value(HttpHeaders.authorizationHeader));
        if (revoked) {
          request.response.statusCode = 403;
          request.response.write(
            await signedRevocation(
              key,
              'test-device',
              request.headers.value('X-VPNN-Nonce')!,
            ),
          );
        } else {
          final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
          final data = utf8.encode(
            jsonEncode({
              'schema': 1,
              'deviceId': 'test-device',
              'version': version,
              'issuedAt': now,
              'expiresAt': now + 3600,
              'profiles': [
                {
                  'id': 'direct',
                  'name': 'Direct',
                  'config': '{"proxies":[],"private":"hidden-profile-secret"}',
                },
              ],
            }),
          );
          final signature = await algorithm.sign(data, keyPair: key);
          request.response.write(
            jsonEncode({
              'payload': base64UrlEncode(data),
              'signature': base64UrlEncode(signature.bytes),
            }),
          );
        }
        await request.response.close();
      });
      final enrollment = Enrollment(
        endpoints: [Uri.parse('http://127.0.0.1:${server.port}')],
        token: 'individual-token-${'x' * 32}',
        publicKey: public.bytes,
        deviceId: 'test-device',
      );
      final vault = MemoryVault();
      final cache = MemoryCache();
      final repository = ConfigurationRepository(vault: vault, cache: cache);
      await repository.enroll(enrollment);
      expect(repository.configuration?.version, 2);
      expect(requests.single, 'Bearer ${enrollment.token}');
      expect(cache.text, isNot(contains('hidden-profile-secret')));
      expect(cache.text, isNot(contains(enrollment.token)));
      final older = cache.text;
      version = 3;
      await repository.refresh();
      cache.text = older;
      final restored = ConfigurationRepository(vault: vault, cache: cache);
      await expectLater(restored.load(), throwsA(isA<ConfigException>()));
      revoked = true;
      await expectLater(
        repository.refresh(),
        throwsA(
          isA<ConfigException>().having(
            (e) => e.failure,
            'failure',
            ConfigFailure.revoked,
          ),
        ),
      );
      expect(cache.text, isNull);
      expect(repository.configuration, isNull);
      final afterRevoke = ConfigurationRepository(vault: vault, cache: cache);
      await expectLater(
        afterRevoke.load(),
        throwsA(
          isA<ConfigException>().having(
            (e) => e.failure,
            'failure',
            ConfigFailure.revoked,
          ),
        ),
      );
    },
  );
}
