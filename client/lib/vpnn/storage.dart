import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'repository.dart';

class PlatformSecretVault implements SecretVault {
  const PlatformSecretVault();
  static const _storage = FlutterSecureStorage();
  @override
  Future<String?> read(String key) => _storage.read(key: key);
  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);
  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class FileConfigurationCache implements ConfigurationCache {
  Future<File> get _pending async => File('${(await _file).path}.pending');

  @override
  Future<String?> readPending() async {
    final file = await _pending;
    return await file.exists() ? file.readAsString() : null;
  }

  @override
  Future<void> writePending(String value) async {
    final file = await _pending;
    await file.parent.create(recursive: true);
    final temporary = File('${file.path}.tmp');
    await temporary.writeAsString(value, flush: true);
    await temporary.rename(file.path);
  }

  @override
  Future<void> clearPending() async {
    final file = await _pending;
    if (await file.exists()) await file.delete();
  }

  Future<File> get _file async {
    final directory = await getApplicationSupportDirectory();
    return File(p.join(directory.path, 'vpnn-config.enc'));
  }

  @override
  Future<String?> read() async {
    final file = await _file;
    return await file.exists() ? file.readAsString() : null;
  }

  @override
  Future<void> write(String value) async {
    final file = await _file;
    await file.parent.create(recursive: true);
    final temporary = File('${file.path}.tmp');
    await temporary.writeAsString(value, flush: true);
    await temporary.rename(file.path);
  }

  @override
  Future<void> clear() async {
    final file = await _file;
    if (await file.exists()) await file.delete();
  }
}
