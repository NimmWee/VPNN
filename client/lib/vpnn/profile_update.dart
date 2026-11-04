import 'dart:convert';

import 'package:collection/collection.dart';

import 'contract.dart';

const managedRefreshPort = 19094;

void addManagedRefreshListener(Map<String, dynamic> data) {
  final embedded = (data['proxies'] as List)
      .cast<Map<String, dynamic>>()
      .where((proxy) => proxy.containsKey('x-vpnn'))
      .toList();
  if (embedded.isEmpty) return;
  if (embedded.length != 1 || embedded.single['name'] is! String) {
    throw const ConfigException(ConfigFailure.malformed);
  }
  final name = embedded.single['name'] as String;
  if (name.isEmpty || const ['DIRECT', 'GLOBAL', 'REJECT'].contains(name)) {
    throw const ConfigException(ConfigFailure.malformed);
  }
  final listeners = (data['listeners'] as List? ?? []).toList();
  if (listeners.any(
    (entry) => (entry as Map)['name'] == 'VPNN config refresh',
  )) {
    throw const ConfigException(ConfigFailure.malformed);
  }
  listeners.add({
    'name': 'VPNN config refresh',
    'type': 'http',
    'listen': '127.0.0.1',
    'port': managedRefreshPort,
    'users': <Object>[],
    'proxy': name,
  });
  data['listeners'] = listeners;
}

bool canReuseManagedProfile(
  List<int> installed,
  String incoming, {
  required DateTime expiresAt,
  required DateTime now,
}) {
  try {
    if (installed.length > 1500000 || incoming.length > 1500000) return false;
    final old = jsonDecode(utf8.decode(installed)) as Map<String, dynamic>;
    final next = jsonDecode(incoming) as Map<String, dynamic>;
    addManagedRefreshListener(next);
    final proxies = old['proxies'] as List;
    if (proxies.isEmpty) return false;
    final renewal =
        now.add(const Duration(days: 1)).millisecondsSinceEpoch ~/ 1000;
    final maximum = expiresAt.millisecondsSinceEpoch ~/ 1000;
    for (final proxy in proxies) {
      final value = proxy as Map<String, dynamic>;
      final deadline = value.remove('x-vpnn-valid-until');
      if (deadline is! int || deadline <= renewal || deadline > maximum) {
        return false;
      }
    }
    for (final proxy in next['proxies'] as List) {
      (proxy as Map<String, dynamic>).remove('x-vpnn-valid-until');
    }
    return const DeepCollectionEquality().equals(old, next);
  } catch (_) {
    return false;
  }
}
