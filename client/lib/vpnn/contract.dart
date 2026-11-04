import 'dart:convert';
import 'dart:isolate';

import 'package:cryptography/cryptography.dart';
import 'build_variant.dart';

enum ConfigFailure {
  malformed,
  signature,
  device,
  rollback,
  expired,
  network,
  capture,
  revoked,
}

class ConfigException implements Exception {
  const ConfigException(this.failure);
  final ConfigFailure failure;
  @override
  String toString() => 'VPNN configuration: ${failure.name}';
}

class Enrollment {
  const Enrollment({
    required this.endpoints,
    required this.token,
    required this.publicKey,
    required this.deviceId,
  });

  final List<Uri> endpoints;
  final String token;
  final List<int> publicKey;
  final String deviceId;

  factory Enrollment.parse(String text) {
    final uri = Uri.parse(text.trim());
    if (uri.scheme != 'vpnn' || uri.host != 'enroll' || uri.path.isNotEmpty) {
      throw const FormatException('Invalid VPNN invitation');
    }
    final params = uri.queryParameters;
    final urls = uri.queryParametersAll['url'] ?? const [];
    final endpoints = urls.map(Uri.parse).toList();
    final token = params['token'] ?? '';
    final device = params['device'] ?? '';
    List<int> key;
    try {
      key = decode64(params['key'] ?? '');
    } catch (_) {
      throw const FormatException('Invalid signing key');
    }
    if (endpoints.isEmpty ||
        endpoints.length > 3 ||
        endpoints.any((endpoint) => !safeControlEndpoint(endpoint)) ||
        token.length < 32 ||
        token.length > 128 ||
        key.length != 32 ||
        device.isEmpty ||
        device.length > 64 ||
        uri.fragment.isNotEmpty) {
      throw const FormatException('Incomplete or unsafe VPNN invitation');
    }
    return Enrollment(
      endpoints: endpoints,
      token: token,
      publicKey: key,
      deviceId: device,
    );
  }

  factory Enrollment.fromJson(Map<String, dynamic> data) {
    final query = <String, dynamic>{
      'url': (data['endpoints'] as List).cast<String>(),
      'token': data['token'],
      'key': data['key'],
      'device': data['device'],
    };
    return Enrollment.parse(
      Uri(scheme: 'vpnn', host: 'enroll', queryParameters: query).toString(),
    );
  }

  Map<String, dynamic> toJson() => {
    'endpoints': endpoints.map((endpoint) => endpoint.toString()).toList(),
    'token': token,
    'key': base64UrlEncode(publicKey),
    'device': deviceId,
  };

  @override
  String toString() =>
      'VPNN enrollment ($deviceId, ${endpoints.length} endpoints)';
}

bool safeControlEndpoint(Uri uri) {
  if (uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.query.isNotEmpty ||
      uri.fragment.isNotEmpty ||
      (uri.path.isNotEmpty && uri.path != '/')) {
    return false;
  }
  return uri.scheme == 'https' ||
      (uri.scheme == 'http' &&
          const [
            '127.0.0.1',
            'localhost',
            '::1',
            '10.0.2.2',
          ].contains(uri.host));
}

List<int> decode64(String text) => base64Url.decode(base64Url.normalize(text));

Future<bool> verifyRevocation(
  List<int> bytes,
  Enrollment enrollment, {
  required String nonce,
  required int minimumVersion,
}) => Isolate.run(() async {
  try {
    final envelope = jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
    final payload = decode64(envelope['payload'] as String);
    final signature = decode64(envelope['signature'] as String);
    if (payload.length > 4096 ||
        signature.length != 64 ||
        !await Ed25519().verify(
          payload,
          signature: Signature(
            signature,
            publicKey: SimplePublicKey(
              enrollment.publicKey,
              type: KeyPairType.ed25519,
            ),
          ),
        )) {
      return false;
    }
    final data = jsonDecode(utf8.decode(payload)) as Map<String, dynamic>;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final issued = data['issuedAt'] as int;
    final expires = data['expiresAt'] as int;
    return data['schema'] == 1 &&
        data['kind'] == 'revocation' &&
        data['deviceId'] == enrollment.deviceId &&
        data['nonce'] == nonce &&
        (data['version'] as int) >= minimumVersion &&
        issued <= now + 300 &&
        expires > now &&
        expires > issued &&
        expires - issued <= 300;
  } catch (_) {
    return false;
  }
});

class ManagedProfile {
  const ManagedProfile({
    required this.id,
    required this.name,
    required this.config,
    String? kind,
    this.priority,
    this.enabled = true,
    this.capabilities = const [],
    this.minimumClientVersion = '0.0.0',
  }) : _kind = kind;
  final String id;
  final String name;
  final String config;
  final String? _kind;
  String get kind => _kind ?? id;
  final int? priority;
  final bool enabled;
  final List<String> capabilities;
  final String minimumClientVersion;
  bool get available =>
      enabled &&
      const ['direct', 'vk', 'dns'].contains(kind) &&
      managedVersionSupported(minimumClientVersion);
  int get connectionPriority =>
      priority ??
      switch (kind) {
        'direct' => 100,
        'vk' => 200,
        _ => 300,
      };
}

class ManagedConfiguration {
  const ManagedConfiguration({
    required this.version,
    required this.expiresAt,
    required this.profiles,
    this.controlEndpoints,
    this.refreshAfter,
  });
  final int version;
  final DateTime expiresAt;
  final List<ManagedProfile> profiles;
  final List<Uri>? controlEndpoints;
  final DateTime? refreshAfter;
}

