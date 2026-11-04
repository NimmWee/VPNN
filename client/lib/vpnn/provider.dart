import 'dart:async';
import 'dart:convert';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:fl_clash/common/system.dart';
import 'package:fl_clash/enum/enum.dart';
import 'package:fl_clash/models/models.dart';
import 'package:fl_clash/providers/providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'contract.dart';
import 'config_transport.dart';
import 'controller.dart';
import 'profile_update.dart';
import 'repository.dart';
import 'storage.dart';
import 'health.dart';
import 'build_variant.dart';
import 'profile_registry.dart';

final vpnnControllerProvider = Provider<VpnnController>((ref) {
  final connection = ManagedPlatformConnection(ref);
  late final ConfigurationRepository repository;
  repository = ConfigurationRepository(
    vault: const PlatformSecretVault(),
    cache: FileConfigurationCache(),
    transport: () {
      if (!connection.running || connection.suspended) {
        return ConfigTransport.direct();
      }
      final enrollment = repository.enrollment;
      final active = enrollment == null
          ? null
          : connection.activeMode(enrollment);
      final mode = repository.configuration?.profiles
          .where((profile) => profile.id == active && profile.available)
          .firstOrNull
          ?.kind;
      if (mode == null) throw const ConfigException(ConfigFailure.network);
      return ConfigTransport.core(
        port: mode == 'direct'
            ? ref.read(patchClashConfigProvider).mixedPort
            : managedRefreshPort,
        mode: mode,
      );
    },
  );
  final controller = VpnnController(
    repository: repository,
    connection: connection,
    defaultAutomatic: !vpnnAdminBuild,
  );
  ref.onDispose(controller.dispose);
  unawaited(controller.initialize());
  return controller;
});

int managedProfileId(String device, String mode) {
  final digest = crypto.sha256
      .convert(utf8.encode('VPNN:$device:$mode'))
      .toString();
  return -int.parse(digest.substring(0, 12), radix: 16) - 1;
}

