import 'dart:async';

import 'package:fl_clash/common/service_probe.dart';
import 'package:fl_clash/providers/providers.dart';
import 'package:fl_clash/providers/routed_probe.dart';
import 'package:fl_clash/providers/service_status.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

const managedHealthTargets = [ServiceTarget.google, ServiceTarget.github];

bool? managedInternetHealth(
  RouteState route,
  RoutedProbeState<ServiceTarget, ServiceCheck> checks,
) {
  var failed = 0;
  for (final target in managedHealthTargets) {
    final entry = checks.entryOf(target);
    final stamp = entry.stamp;
    if (stamp == null || !route.isFresh(stamp)) continue;
    if (entry.phase == ProbePhase.fresh && entry.value != null) return true;
    if (entry.phase == ProbePhase.failed) failed++;
  }
  return failed == managedHealthTargets.length ? false : null;
}

final vpnnInternetHealthProvider = Provider<bool?>((ref) {
  if (!ref.watch(isStartProvider) ||
      ref.watch(safeModeProvider) ||
      ref.watch(suspendProvider) ||
      !ref.watch(appVisibleProvider)) {
    return null;
  }
  return managedInternetHealth(
    ref.watch(routeTrackerProvider),
    ref.watch(serviceStatusProvider),
  );
});

final vpnnHealthMonitorProvider = Provider<ManagedHealthMonitor>((ref) {
  final monitor = ManagedHealthMonitor(ref);
  ref.listen(isStartProvider, (_, _) => monitor.sync());
  ref.listen(appVisibleProvider, (_, _) => monitor.sync());
  ref.listen(suspendProvider, (_, _) => monitor.sync());
  ref.onDispose(monitor.dispose);
  return monitor;
});

class ManagedHealthMonitor {
  ManagedHealthMonitor(this.ref);
  final Ref ref;
  bool _active = false;
  late final ServiceStatus _checks = ref.read(serviceStatusProvider.notifier);

  void sync() {
    final enabled =
        ref.read(isStartProvider) &&
        ref.read(appVisibleProvider) &&
        !ref.read(suspendProvider) &&
        !ref.read(safeModeProvider);
    if (enabled == _active) return;
    _active = enabled;
    for (final target in managedHealthTargets) {
      enabled ? _checks.watch(target) : _checks.unwatch(target);
    }
  }

  Future<bool?> check() async {
    sync();
    if (!_active) return null;
    _checks.refresh(managedHealthTargets);
    await Future<void>.delayed(Duration.zero);
    final watch = Stopwatch()..start();
    while (ref.mounted &&
        _active &&
        watch.elapsed < const Duration(seconds: 25)) {
      final result = ref.read(vpnnInternetHealthProvider);
      if (result != null) return result;
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    return null;
  }

  void dispose() {
    if (!_active) return;
    _active = false;
    for (final target in managedHealthTargets) {
      _checks.unwatch(target);
    }
  }
}
