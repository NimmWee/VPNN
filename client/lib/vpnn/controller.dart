import 'dart:async';

import 'package:flutter/foundation.dart';

import 'contract.dart';
import 'repository.dart';
import 'diagnostics.dart';
import 'refresh_policy.dart';
import 'connection_policy.dart';

abstract interface class ManagedConnection {
  bool get running;
  bool get suspended;
  bool? get internet;
  Future<bool?> checkInternet();
  String? activeMode(Enrollment enrollment);
  Future<void> validate(ManagedConfiguration config);
  Future<void> install(Enrollment enrollment, ManagedConfiguration config);
  Future<void> select(Enrollment enrollment, String mode);
  Future<bool> setRunning(bool value);
  Future<void> remove(Enrollment enrollment);
  Future<Map<String, dynamic>> transportStatus();
}

abstract interface class ManagedProfileUpdates {
  Future<bool> needsReload(
    Enrollment enrollment,
    ManagedConfiguration config,
    String mode,
  );
}

class VpnnController extends ChangeNotifier {
  VpnnController({
    required this.repository,
    required this.connection,
    this.poll = true,
    this.defaultAutomatic = false,
    this.connectionTimeout = const Duration(seconds: 180),
    this.transportTimeout = const Duration(seconds: 95),
  });
  final ConfigurationRepository repository;
  final ManagedConnection connection;
  final bool poll;
  final bool defaultAutomatic;
  final Duration connectionTimeout;
  final _policy = ConnectionPolicy();
  Future<void> _operation = Future<void>.value();
  int _pendingOperations = 0;
  bool _wantConnection = false;
  bool automaticSelection = false;
  bool networkAvailable = true;
  bool routesExhausted = false;
  static const _selectionKey = 'vpnn.selection.v2';

  String _kind(String id) =>
      configuration?.profiles
          .where((profile) => profile.id == id)
          .firstOrNull
          ?.kind ??
      id;
  final Duration transportTimeout;
  final _refreshPolicy = RefreshPolicy();
  bool automaticFallback = false;
  bool usedFallback = false;
  bool checkingInternet = false;
  DateTime? _lastHealthCheck;
  int _healthFailures = 0;
  static const _automaticKey = 'vpnn.automatic-fallback.v1';
  bool busy = false;
  bool initialized = false;
  bool usingCache = false;
  String selectedMode = 'direct';
  ConfigFailure? failure;
  DateTime? lastUpdate;
  Map<String, dynamic> transport = const {};
  Timer? _updates;
  Timer? _status;
  bool _disposed = false;
  bool _pollingStatus = false;
  int _intent = 0;
  final _probeCancellations = <void Function()>{};

  void _advanceIntent() {
    _intent += 1;
    for (final cancel in _probeCancellations.toList()) {
      cancel();
    }
  }

  Future<T> _boundedProbe<T>(
    Future<T> operation,
    Duration timeout,
    T cancelled,
  ) async {
    final result = Completer<T>();
    void cancel() {
      if (!result.isCompleted) result.complete(cancelled);
    }

    _probeCancellations.add(cancel);
    final timer = Timer(timeout, cancel);
    unawaited(
      operation.then<void>((value) {
        if (!result.isCompleted) result.complete(value);
      }, onError: (Object _, StackTrace _) => cancel()),
    );
    try {
      return await result.future;
    } finally {
      timer.cancel();
      _probeCancellations.remove(cancel);
    }
  }

  ConnectionStage stage = ConnectionStage.idle;
  final _clock = Stopwatch()..start();
  int _stageStartedMs = 0;
  final _events = <Map<String, Object?>>[];
  bool? _lastProbe;

  void _setStage(ConnectionStage value) {
    if (stage == value || _disposed) return;
    final now = _clock.elapsedMilliseconds;
    _events.add({'stage': stage.name, 'durationMs': now - _stageStartedMs});
    if (_events.length > 32) _events.removeAt(0);
    stage = value;
    _stageStartedMs = now;
    _notify();
  }

