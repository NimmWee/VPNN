const vpnnAdminBuild = bool.fromEnvironment('VPNN_ADMIN');
const managedClientVersion = '0.1.6';

bool managedVersionSupported(String minimum) {
  List<int>? parts(String value) {
    if (!RegExp(r'^\d{1,4}\.\d{1,4}\.\d{1,4}$').hasMatch(value)) return null;
    return value.split('.').map(int.parse).toList();
  }

  final required = parts(minimum);
  final current = parts(managedClientVersion)!;
  if (required == null) return false;
  for (var i = 0; i < 3; i++) {
    if (required[i] != current[i]) return required[i] < current[i];
  }
  return true;
}
