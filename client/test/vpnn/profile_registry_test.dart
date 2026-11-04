import 'package:fl_clash/vpnn/profile_registry.dart';
import 'package:flutter_test/flutter_test.dart';

import 'repository_test.dart' show MemoryVault;

void main() {
  test('managed IDs survive restart for precise revocation cleanup', () async {
    final vault = MemoryVault();
    final registry = ManagedProfileRegistry(vault);
    await registry.write('device', {'fast', 'backup', 'vk'});
    expect(await ManagedProfileRegistry(vault).read('device'), {
      'fast',
      'backup',
      'vk',
    });
    expect(await registry.read('another'), isEmpty);
    await registry.clear('device');
    expect(await registry.read('device'), isEmpty);
  });
  test(
    'registry never accepts arbitrary file paths or unbounded IDs',
    () async {
      final registry = ManagedProfileRegistry(MemoryVault());
      await expectLater(
        registry.write('device', {'../outside'}),
        throwsA(anything),
      );
    },
  );
}
