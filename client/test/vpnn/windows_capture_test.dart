import 'dart:io';

import 'package:fl_clash/enum/enum.dart';
import 'package:fl_clash/providers/providers.dart';
import 'package:fl_clash/vpnn/provider.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class RecordingOwner extends SetupAction {
  final calls = <bool>[];
  bool? tunAtStart;
  bool? androidVpnAtStart;
  bool authorize = true;
  @override
  void build() {}
  @override
  Future<bool> setRunning(bool running, {bool initialize = false}) async {
    calls.add(running);
    if (running) {
      androidVpnAtStart = ref.read(vpnSettingProvider).enable;
      tunAtStart = ref.read(patchClashConfigProvider).tun.enable;
      ref.read(authorizedTunEnableProvider.notifier).value = authorize
          ? TunAuthorizationState.authorized
          : TunAuthorizationState.none;
      if (!authorize) {
        ref
            .read(patchClashConfigProvider.notifier)
            .update((state) => state.copyWith.tun(enable: false));
      }
    }
    return true;
  }
}

void main() {
  test(
    'managed Android enables the existing VPN owner and rule routing',
    () async {
      final owner = RecordingOwner();
      final adapter = Provider(
        (ref) =>
            ManagedPlatformConnection(ref, isAndroid: true, isWindows: false),
      );
      final container = ProviderContainer(
        overrides: [
          safeModeProvider.overrideWithValue(false),
          setupActionProvider.overrideWith(() => owner),
        ],
      );
      addTearDown(container.dispose);
      container
          .read(vpnSettingProvider.notifier)
          .update((state) => state.copyWith(enable: false));
      container
          .read(patchClashConfigProvider.notifier)
          .update((state) => state.copyWith(mode: Mode.direct));
      await container.read(adapter).setRunning(true);
      expect(owner.androidVpnAtStart, isTrue);
      expect(container.read(patchClashConfigProvider).mode, Mode.rule);
      expect(owner.calls, [true]);
    },
  );
  test(
    'managed Windows start requests TUN through the existing owner',
    () async {
      final owner = RecordingOwner();
      final adapter = Provider((ref) => ManagedPlatformConnection(ref));
      final container = ProviderContainer(
        overrides: [
          safeModeProvider.overrideWithValue(false),
          setupActionProvider.overrideWith(() => owner),
        ],
      );
      addTearDown(container.dispose);
      await container.read(adapter).setRunning(true);
      expect(owner.tunAtStart, isTrue);
      expect(container.read(patchClashConfigProvider).ipv6, isTrue);
      expect(
        container.read(patchClashConfigProvider).generalOverrideKeys,
        contains(GeneralOverrideKey.ipv6),
      );
      expect(owner.calls, [true]);
    },
    skip: !Platform.isWindows,
  );

  test(
    'failed capture authorization stops the owner instead of reporting success',
    () async {
      final owner = RecordingOwner()..authorize = false;
      final adapter = Provider((ref) => ManagedPlatformConnection(ref));
      final container = ProviderContainer(
        overrides: [
          safeModeProvider.overrideWithValue(false),
          setupActionProvider.overrideWith(() => owner),
        ],
      );
      addTearDown(container.dispose);
      await expectLater(
        container.read(adapter).setRunning(true),
        throwsA(predicate((e) => e.toString().contains('capture'))),
      );
      expect(owner.calls, [true, false]);
    },
    skip: !Platform.isWindows,
  );

  test('safe mode does not request native takeover', () async {
    final owner = RecordingOwner();
    final adapter = Provider((ref) => ManagedPlatformConnection(ref));
    final container = ProviderContainer(
      overrides: [
        safeModeProvider.overrideWithValue(true),
        setupActionProvider.overrideWith(() => owner),
      ],
    );
    addTearDown(container.dispose);
    await container.read(adapter).setRunning(true);
    expect(owner.tunAtStart, isFalse);
  });
}
