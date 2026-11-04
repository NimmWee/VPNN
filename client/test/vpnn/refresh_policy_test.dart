import 'package:fl_clash/vpnn/refresh_policy.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('refresh is early with bounded jitter and failures back off', () {
    final now = DateTime.utc(2026, 11, 3);
    final policy = RefreshPolicy(jitter: () => 0.5);
    expect(policy.due(now), isTrue);
    policy.succeeded(now, now.add(const Duration(days: 7)));
    expect(policy.due(now.add(const Duration(minutes: 10))), isFalse);
    expect(policy.due(now.add(const Duration(hours: 7))), isTrue);
    policy.failed(now);
    expect(policy.due(now.add(const Duration(seconds: 29))), isFalse);
    expect(policy.due(now.add(const Duration(seconds: 31))), isTrue);
    for (var i = 0; i < 20; i++) {
      policy.failed(now);
    }
    expect(policy.due(now.add(const Duration(minutes: 31))), isTrue);
    policy.succeeded(
      now,
      now.add(const Duration(days: 7)),
      refreshAfter: now.add(const Duration(minutes: 5)),
    );
    expect(policy.due(now.add(const Duration(minutes: 6))), isTrue);
  });
}