  Map<String, Object?> diagnosticReport({required String version}) => {
    'schema': 1,
    'version': version,
    'platform': defaultTargetPlatform.name,
    'mode': const ['direct', 'vk', 'dns'].contains(_kind(selectedMode))
        ? _kind(selectedMode)
        : 'unknown',
    'stage': stage.name,
    'stageElapsedMs': _clock.elapsedMilliseconds - _stageStartedMs,
    'failure': failure?.name,
    'running': connection.running,
    'suspended': connection.suspended,
    'captureReady': transport['captureReady'] is bool
        ? transport['captureReady']
        : null,
    'coreProbeReachable': _lastProbe,
    'systemEgressVerified': false,
    'automaticFallback': automaticFallback,
    'automaticSelection': automaticSelection,
    'networkAvailable': networkAvailable,
    'routesExhausted': routesExhausted,
    'usedFallback': usedFallback,
    'usingCache': usingCache,
    'configurationVersion': configuration?.version,
    'configurationRoute': repository.lastRefreshMode,
    'counters': safeDiagnosticCounters(transport['counters']),
    'events': _events.map((event) => Map<String, Object?>.of(event)).toList(),
  };

  ManagedConfiguration? get configuration => repository.configuration;
  Enrollment? get enrollment => repository.enrollment;
  bool _current(int intent) => !_disposed && intent == _intent;
  void _notify() {
    if (!_disposed) notifyListeners();
  }

  Future<bool> _run(Future<void> Function(int) action, {bool replace = false}) {
    if (_disposed || (busy && !replace)) return Future.value(false);
    if (replace) {
      _advanceIntent();
      repository.cancelPending();
    }
    final intent = _intent;
    final previous = _operation;
    _pendingOperations++;
    busy = true;
    _notify();
    final result = () async {
      await previous;
      try {
        if (!_current(intent)) return false;
        failure = null;
        await action(intent);
        return _current(intent);
      } on ConfigException catch (error) {
        if (_current(intent)) await _failure(error.failure);
        return false;
      } catch (_) {
        if (_current(intent)) await _failure(ConfigFailure.network);
        return false;
      } finally {
        _pendingOperations--;
        busy = _pendingOperations > 0;
        if (_current(intent) && stage == ConnectionStage.settings) {
          _setStage(
            connection.running ? ConnectionStage.ready : ConnectionStage.idle,
          );
        }
        _notify();
      }
    }();
    _operation = result.then<void>(
      (_) {},
      onError: (Object _, StackTrace _) {},
    );
    return result;
  }

  Future<void> _failure(ConfigFailure value) async {
    failure = value;
    _setStage(ConnectionStage.failed);
    if (value == ConfigFailure.revoked) {
      repository.configuration = null;
      usingCache = false;
      _wantConnection = false;
    }
    if (value == ConfigFailure.revoked && enrollment != null) {
      try {
        try {
          await connection.setRunning(false);
        } catch (_) {
          transport = const {'state': 'error'};
        }
      } finally {
        try {
          await connection.remove(enrollment!);
        } catch (_) {}
      }
    }
  }

  Future<void> initialize() async {
    await _run((intent) async {
      _setStage(ConnectionStage.settings);
      final storedFallback = await repository.vault.read(_automaticKey);
      final selection = await repository.vault.read(_selectionKey);
      automaticSelection =
          selection == 'auto' ||
          (selection == null &&
              (storedFallback == 'true' ||
                  (storedFallback == null && defaultAutomatic)));
      automaticFallback = automaticSelection || storedFallback == 'true';
      try {
        await repository.load();
      } on ConfigException catch (error) {
        if (error.failure == ConfigFailure.revoked) rethrow;
        failure = error.failure;
      }
      if (!_current(intent)) return;
      final config = configuration;
      if (config != null && enrollment != null) {
        await connection.validate(config);
        if (!_current(intent)) return;
        await connection.install(enrollment!, config);
        final restoredMode =
            (selection != null &&
                    selection != 'auto' &&
                    config.profiles.any((p) => p.id == selection && p.available)
                ? selection
                : connection.activeMode(enrollment!)) ??
            config.profiles
                .where((profile) => profile.available)
                .firstOrNull
                ?.id ??
            'direct';
        selectedMode =
            config.profiles.any((p) => p.id == restoredMode && p.available)
            ? restoredMode
            : config.profiles.where((p) => p.available).firstOrNull?.id ??
                  'direct';
        _wantConnection = connection.running;
        usingCache = true;
      }
      if (poll && enrollment != null && config == null) {
        await _refresh(intent, allowCache: true);
      }
    });
    initialized = true;
    if (poll && !_disposed) {
      _updates = Timer.periodic(const Duration(minutes: 2), (_) {
        if (!busy && enrollment != null && _refreshPolicy.due(DateTime.now())) {
          unawaited(refresh());
        }
      });
      _status = Timer.periodic(
        const Duration(seconds: 2),
        (_) => unawaited(refreshTransportStatus()),
      );
    }
    _notify();
  }

