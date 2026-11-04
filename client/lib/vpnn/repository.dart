import 'dart:convert';
import 'dart:async';
import 'dart:isolate';
import 'dart:math';

import 'package:cryptography/cryptography.dart';

import 'contract.dart';
import 'bootstrap.dart';
import 'config_transport.dart';

abstract interface class SecretVault {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

abstract interface class ConfigurationCache {
  Future<String?> read();
  Future<void> write(String value);
  Future<void> clear();
  Future<String?> readPending();
  Future<void> writePending(String value);
  Future<void> clearPending();
}

class ConfigurationRepository {
  ConfigurationRepository({
    required this.vault,
    required this.cache,
    ConfigTransport Function()? transport,
    DateTime Function()? now,
    Duration refreshTimeout = const Duration(seconds: 30),
  }) : transport = transport ?? ConfigTransport.direct,
       now = now ?? DateTime.now,
       refreshTimeout = Duration(
         microseconds: refreshTimeout.inMicroseconds.clamp(1, 30000000),
       );

  final SecretVault vault;
  final ConfigurationCache cache;
  final ConfigTransport Function() transport;
  final DateTime Function() now;
  final Duration refreshTimeout;
  ConfigTransport? _pending;
  int _generation = 0;
  String? lastRefreshMode;

  void cancelPending() {
    _generation++;
    _pending?.close();
    _pending = null;
  }

  Enrollment? enrollment;
  ManagedConfiguration? configuration;
  int _minimumVersion = 0;
  static const _enrollmentKey = 'vpnn.enrollment.v1';
  static const _versionKey = 'vpnn.version.v1';
  static const _cacheKey = 'vpnn.cache-key.v1';
  static const _revokedKey = 'vpnn.revoked.v1';
  static const _clockKey = 'vpnn.clock.v1';

  Future<DateTime> _trustedNow() async {
    final current = now().toUtc();
    final stored = int.tryParse(await vault.read(_clockKey) ?? '');
    if (stored == null) return current;
    final floor = DateTime.fromMillisecondsSinceEpoch(stored, isUtc: true);
    if (current.add(const Duration(minutes: 5)).isBefore(floor)) {
      throw const ConfigException(ConfigFailure.expired);
    }
    return current.isBefore(floor) ? floor : current;
  }

  Future<void> _rememberClock() async => vault.write(
    _clockKey,
    (await _trustedNow()).millisecondsSinceEpoch.toString(),
  );

  Future<void> load() async {
    final data = await vault.read(_enrollmentKey);
    if (data == null) return;
    try {
      enrollment = Enrollment.fromJson(
        jsonDecode(data) as Map<String, dynamic>,
      );
      _minimumVersion = int.tryParse(await vault.read(_versionKey) ?? '') ?? 0;
      if (await vault.read(_revokedKey) == 'true') {
        throw const ConfigException(ConfigFailure.revoked);
      }
      final pending = await cache.readPending();
      final encrypted = pending ?? await cache.read();
      if (encrypted == null) return;
      final key = await _encryptionKey(create: false);
      final decoded = await _decryptCache(encrypted, await key.extractBytes());
      final config = await verifyConfiguration(
        decoded,
        enrollment!,
        minimumVersion: _minimumVersion,
        now: await _trustedNow(),
      );
      if (pending != null) {
        await vault.write(_versionKey, config.version.toString());
        await cache.write(pending);
      }
      await _updateEndpoints(config);
      await _rememberClock();
      if (pending != null) await cache.clearPending();
      _minimumVersion = config.version;
      configuration = config;
    } on ConfigException {
      rethrow;
    } catch (_) {
      throw const ConfigException(ConfigFailure.malformed);
    }
  }

  Future<ManagedConfiguration> enroll(
    Enrollment value, {
    Future<void> Function(ManagedConfiguration)? validate,
  }) async {
    final result = await _fetch(value, await _minimumFor(value));
    await validate?.call(result.configuration);
    await vault.write(_enrollmentKey, jsonEncode(value.toJson()));
    await vault.delete(_revokedKey);
    enrollment = value;
    _minimumVersion = 0;
    await _accept(result.envelope, result.configuration);
    return result.configuration;
  }