Future<ManagedConfiguration> verifyConfiguration(
  Map<String, dynamic> envelope,
  Enrollment enrollment, {
  DateTime? now,
  int minimumVersion = 0,
}) => Isolate.run(
  () => _verifyConfiguration(
    envelope,
    enrollment,
    now: now,
    minimumVersion: minimumVersion,
  ),
);

Future<ManagedConfiguration> _verifyConfiguration(
  Map<String, dynamic> envelope,
  Enrollment enrollment, {
  DateTime? now,
  int minimumVersion = 0,
}) async {
  try {
    final encoded = envelope['payload'] as String;
    final encodedSignature = envelope['signature'] as String;
    if (encoded.length > 1400000 || encodedSignature.length > 100) {
      throw const ConfigException(ConfigFailure.malformed);
    }
    final payload = decode64(encoded);
    final signature = decode64(encodedSignature);
    if (signature.length != 64 ||
        enrollment.publicKey.length != 32 ||
        !await Ed25519().verify(
          payload,
          signature: Signature(
            signature,
            publicKey: SimplePublicKey(
              enrollment.publicKey,
              type: KeyPairType.ed25519,
            ),
          ),
        )) {
      throw const ConfigException(ConfigFailure.signature);
    }
    final data = jsonDecode(utf8.decode(payload)) as Map<String, dynamic>;
    if (data['schema'] != 1) {
      throw const ConfigException(ConfigFailure.malformed);
    }
    if (data['deviceId'] != enrollment.deviceId) {
      throw const ConfigException(ConfigFailure.device);
    }
    final version = data['version'] as int;
    if (version < minimumVersion || version <= 0) {
      throw const ConfigException(ConfigFailure.rollback);
    }
    final issuedAt = DateTime.fromMillisecondsSinceEpoch(
      (data['issuedAt'] as int) * 1000,
      isUtc: true,
    );
    final expiresAt = DateTime.fromMillisecondsSinceEpoch(
      (data['expiresAt'] as int) * 1000,
      isUtc: true,
    );
    final clock = (now ?? DateTime.now()).toUtc();
    if (!expiresAt.isAfter(clock) ||
        issuedAt.isAfter(clock.add(const Duration(minutes: 5))) ||
        expiresAt.difference(issuedAt) > const Duration(days: 8)) {
      throw const ConfigException(ConfigFailure.expired);
    }
    List<Uri>? endpoints;
    if (data.containsKey('controlEndpoints')) {
      endpoints = (data['controlEndpoints'] as List)
          .map((value) => Uri.parse(value as String))
          .toList();
      if (endpoints.isEmpty ||
          endpoints.length > 3 ||
          endpoints.any((uri) => !safeControlEndpoint(uri))) {
        throw const ConfigException(ConfigFailure.malformed);
      }
    }
    DateTime? refreshAfter;
    if (data.containsKey('refreshAfter')) {
      refreshAfter = DateTime.fromMillisecondsSinceEpoch(
        (data['refreshAfter'] as int) * 1000,
        isUtc: true,
      );
      if (refreshAfter.isBefore(issuedAt) ||
          !refreshAfter.isBefore(expiresAt)) {
        throw const ConfigException(ConfigFailure.malformed);
      }
    }
    final entries = data['profiles'] as List;
    if (entries.isEmpty || entries.length > 32) {
      throw const ConfigException(ConfigFailure.malformed);
    }
    final ids = <String>{};
    final profiles = <ManagedProfile>[];
    for (final value in entries) {
      final entry = value as Map<String, dynamic>;
      final id = entry['id'] as String;
      final name = entry['name'] as String;
      final config = entry['config'] as String;
      if (!RegExp(r'^[a-zA-Z0-9_-]{1,64}$').hasMatch(id) ||
          !ids.add(id) ||
          name.length > 100 ||
          config.length > 512000 ||
          jsonDecode(config) is! Map<String, dynamic>) {
        throw const ConfigException(ConfigFailure.malformed);
      }
      final kind = entry['kind'] as String?;
      final priority = entry['priority'] as int?;
      final enabled = entry['enabled'] as bool? ?? true;
      final capabilities = (entry['capabilities'] as List? ?? const [])
          .cast<String>();
      final minimum = entry['minimumClientVersion'] as String? ?? '0.0.0';
      if ((kind != null && !RegExp(r'^[a-zA-Z0-9_-]{1,32}$').hasMatch(kind)) ||
          (priority != null && (priority < 0 || priority > 10000)) ||
          capabilities.length > 16 ||
          capabilities.any((value) => value.length > 32) ||
          !RegExp(r'^\d{1,4}\.\d{1,4}\.\d{1,4}$').hasMatch(minimum)) {
        throw const ConfigException(ConfigFailure.malformed);
      }
      profiles.add(
        ManagedProfile(
          id: id,
          name: name,
          config: config,
          kind: kind,
          priority: priority,
          enabled: enabled,
          capabilities: List.unmodifiable(capabilities),
          minimumClientVersion: minimum,
        ),
      );
    }
    return ManagedConfiguration(
      version: version,
      expiresAt: expiresAt,
      profiles: List.unmodifiable(profiles),
      controlEndpoints: endpoints == null ? null : List.unmodifiable(endpoints),
      refreshAfter: refreshAfter,
    );
  } on ConfigException {
    rethrow;
  } catch (_) {
    throw const ConfigException(ConfigFailure.malformed);
  }
}
