import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:fl_clash/vpnn/contract.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('invitation requires pinned key, device identity and a safe server URL', () {
    expect(
      () => Enrollment.parse('https://example.test'),
      throwsFormatException,
    );
    expect(
      () => Enrollment.parse(
        'vpnn://enroll?url=http%3A%2F%2Fevil.test&token=secret&key=bad&device=x',
      ),
      throwsFormatException,
    );
    final key = base64UrlEncode(List.filled(32, 1));
    final invite = Enrollment.parse(
      'vpnn://enroll?url=https%3A%2F%2Fcontrol.example.test&token=${'t' * 43}&key=$key&device=device-a',
    );
    expect(invite.deviceId, 'device-a');
    expect(invite.endpoints.single.host, 'control.example.test');
    expect(invite.toString(), isNot(contains('t' * 43)));
  });

  test(
    'signed configuration rejects tampering, wrong device and rollback',
    () async {
      final algorithm = Ed25519();
      final key = await algorithm.newKeyPair();
      final public = await key.extractPublicKey();
      final enrollment = Enrollment(
        endpoints: [Uri.parse('https://control.example.test')],
        token: 't' * 43,
        publicKey: public.bytes,
        deviceId: 'device-a',
      );
      final now = DateTime.utc(2026, 11, 2);
      Future<Map<String, dynamic>> envelope({
        String device = 'device-a',
        int version = 20,
      }) async {
        final payload = utf8.encode(
          jsonEncode({
            'schema': 1,
            'deviceId': device,
            'version': version,
            'issuedAt': now.millisecondsSinceEpoch ~/ 1000,
            'expiresAt':
                now.add(const Duration(days: 1)).millisecondsSinceEpoch ~/ 1000,
            'profiles': [
              {'id': 'direct', 'name': 'Direct', 'config': '{"proxies":[]}'},
            ],
          }),
        );
        final signature = await algorithm.sign(payload, keyPair: key);
        return {
          'payload': base64UrlEncode(payload),
          'signature': base64UrlEncode(signature.bytes),
        };
      }

      final valid = await envelope();
      final config = await verifyConfiguration(
        valid,
        enrollment,
        now: now,
        minimumVersion: 19,
      );
      expect(config.version, 20);
      await expectLater(
        verifyConfiguration(
          {...valid, 'signature': base64UrlEncode(List.filled(64, 0))},
          enrollment,
          now: now,
        ),
        throwsA(isA<ConfigException>()),
      );
      await expectLater(
        verifyConfiguration(
          await envelope(device: 'device-b'),
          enrollment,
          now: now,
        ),
        throwsA(isA<ConfigException>()),
      );
      await expectLater(
        verifyConfiguration(
          await envelope(version: 18),
          enrollment,
          now: now,
          minimumVersion: 19,
        ),
        throwsA(isA<ConfigException>()),
      );
      await expectLater(
        verifyConfiguration(
          valid,
          enrollment,
          now: now.add(const Duration(days: 2)),
        ),
        throwsA(isA<ConfigException>()),
      );
    },
  );
}
