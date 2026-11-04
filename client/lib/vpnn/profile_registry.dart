import 'dart:convert';

import 'contract.dart';
import 'repository.dart';

class ManagedProfileRegistry {
  const ManagedProfileRegistry(this.vault);
  final SecretVault vault;
  String _key(String device) => 'vpnn.profile-modes.$device';

  Set<String> _validated(Iterable<String> ids) {
    final result = ids.toSet();
    if (result.length > 96 ||
        result.any((id) => !RegExp(r'^[a-zA-Z0-9_-]{1,64}$').hasMatch(id))) {
      throw const ConfigException(ConfigFailure.malformed);
    }
    return result;
  }

  Future<Set<String>> read(String device) async {
    final value = await vault.read(_key(device));
    if (value == null) return {};
    try {
      return _validated((jsonDecode(value) as List).cast<String>());
    } catch (_) {
      throw const ConfigException(ConfigFailure.malformed);
    }
  }

  Future<void> write(String device, Set<String> ids) async {
    await vault.write(_key(device), jsonEncode(_validated(ids).toList()));
  }

  Future<void> clear(String device) => vault.delete(_key(device));
}