  Future<int> _minimumFor(Enrollment next) async {
    bool same(Enrollment value) =>
        value.deviceId == next.deviceId &&
        base64UrlEncode(value.publicKey) == base64UrlEncode(next.publicKey);
    var minimum = enrollment != null && same(enrollment!) ? _minimumVersion : 0;
    final encoded = await vault.read(_enrollmentKey);
    if (encoded != null) {
      final stored = Enrollment.fromJson(
        jsonDecode(encoded) as Map<String, dynamic>,
      );
      if (same(stored)) {
        if (await vault.read(_revokedKey) == 'true') {
          throw const ConfigException(ConfigFailure.revoked);
        }
        final floor = int.tryParse(await vault.read(_versionKey) ?? '') ?? 0;
        if (floor > minimum) minimum = floor;
      }
    }
    return minimum;
  }

  Future<ManagedConfiguration> importBootstrap(
    List<int> bytes, {
    Future<void> Function(ManagedConfiguration)? validate,
  }) async {
    final bundle = await decodeOfflineBootstrap(bytes);
    final config = await verifyConfiguration(
      bundle.configuration,
      bundle.enrollment,
      minimumVersion: await _minimumFor(bundle.enrollment),
      now: await _trustedNow(),
    );
    await validate?.call(config);
    await vault.write(_enrollmentKey, jsonEncode(bundle.enrollment.toJson()));
    await vault.delete(_revokedKey);
    enrollment = bundle.enrollment;
    _minimumVersion = 0;
    await _accept(bundle.configuration, config);
    return config;
  }

  Future<ManagedConfiguration> refresh({
    Future<void> Function(ManagedConfiguration)? validate,
  }) => _refresh(validate: validate).timeout(
    refreshTimeout,
    onTimeout: () {
      cancelPending();
      throw const ConfigException(ConfigFailure.network);
    },
  );

  Future<ManagedConfiguration> _refresh({
    Future<void> Function(ManagedConfiguration)? validate,
  }) async {
    final generation = _generation;
    final value = enrollment;
    if (value == null) throw const ConfigException(ConfigFailure.malformed);
    if (await vault.read(_revokedKey) == 'true') {
      throw const ConfigException(ConfigFailure.revoked);
    }
    try {
      final result = await _fetch(value, await _minimumFor(value));
      await validate?.call(result.configuration);
      if (generation != _generation) {
        throw const ConfigException(ConfigFailure.network);
      }
      await _accept(result.envelope, result.configuration);
      return result.configuration;
    } on ConfigException catch (error) {
      if (error.failure == ConfigFailure.revoked) {
        await vault.write(_revokedKey, 'true');
        await cache.clearPending();
        await cache.clear();
        configuration = null;
      }
      rethrow;
    }
  }

  Future<void> forget() async {
    cancelPending();
    await cache.clearPending();
    await cache.clear();
    for (final key in [
      _enrollmentKey,
      _versionKey,
      _cacheKey,
      _revokedKey,
      _clockKey,
    ]) {
      await vault.delete(key);
    }
    enrollment = null;
    configuration = null;
    _minimumVersion = 0;
  }

  Future<SecretKey> _encryptionKey({bool create = true}) async {
    final existing = await vault.read(_cacheKey);
    if (existing != null) {
      final bytes = decode64(existing);
      if (bytes.length != 32) {
        throw const ConfigException(ConfigFailure.malformed);
      }
      return SecretKey(bytes);
    }
    if (!create) throw const ConfigException(ConfigFailure.malformed);
    final key = await AesGcm.with256bits().newSecretKey();
    await vault.write(_cacheKey, base64UrlEncode(await key.extractBytes()));
    return key;
  }