  Future<bool> enroll(String invitation) => _run((intent) async {
    _setStage(ConnectionStage.settings);
    final Enrollment next;
    try {
      next = Enrollment.parse(invitation);
    } on FormatException {
      throw const ConfigException(ConfigFailure.malformed);
    }
    final previous = enrollment;
    final config = await repository.enroll(next, validate: connection.validate);
    await _installEnrollment(previous, next, config, intent);
  });

  Future<bool> importBootstrap(List<int> bytes) => _run((intent) async {
    _setStage(ConnectionStage.settings);
    final previous = enrollment;
    final config = await repository.importBootstrap(
      bytes,
      validate: connection.validate,
    );
    await _installEnrollment(previous, enrollment!, config, intent);
  });

  Future<void> _installEnrollment(
    Enrollment? previous,
    Enrollment next,
    ManagedConfiguration config,
    int intent,
  ) async {
    if (!_current(intent)) return;
    if (connection.running) await connection.setRunning(false);
    if (!_current(intent)) return;
    if (previous != null && previous.deviceId != next.deviceId) {
      await connection.remove(previous);
    }
    await connection.install(next, config);
    if (!_current(intent)) return;
    _policy.networkChanged();
    _wantConnection = false;
    selectedMode =
        config.profiles.where((p) => p.available).firstOrNull?.id ?? 'direct';
    await connection.select(next, selectedMode);
    usingCache = false;
    lastUpdate = DateTime.now();
  }

  Future<void> _refresh(int intent, {required bool allowCache}) async {
    _setStage(ConnectionStage.settings);
    final previous = configuration;
    final device = enrollment;
    if (device == null) return;
    ManagedConfiguration next;
    try {
      next = await repository.refresh(validate: connection.validate);
      _refreshPolicy.succeeded(
        DateTime.now(),
        next.expiresAt,
        refreshAfter: next.refreshAfter,
      );
    } on ConfigException catch (error) {
      _refreshPolicy.failed(DateTime.now());
      if (allowCache &&
          error.failure != ConfigFailure.revoked &&
          previous != null &&
          previous.expiresAt.isAfter(DateTime.now())) {
        usingCache = true;
        failure = error.failure;
        return;
      }
      rethrow;
    }
    if (!_current(intent)) return;
    final active = connection.activeMode(device);
    final oldContent = previous?.profiles
        .where((profile) => profile.id == active)
        .firstOrNull
        ?.config;
    final newProfile = next.profiles
        .where((profile) => profile.id == active && profile.available)
        .firstOrNull;
    final updates = connection;
    final changed =
        active != null &&
        (oldContent != newProfile?.config ||
            (updates is ManagedProfileUpdates &&
                await (updates as ManagedProfileUpdates).needsReload(
                  device,
                  next,
                  active,
                )));
    if (!_current(intent)) return;
    final wasRunning = connection.running;
    if (changed && wasRunning) await connection.setRunning(false);
    if (!_current(intent)) return;
    await connection.install(device, next);
    if (!_current(intent)) return;
    if (!next.profiles.any(
      (profile) => profile.id == selectedMode && profile.available,
    )) {
      selectedMode =
          next.profiles.where((p) => p.available).firstOrNull?.id ?? 'direct';
    }
    if (changed && newProfile != null) {
      await connection.select(device, active);
      if (!_current(intent)) return;
      if (wasRunning && !await connection.setRunning(true)) {
        throw const ConfigException(ConfigFailure.network);
      }
    } else if (changed && wasRunning && automaticSelection) {
      await _connect(intent, selectedMode);
    }
    usingCache = false;
    lastUpdate = DateTime.now();
  }

  Future<bool> refresh() =>
      _run((intent) => _refresh(intent, allowCache: false));

  Future<bool> connect() {
    if (!initialized && busy) {
      final intent = _intent;
      return _operation.then((_) => _current(intent) ? connect() : false);
    }
    _wantConnection = true;
    return _run((intent) => _connect(intent, selectedMode), replace: true);
  }

