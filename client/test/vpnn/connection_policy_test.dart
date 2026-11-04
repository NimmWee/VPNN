import 'package:fl_clash/vpnn/connection_policy.dart';
import 'package:fl_clash/vpnn/contract.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final profiles = [
    const ManagedProfile(id: 'direct', name: 'Direct', config: '{}'),
    const ManagedProfile(id: 'vk', name: 'VK', config: '{}'),
    const ManagedProfile(id: 'dns', name: 'DNS', config: '{}'),
    const ManagedProfile(
      id: 'future',
      kind: 'unknown',
      name: 'Future',
      config: '{}',
    ),
    const ManagedProfile(
      id: 'off',
      kind: 'direct',
      enabled: false,
      name: 'Off',
      config: '{}',
    ),
    const ManagedProfile(
      id: 'new',
      kind: 'direct',
      minimumClientVersion: '99.0.0',
      name: 'New',
      config: '{}',
    ),
  ];
  test(
    'only compatible enabled profiles, deterministic priority and preferred route',
    () {
      final policy = ConnectionPolicy();
      final now = DateTime.utc(2026, 11, 3);
      expect(policy.candidates(profiles, now: now).map((p) => p.id), [
        'direct',
        'vk',
        'dns',
      ]);
      expect(
        policy.candidates(profiles, now: now, preferred: 'vk').first.id,
        'vk',
      );
    },
  );
  test('cooldown prevents ping-pong, last good is network scoped', () {
    final policy = ConnectionPolicy();
    final now = DateTime.utc(2026, 11, 3);
    policy.succeeded('dns');
    expect(policy.candidates(profiles, now: now).first.id, 'dns');
    policy.failed('dns', now);
    expect(policy.candidates(profiles, now: now).map((p) => p.id), [
      'direct',
      'vk',
    ]);
    expect(
      policy.candidates(profiles, now: now, attempted: {'direct', 'vk'}),
      isEmpty,
    );
    expect(
      policy
          .candidates(profiles, now: now.add(const Duration(minutes: 3)))
          .length,
      3,
    );
    policy.networkChanged();
    expect(policy.candidates(profiles, now: now).first.id, 'direct');
  });
  test(
    'multiple direct assignments retain identities and administrator priority',
    () {
      final policy = ConnectionPolicy();
      final routes = [
        const ManagedProfile(
          id: 'fast',
          kind: 'direct',
          priority: 20,
          name: 'Fast',
          config: '{}',
        ),
        const ManagedProfile(
          id: 'backup',
          kind: 'direct',
          priority: 10,
          name: 'Backup',
          config: '{}',
        ),
      ];
      expect(policy.candidates(routes, now: DateTime.now()).map((p) => p.id), [
        'backup',
        'fast',
      ]);
    },
  );
}
