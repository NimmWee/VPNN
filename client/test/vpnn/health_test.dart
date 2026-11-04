import 'package:fl_clash/common/service_probe.dart';
import 'package:fl_clash/providers/routed_probe.dart';
import 'package:fl_clash/providers/route_state.dart';
import 'package:fl_clash/vpnn/health.dart';
import 'package:flutter_test/flutter_test.dart';

const route = RouteState(
  coreEpoch: 2,
  routeVersion: 3,
  hostEpoch: 4,
  proxied: true,
  synced: true,
  live: true,
);
const stamp = RouteStamp(
  coreEpoch: 2,
  routeVersion: 3,
  hostEpoch: 4,
  proxied: true,
);
const success = ProbeEntry<ServiceCheck>(
  phase: ProbePhase.fresh,
  value: ServiceCheck(ServiceProbeStatus.available),
  stamp: stamp,
);
const failure = ProbeEntry<ServiceCheck>(
  phase: ProbePhase.failed,
  stamp: stamp,
);

void main() {
  test('one current HTTPS success proves reachability', () {
    expect(
      managedInternetHealth(
        route,
        const RoutedProbeState({ServiceTarget.google: success}),
      ),
      isTrue,
    );
  });
  test('all current checks must fail before declaring a failure', () {
    expect(
      managedInternetHealth(
        route,
        const RoutedProbeState({ServiceTarget.google: failure}),
      ),
      isNull,
    );
    expect(
      managedInternetHealth(
        route,
        const RoutedProbeState({
          ServiceTarget.google: failure,
          ServiceTarget.github: failure,
        }),
      ),
      isFalse,
    );
  });
  test('answers from an old route, Core or host never prove connectivity', () {
    for (final moved in [
      route.copyWith(coreEpoch: 5),
      route.copyWith(routeVersion: 5),
      route.copyWith(hostEpoch: 5),
      route.copyWith(proxied: false),
      route.copyWith(synced: false),
    ]) {
      expect(
        managedInternetHealth(
          moved,
          const RoutedProbeState({ServiceTarget.google: success}),
        ),
        isNull,
      );
      expect(
        managedInternetHealth(
          moved,
          const RoutedProbeState({
            ServiceTarget.google: failure,
            ServiceTarget.github: failure,
          }),
        ),
        isNull,
      );
    }
  });
  test('retained values during a fresh probe are unknown', () {
    expect(
      managedInternetHealth(
        route,
        const RoutedProbeState({
          ServiceTarget.google: ProbeEntry(
            phase: ProbePhase.probing,
            value: ServiceCheck(ServiceProbeStatus.available),
            stamp: stamp,
          ),
        }),
      ),
      isNull,
    );
  });
}