  Future<bool> selectManualMode(String mode) => _run((intent) async {
    if (!(configuration?.profiles.any((p) => p.id == mode && p.available) ??
        false)) {
      throw const ConfigException(ConfigFailure.malformed);
    }
    automaticSelection = false;
    automaticFallback = false;
    await repository.vault.write(_selectionKey, mode);
    await repository.vault.write(_automaticKey, 'false');
    if (!_current(intent)) return;
    await _selectMode(intent, mode);
  }, replace: true);

  Future<bool> selectAutomatically() => _run((intent) async {
    automaticSelection = true;
    automaticFallback = true;
    await repository.vault.write(_selectionKey, 'auto');
    await repository.vault.write(_automaticKey, 'true');
    if (_current(intent) && (_wantConnection || connection.running)) {
      await _connect(intent, selectedMode);
    }
  }, replace: true);

  Future<void> networkChanged({required bool available}) async {
    if (_disposed) return;
    networkAvailable = available;
    if (!initialized) {
      _policy.networkChanged();
      _notify();
      return;
    }
    _advanceIntent();
    repository.cancelPending();
    _policy.networkChanged();
    _healthFailures = 0;
    _lastProbe = null;
    routesExhausted = false;
    if (!available) {
      final intent = _intent;
      await connection.setRunning(false);
      if (!_current(intent)) return;
      failure = ConfigFailure.network;
      _setStage(ConnectionStage.failed);
    } else if (_wantConnection && automaticSelection) {
      await _run((intent) => _connect(intent, selectedMode), replace: true);
    }
    _notify();
  }

  Future<bool> setAutomaticFallback(bool value) => _run((_) async {
    await repository.vault.write(_automaticKey, value.toString());
    automaticFallback = value;
  });

  Future<void> _connect(
    int intent,
    String mode, {
    bool skipCurrent = false,
  }) async {
    if (configuration == null ||
        !configuration!.expiresAt.isAfter(DateTime.now())) {
      await _refresh(intent, allowCache: true);
    }
    if (!_current(intent)) return;
    final config = configuration;
    final device = enrollment;
    if (config == null ||
        device == null ||
        !config.expiresAt.isAfter(DateTime.now())) {
      throw const ConfigException(ConfigFailure.expired);
    }
    if (!networkAvailable) throw const ConfigException(ConfigFailure.network);
    if (skipCurrent) {
      _policy.failed(mode, DateTime.now());
    }
    if (!skipCurrent && !automaticSelection) _policy.retry(mode);
    routesExhausted = false;
    usedFallback = false;
    final candidates = _policy
        .candidates(
          config.profiles,
          now: DateTime.now(),
          preferred: automaticSelection ? null : mode,
          attempted: {if (skipCurrent) mode},
        )
        .where((profile) => automaticFallback || profile.id == mode)
        .map((profile) => profile.id)
        .toList();
    final watch = Stopwatch()..start();
    Duration remaining() {
      final value = connectionTimeout - watch.elapsed;
      if (value <= Duration.zero) throw TimeoutException('Connection deadline');
      return value;
    }

    for (final candidate in candidates) {
      if (!_current(intent)) return;
      try {
        await _startMode(intent, device, candidate, remaining: remaining);
        if (!_current(intent)) return;
        final state = await _waitForTransport(
          intent,
          candidate,
          limit: remaining(),
        );
        if (!_current(intent)) return;
        if (state == 'stopped') throw const _OwnerStopped();
        if (state == 'capture-error') {
          throw const ConfigException(ConfigFailure.capture);
        }
        if (state == 'suspended') return;
        if (state == 'captcha' && !automaticFallback) return;
        if (state == 'captcha' || state == 'error') {
          throw const ConfigException(ConfigFailure.network);
        }
        final reachable = await _checkInternet(intent, timeout: remaining());
        if (connection.suspended) return;
        if (!_current(intent)) return;
        if (reachable != true) {
          throw const ConfigException(ConfigFailure.network);
        }
        if (!_current(intent)) return;
        usedFallback = skipCurrent || candidate != candidates.first;
        _policy.succeeded(candidate);
        _setStage(ConnectionStage.ready);
        return;
      } on TimeoutException {
        if (_current(intent)) {
          await connection
              .setRunning(false)
              .timeout(const Duration(seconds: 10));
          routesExhausted = true;
        }
        throw const ConfigException(ConfigFailure.network);
      } on _OwnerStopped {
        if (_current(intent)) _wantConnection = false;
        throw const ConfigException(ConfigFailure.network);
      } on ConfigException catch (error) {
        if (error.failure != ConfigFailure.network) {
          if (_current(intent) && connection.running) {
            await connection.setRunning(false);
          }
          rethrow;
        }
      } catch (_) {
        if (!_current(intent)) return;
      }
      if (!_current(intent)) return;
      _policy.failed(candidate, DateTime.now());
      await connection.setRunning(false).timeout(const Duration(seconds: 10));
      if (watch.elapsed >= connectionTimeout) break;
    }
    routesExhausted = true;
    if (_current(intent) && connection.running) {
      await connection.setRunning(false);
    }
    throw const ConfigException(ConfigFailure.network);
  }

