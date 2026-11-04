import 'dart:async';
import 'dart:io';

import 'contract.dart';

class ConfigResponse {
  const ConfigResponse(this.status, this.bytes);
  final int status;
  final List<int> bytes;
}

class ConfigTransport {
  ConfigTransport.direct() : mode = 'direct', _proxy = 'DIRECT';
  ConfigTransport.core({required int port, required this.mode})
    : _proxy = 'PROXY 127.0.0.1:$port' {
    if (port < 1 ||
        port > 65535 ||
        !const ['vk', 'dns', 'direct'].contains(mode)) {
      throw const ConfigException(ConfigFailure.network);
    }
  }

  final String mode;
  final String _proxy;
  final _client = HttpClient()..connectionTimeout = const Duration(seconds: 8);
  bool _closed = false;

  Future<ConfigResponse> get(
    Uri uri, {
    required String token,
    required int minimumVersion,
    String? nonce,
  }) async {
    if (_closed) throw const ConfigException(ConfigFailure.network);
    _client.findProxy = (_) => _proxy;
    _client.badCertificateCallback = null;
    final timer = Timer(const Duration(seconds: 25), close);
    try {
      return await _get(
        uri,
        token,
        minimumVersion,
        nonce,
      ).timeout(const Duration(seconds: 25));
    } finally {
      timer.cancel();
    }
  }

  Future<ConfigResponse> _get(
    Uri uri,
    String token,
    int minimumVersion,
    String? nonce,
  ) async {
    final request = await _client.getUrl(uri);
    request.followRedirects = false;
    request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
    request.headers.set('X-VPNN-Version', minimumVersion.toString());
    if (nonce != null) request.headers.set('X-VPNN-Nonce', nonce);
    final response = await request.close();
    if (response.contentLength > 1500000) {
      throw const ConfigException(ConfigFailure.malformed);
    }
    final bytes = <int>[];
    await for (final chunk in response) {
      bytes.addAll(chunk);
      if (bytes.length > 1500000) {
        throw const ConfigException(ConfigFailure.malformed);
      }
    }
    return ConfigResponse(response.statusCode, bytes);
  }

  void close() {
    _closed = true;
    _client.close(force: true);
  }
}