  Future<void> _accept(
    Map<String, dynamic> envelope,
    ManagedConfiguration config,
  ) async {
    if (!config.expiresAt.isAfter(await _trustedNow())) {
      throw const ConfigException(ConfigFailure.expired);
    }
    final encrypted = await _encryptCache(
      envelope,
      await (await _encryptionKey()).extractBytes(),
    );
    await cache.writePending(encrypted);
    await vault.write(_versionKey, config.version.toString());
    await cache.write(encrypted);
    await _updateEndpoints(config);
    await _rememberClock();
    await cache.clearPending();
    _minimumVersion = config.version;
    configuration = config;
  }

  Future<void> _updateEndpoints(ManagedConfiguration config) async {
    final current = enrollment;
    final endpoints = config.controlEndpoints;
    if (current == null || endpoints == null) return;
    final next = Enrollment(
      endpoints: endpoints,
      token: current.token,
      publicKey: current.publicKey,
      deviceId: current.deviceId,
    );
    await vault.write(_enrollmentKey, jsonEncode(next.toJson()));
    enrollment = next;
  }

  Future<({Map<String, dynamic> envelope, ManagedConfiguration configuration})>
  _fetch(Enrollment value, int minimumVersion) async {
    final generation = _generation;
    final route = transport();
    _pending = route;
    var expired = false;
    final deadline = Timer(refreshTimeout, () {
      expired = true;
      route.close();
    });
    ConfigException failure = const ConfigException(ConfigFailure.network);
    try {
      for (final endpoint in value.endpoints.take(3)) {
        try {
          if (generation != _generation || expired) {
            throw const ConfigException(ConfigFailure.network);
          }
          final random = Random.secure();
          final nonce = base64UrlEncode(
            List.generate(32, (_) => random.nextInt(256)),
          ).replaceAll('=', '');
          final response = await route.get(
            endpoint.resolve('/api/device/config'),
            token: value.token,
            minimumVersion: minimumVersion,
            nonce: nonce,
          );
          if (generation != _generation || expired) {
            throw const ConfigException(ConfigFailure.network);
          }
          if (response.status == 401 || response.status == 403) {
            final revoked = await verifyRevocation(
              response.bytes,
              value,
              nonce: nonce,
              minimumVersion: minimumVersion,
            );
            if (generation != _generation || expired) {
              throw const ConfigException(ConfigFailure.network);
            }
            throw ConfigException(
              revoked ? ConfigFailure.revoked : ConfigFailure.network,
            );
          }
          if (response.status != 200) {
            throw const ConfigException(ConfigFailure.network);
          }
          final envelope = await _decodeEnvelope(response.bytes);
          final config = await verifyConfiguration(
            envelope,
            value,
            minimumVersion: minimumVersion,
            now: await _trustedNow(),
          );
          if (generation != _generation || expired) {
            throw const ConfigException(ConfigFailure.network);
          }
          lastRefreshMode = route.mode;
          return (envelope: envelope, configuration: config);
        } on ConfigException catch (error) {
          if (error.failure == ConfigFailure.revoked) rethrow;
          failure = error;
        } catch (_) {
          failure = const ConfigException(ConfigFailure.network);
        }
      }
      throw failure;
    } finally {
      deadline.cancel();
      route.close();
      if (identical(_pending, route)) _pending = null;
    }
  }
}

Future<Map<String, dynamic>> _decodeEnvelope(List<int> bytes) =>
    Isolate.run(() => jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>);

Future<Map<String, dynamic>> _decryptCache(String encoded, List<int> key) =>
    Isolate.run(() async {
      final plain = await AesGcm.with256bits().decrypt(
        SecretBox.fromConcatenation(
          decode64(encoded),
          nonceLength: 12,
          macLength: 16,
        ),
        secretKey: SecretKey(key),
      );
      return jsonDecode(utf8.decode(plain)) as Map<String, dynamic>;
    });

Future<String> _encryptCache(Map<String, dynamic> envelope, List<int> key) =>
    Isolate.run(() async {
      final box = await AesGcm.with256bits().encrypt(
        utf8.encode(jsonEncode(envelope)),
        secretKey: SecretKey(key),
      );
      return base64UrlEncode(box.concatenation());
    });