  Future<void> _startMode(
    int intent,
    Enrollment device,
    String mode, {
    required Duration Function() remaining,
  }) async {
    if (connection.running) await connection.setRunning(false);
    if (!_current(intent)) return;
    selectedMode = mode;
    _lastProbe = null;
    transport = const {};
    _lastHealthCheck = null;
    _healthFailures = 0;
    _notify();
    _setStage(ConnectionStage.selecting);
    final selectBudget = remaining();
    await connection
        .select(device, mode)
        .timeout(
          selectBudget < const Duration(seconds: 15)
              ? selectBudget
              : const Duration(seconds: 15),
        );
    if (!_current(intent)) return;
    _setStage(ConnectionStage.systemTunnel);
    final startBudget = remaining();
    final started = await connection
        .setRunning(true)
        .timeout(
          startBudget < const Duration(seconds: 20)
              ? startBudget
              : const Duration(seconds: 20),
        );
    if (!_current(intent)) {
      if ((!_wantConnection || !networkAvailable) && connection.running) {
        await connection.setRunning(false);
      }
      return;
    }
    if (!started) {
      throw const _OwnerStopped();
    }
    if (_current(intent)) _setStage(ConnectionStage.transport);
  }

  Future<String> _waitForTransport(
    int intent,
    String mode, {
    required Duration limit,
  }) async {
    if (connection.suspended) return 'suspended';
    final watch = Stopwatch()..start();
    var capturePending = false;
    final budget = limit < transportTimeout ? limit : transportTimeout;
    while (_current(intent) && watch.elapsed < budget) {
      if (!connection.running) return 'stopped';
      if (connection.suspended) return 'suspended';
      try {
        final statusBudget = budget - watch.elapsed;
        final value = await _boundedProbe(
          connection.transportStatus(),
          statusBudget < const Duration(seconds: 4)
              ? statusBudget
              : const Duration(seconds: 4),
          const <String, dynamic>{},
        );
        if (!_current(intent)) return 'superseded';
        if (_kind(mode) == 'direct' ||
            value['mode'] == null ||
            value['mode'] == _kind(mode)) {
          transport = value;
          if (value['state'] == 'captcha') _setStage(ConnectionStage.captcha);
          _notify();
          final state = value['state'];
          final captured = value['captureReady'];
          capturePending = captured != true;
          if (state == 'error') return 'error';
          final transportReady = state == 'ready' || state == 'connected';
          if (captured == false && (transportReady || state == 'captcha')) {
            return 'capture-error';
          }
          if (captured == true) {
            if (state == 'captcha') return 'captcha';
            if (_kind(mode) == 'direct' || transportReady) return 'ready';
          }
        }
      } catch (_) {}
      final pause = budget - watch.elapsed;
      if (pause > Duration.zero) {
        await Future<void>.delayed(
          pause < const Duration(milliseconds: 250)
              ? pause
              : const Duration(milliseconds: 250),
        );
      }
    }
    if (!_current(intent)) return 'superseded';
    return capturePending ? 'capture-error' : 'error';
  }

  Future<bool?> checkInternet() => _checkInternet(_intent);

  Future<bool?> _checkInternet(
    int intent, {
    Duration timeout = const Duration(seconds: 25),
  }) async {
    if (_disposed || connection.suspended) return null;
    if (checkingInternet || !connection.running) return null;
    final mode = selectedMode;
    checkingInternet = true;
    final previousStage = stage;
    _setStage(ConnectionStage.checking);
    _lastHealthCheck = DateTime.now();
    _notify();
    try {
      final result = await _boundedProbe<bool?>(
        connection.checkInternet(),
        timeout < const Duration(seconds: 25)
            ? timeout
            : const Duration(seconds: 25),
        null,
      );
      if (!_current(intent) ||
          mode != selectedMode ||
          !connection.running ||
          result != connection.internet) {
        return null;
      }
      _lastProbe = result;
      return result;
    } catch (_) {
      return null;
    } finally {
      checkingInternet = false;
      if (_current(intent) && stage == ConnectionStage.checking) {
        _setStage(previousStage);
      }
      _notify();
    }
  }

