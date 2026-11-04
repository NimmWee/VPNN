import 'dart:convert';

import 'package:fl_clash/vpnn/profile_update.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'refresh listener pins embedded proxy even if profile rules use DIRECT',
    () {
      final data = <String, dynamic>{
        'proxies': [
          {
            'name': 'VPNN',
            'x-vpnn': {'mode': 'vk'},
          },
        ],
        'rules': ['MATCH,DIRECT'],
      };
      addManagedRefreshListener(data);
      final listener = (data['listeners'] as List).single as Map;
      expect(listener['proxy'], 'VPNN');
      expect(listener['listen'], '127.0.0.1');
      expect(listener['port'], managedRefreshPort);
    },
  );
  final now = DateTime.utc(2026, 11, 2);
  final expires = now.add(const Duration(days: 7));
  Map<String, dynamic> config(String call, {DateTime? deadline}) => {
    'proxies': [
      {
        'name': 'VPNN',
        'x-vpnn': {
          'vk': {
            'links': [call],
          },
        },
        if (deadline != null)
          'x-vpnn-valid-until': deadline.millisecondsSinceEpoch ~/ 1000,
      },
    ],
    'rules': ['MATCH,VPNN'],
  };
  bool reuse(Map<String, dynamic> old, Map<String, dynamic> next) {
    final installed = jsonDecode(jsonEncode(old)) as Map<String, dynamic>;
    addManagedRefreshListener(installed);
    return canReuseManagedProfile(
      utf8.encode(jsonEncode(installed)),
      jsonEncode(next),
      expiresAt: expires,
      now: now,
    );
  }

  test('unchanged configuration with fresh access does not need a rewrite', () {
    expect(
      reuse(
        config('owned-call', deadline: now.add(const Duration(days: 6))),
        config('owned-call'),
      ),
      isTrue,
    );
  });
  test('changed call or routing replaces the installed profile', () {
    final old = config('old-call', deadline: expires);
    expect(reuse(old, config('new-call')), isFalse);
    final changed = config('old-call')..['rules'] = ['MATCH,DIRECT'];
    expect(reuse(old, changed), isFalse);
  });
  test('expiring access is renewed and shortened access is enforced', () {
    expect(
      reuse(
        config('call', deadline: now.add(const Duration(hours: 12))),
        config('call'),
      ),
      isFalse,
    );
    expect(
      reuse(
        config('call', deadline: expires.add(const Duration(days: 1))),
        config('call'),
      ),
      isFalse,
    );
  });
  test('missing expiry or invalid installed data is repaired', () {
    expect(reuse(config('call'), config('call')), isFalse);
    expect(
      canReuseManagedProfile(
        utf8.encode('bad'),
        jsonEncode(config('call')),
        expiresAt: expires,
        now: now,
      ),
      isFalse,
    );
  });
}