class ManagedPlatformConnection
    implements ManagedConnection, ManagedProfileUpdates {
  ManagedPlatformConnection(this.ref, {bool? isAndroid, bool? isWindows})
    : _isAndroid = isAndroid ?? system.isAndroid,
      _isWindows = isWindows ?? system.isWindows;
  final Ref ref;
  final bool _isAndroid;
  final bool _isWindows;
  final _modes = <String>{'direct', 'vk', 'dns'};
  final _registry = const ManagedProfileRegistry(PlatformSecretVault());

  @override
  Future<bool> needsReload(
    Enrollment enrollment,
    ManagedConfiguration config,
    String mode,
  ) async {
    final existing = ref
        .read(profilesProvider)
        .where(
          (profile) =>
              profile.id == managedProfileId(enrollment.deviceId, mode),
        )
        .firstOrNull;
    final incoming = config.profiles
        .where((profile) => profile.id == mode)
        .firstOrNull;
    if (existing == null || incoming == null) return true;
    return !await _canReuse(existing, incoming, config.expiresAt);
  }

  @override
  bool get running => ref.read(isStartProvider);

  @override
  bool get suspended => ref.read(suspendProvider);

  @override
  bool? get internet => ref.read(vpnnInternetHealthProvider);

  @override
  Future<bool?> checkInternet() => ref.read(vpnnHealthMonitorProvider).check();

  @override
  String? activeMode(Enrollment enrollment) {
    final id = ref.read(currentProfileIdProvider);
    for (final mode in _modes) {
      if (id == managedProfileId(enrollment.deviceId, mode)) return mode;
    }
    return null;
  }

  @override
  Future<void> validate(ManagedConfiguration config) async {
    for (final profile in config.profiles.where(
      (profile) => profile.available,
    )) {
      final message = await ref
          .read(coreHandlerProvider)
          .validateConfigWithData(utf8.encode(profile.config));
      if (message.isNotEmpty) {
        throw const ConfigException(ConfigFailure.malformed);
      }
    }
  }

  @override
  Future<void> install(
    Enrollment enrollment,
    ManagedConfiguration config,
  ) async {
    final ids = <int>{};
    _modes.addAll(const ['direct', 'vk', 'dns']);
    _modes.addAll(await _registry.read(enrollment.deviceId));
    final incomingModes = config.profiles
        .where((profile) => profile.available)
        .map((profile) => profile.id)
        .toSet();
    _modes.addAll(incomingModes);
    await _registry.write(enrollment.deviceId, _modes);
    for (final managed in config.profiles.where(
      (profile) => profile.available,
    )) {
      final id = managedProfileId(enrollment.deviceId, managed.id);
      ids.add(id);
      final existing = ref
          .read(profilesProvider)
          .where((profile) => profile.id == id)
          .firstOrNull;
      final label = 'VPNN · ${managed.name}';
      if (existing != null &&
          await _canReuse(existing, managed, config.expiresAt)) {
        if (existing.label != label) {
          ref
              .read(profilesActionProvider.notifier)
              .putProfile(existing.copyWith(label: label));
        }
        continue;
      }
      final profile = (existing ?? Profile.normal(label: label)).copyWith(
        id: id,
        label: label,
        autoUpdate: false,
      );
      final updated = await profile.saveFile(
        await _profileBytes(managed, config.expiresAt),
        validate: (path, key) =>
            ref.read(coreHandlerProvider).validateProfile(path, key),
      );
      ref.read(profilesActionProvider.notifier).putProfile(updated);
    }
    for (final mode in _modes) {
      final id = managedProfileId(enrollment.deviceId, mode);
      if (!ids.contains(id) &&
          ref.read(profilesProvider).any((profile) => profile.id == id)) {
        await ref.read(profilesActionProvider.notifier).deleteProfile(id);
      }
    }
    await _registry.write(enrollment.deviceId, incomingModes);
    _modes
      ..clear()
      ..addAll(incomingModes);
  }

  static Future<bool> _canReuse(
    Profile existing,
    ManagedProfile incoming,
    DateTime expiresAt,
  ) async {
    try {
      final bytes = await (await existing.file).readAsBytes();
      return await Isolate.run(
        () => canReuseManagedProfile(
          bytes,
          incoming.config,
          expiresAt: expiresAt,
          now: DateTime.now(),
        ),
      );
    } catch (_) {
      return false;
    }
  }

  static Future<Uint8List> _profileBytes(
    ManagedProfile profile,
    DateTime expiresAt,
  ) => Isolate.run(() {
    final data = jsonDecode(profile.config) as Map<String, dynamic>;
    addManagedRefreshListener(data);
    for (final proxy in data['proxies'] as List) {
      (proxy as Map<String, dynamic>)['x-vpnn-valid-until'] =
          expiresAt.millisecondsSinceEpoch ~/ 1000;
    }
    return Uint8List.fromList(utf8.encode(jsonEncode(data)));
  });

  @override
  Future<void> select(Enrollment enrollment, String mode) async {
    ref.read(currentProfileIdProvider.notifier).value = managedProfileId(
      enrollment.deviceId,
      mode,
    );
    if (!await ref
        .read(setupActionProvider.notifier)
        .applyProfile(force: true)) {
      throw const ConfigException(ConfigFailure.malformed);
    }
  }

  @override
  Future<bool> setRunning(bool value) async {
    final managedWindows = _isWindows && !ref.read(safeModeProvider);
    final managedAndroid = _isAndroid && !ref.read(safeModeProvider);
    if (value && managedAndroid) {
      ref
          .read(vpnSettingProvider.notifier)
          .update((state) => state.copyWith(enable: true));
    }
    if (value && (managedWindows || managedAndroid)) {
      ref
          .read(patchClashConfigProvider.notifier)
          .update(
            (state) => state.copyWith(
              mode: Mode.rule,
              ipv6: managedWindows ? true : state.ipv6,
              generalOverrideKeys: {
                ...state.generalOverrideKeys,
                if (managedWindows) GeneralOverrideKey.ipv6,
              },
              tun: managedWindows
                  ? state.tun.copyWith(enable: true)
                  : state.tun,
            ),
          );
    }
    final owner = ref.read(setupActionProvider.notifier);
    final answered = await owner.setRunning(value, initialize: value);
    if (value &&
        answered &&
        managedWindows &&
        !suspended &&
        (!ref.read(patchClashConfigProvider).tun.enable ||
            ref.read(authorizedTunEnableProvider) !=
                TunAuthorizationState.authorized)) {
      await owner.setRunning(false);
      throw const ConfigException(ConfigFailure.capture);
    }
    return answered;
  }

  @override
  Future<void> remove(Enrollment enrollment) async {
    _modes.addAll(const ['direct', 'vk', 'dns']);
    _modes.addAll(await _registry.read(enrollment.deviceId));
    for (final mode in _modes) {
      final id = managedProfileId(enrollment.deviceId, mode);
      if (ref.read(profilesProvider).any((profile) => profile.id == id)) {
        await ref.read(profilesActionProvider.notifier).deleteProfile(id);
      }
    }
    await _registry.clear(enrollment.deviceId);
    _modes.clear();
  }

  @override
  Future<Map<String, dynamic>> transportStatus() =>
      ref.read(coreHandlerProvider).getVpnnStatus();
}
