import 'dart:math';

class RefreshPolicy {
  RefreshPolicy({double Function()? jitter})
    : _jitter = jitter ?? Random().nextDouble;
  final double Function() _jitter;
  DateTime? _next;
  int _failures = 0;

  bool due(DateTime now) => _next == null || !now.isBefore(_next!);

  void succeeded(DateTime now, DateTime expiresAt, {DateTime? refreshAfter}) {
    _failures = 0;
    final remaining = expiresAt.difference(now).inSeconds;
    final seconds = min(
      21600,
      max(
        30,
        min(remaining ~/ 2, refreshAfter?.difference(now).inSeconds ?? 21600),
      ),
    );
    _next = now.add(
      Duration(seconds: (seconds * (0.9 + _jitter() * 0.2)).round()),
    );
  }

  void failed(DateTime now) {
    final seconds = min(1800, 30 * (1 << min(_failures++, 6)));
    _next = now.add(
      Duration(seconds: (seconds * (0.9 + _jitter() * 0.2)).round()),
    );
  }
}
