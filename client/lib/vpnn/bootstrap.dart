import 'dart:convert';
import 'dart:isolate';

import 'package:cryptography/cryptography.dart';

import 'contract.dart';

const maxBootstrapBytes = 2100000;

class OfflineBootstrap {
  const OfflineBootstrap(this.enrollment, this.configuration);
  final Enrollment enrollment;
  final Map<String, dynamic> configuration;
}

Future<OfflineBootstrap> decodeOfflineBootstrap(List<int> bytes) =>
    Isolate.run(() async {
      try {
        if (bytes.isEmpty || bytes.length > maxBootstrapBytes) {
          throw const ConfigException(ConfigFailure.malformed);
        }
        final bundle = jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
        if (bundle['format'] != 'vpnn-bootstrap-v1') {
          throw const ConfigException(ConfigFailure.malformed);
        }
        final envelope = bundle['envelope'] as Map<String, dynamic>;
        final encoded = envelope['payload'] as String;
        final signature = envelope['signature'] as String;
        if (encoded.length > 2000000 || signature.length > 100) {
          throw const ConfigException(ConfigFailure.malformed);
        }
        final payload = decode64(encoded);
        final data = jsonDecode(utf8.decode(payload)) as Map<String, dynamic>;
        if (data['schema'] != 1 || data['kind'] != 'bootstrap') {
          throw const ConfigException(ConfigFailure.malformed);
        }
        final enrollment = Enrollment.fromJson(
          data['enrollment'] as Map<String, dynamic>,
        );
        final signed = decode64(signature);
        if (signed.length != 64 ||
            !await Ed25519().verify(
              payload,
              signature: Signature(
                signed,
                publicKey: SimplePublicKey(
                  enrollment.publicKey,
                  type: KeyPairType.ed25519,
                ),
              ),
            )) {
          throw const ConfigException(ConfigFailure.signature);
        }
        return OfflineBootstrap(
          enrollment,
          data['configuration'] as Map<String, dynamic>,
        );
      } on ConfigException {
        rethrow;
      } catch (_) {
        throw const ConfigException(ConfigFailure.malformed);
      }
    });