  Future<bool> selectMode(String mode) =>
      _run((intent) => _selectMode(intent, mode), replace: true);

  Future<void> _selectMode(int intent, String mode) async {
    final config = configuration;
    final device = enrollment;
    if (config == null ||
        device == null ||
        !config.profiles.any(
          (profile) => profile.id == mode && profile.available,
        )) {
      throw const ConfigException(ConfigFailure.malformed);
    }
    if (_wantConnection || connection.running) {
      await _connect(intent, mode);
    } else {
      selectedMode = mode;
      usedFallback = false;
      await connection.select(device, mode);
    }
  }

  Future<void> disconnect() async {
    _wantConnection = false;
    _advanceIntent();
    final intent = _intent;
    repository.cancelPending();
    try {
      await connection.setRunning(false);
      if (!_current(intent)) return;
      transport = const {};
      _lastProbe = null;
      routesExhausted = false;
      usedFallback = false;
      failure = null;
      _setStage(ConnectionStage.idle);
    } catch (_) {
      if (!_current(intent)) return;
      failure = ConfigFailure.network;
      _setStage(ConnectionStage.failed);
    }
    _notify();
  }

  Future<bool> forget() => _run((intent) async {
    _wantConnection = false;
    final device = enrollment;
    if (device == null) return;
    await connection.setRunning(false);
    if (!_current(intent)) return;
    await connection.remove(device);
    await repository.forget();
    transport = const {};
    usingCache = false;
    _lastProbe = null;
    _setStage(ConnectionStage.idle);
  });

  @visibleForTesting
  Future<void> refreshTransportStatus() async {
    if (_disposed ||
        busy ||
        _pollingStatus ||
        !connection.running ||
        connection.suspended) {
      return;
    }
    final intent = _intent;
    final mode = selectedMode;
    _pollingStatus = true;
    try {
      final value = await _boundedProbe(
        connection.transportStatus(),
        const Duration(seconds: 4),
        const <String, dynamic>{},
      );
      if (_current(intent) &&
          !busy &&
          selectedMode == mode &&
          connection.running &&
          (_kind(mode) == 'direct' ||
              value['mode'] == null ||
              value['mode'] == _kind(mode))) {
        transport = value;
        if (value['captureReady'] == true &&
            (_kind(mode) == 'direct' ||
                value['state'] == 'ready' ||
                value['state'] == 'connected')) {
          _setStage(ConnectionStage.ready);
        } else if (value['state'] == 'captcha') {
          _setStage(ConnectionStage.captcha);
        }
        if (value['captureReady'] == false) {
          await connection.setRunning(false);
          if (!_current(intent)) return;
          failure = ConfigFailure.capture;
          _setStage(ConnectionStage.failed);
        } else if (value['state'] == 'error' ||
            (value['state'] == 'captcha' && automaticFallback)) {
          if (automaticFallback) {
            await _run((next) => _connect(next, mode, skipCurrent: true));
          } else {
            await connection.setRunning(false);
            if (!_current(intent)) return;
            failure = ConfigFailure.network;
            _setStage(ConnectionStage.failed);
          }
        } else if (value['captureReady'] == true &&
            (_kind(mode) == 'direct' ||
                value['state'] == 'ready' ||
                value['state'] == 'connected') &&
            !checkingInternet &&
            (_lastHealthCheck == null ||
                DateTime.now().difference(_lastHealthCheck!) >=
                    const Duration(seconds: 30))) {
          final reachable = await _checkInternet(intent);
          if (!_current(intent) || selectedMode != mode || busy) return;
          if (reachable == true) _healthFailures = 0;
          if (reachable == false) _healthFailures++;
          if (_healthFailures >= 2 && automaticFallback) {
            await _run((next) => _connect(next, mode, skipCurrent: true));
          }
        }
        _notify();
      }
    } catch (_) {
      // The connection owner reports Core failures; polling never starts another runtime.
    } finally {
      _pollingStatus = false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _advanceIntent();
    repository.cancelPending();
    _updates?.cancel();
    _status?.cancel();
    super.dispose();
  }
}

class _OwnerStopped implements Exception {
  const _OwnerStopped();
}
