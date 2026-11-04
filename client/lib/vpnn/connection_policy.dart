import 'contract.dart';

class ConnectionPolicy {
  ConnectionPolicy({this.cooldown = const Duration(minutes: 2)});
  final Duration cooldown;
  final _failedUntil = <String, DateTime>{};
  String? _lastGood;

  List<ManagedProfile> candidates(
    List<ManagedProfile> profiles, {
    required DateTime now,
    String? preferred,
    Set<String> attempted = const {},
  }) {
    final result = profiles.where((profile) {
      return profile.available &&
          !attempted.contains(profile.id) &&
          !(_failedUntil[profile.id]?.isAfter(now) ?? false);
    }).toList();
    final first = preferred ?? _lastGood;
    result.sort((left, right) {
      if (left.id == right.id) return 0;
      if (left.id == first) return -1;
      if (right.id == first) return 1;
      final priority = left.connectionPriority.compareTo(
        right.connectionPriority,
      );
      return priority != 0 ? priority : left.id.compareTo(right.id);
    });
    return result;
  }

  void retry(String id) => _failedUntil.remove(id);

  void failed(String id, DateTime now) {
    _failedUntil[id] = now.add(cooldown);
    if (_lastGood == id) _lastGood = null;
  }

  void succeeded(String id) {
    _failedUntil.remove(id);
    _lastGood = id;
  }

  void networkChanged() {
    _failedUntil.clear();
    _lastGood = null;
  }
}
