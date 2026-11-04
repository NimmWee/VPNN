import 'dart:io';
import 'dart:async';

import 'package:fl_clash/vpnn/config_transport.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'TLS verification remains mandatory when app overrides allow bad certificates',
    () async {
      final context = SecurityContext()
        ..useCertificateChain('core/Clash.Meta/test/config/example.org.pem')
        ..usePrivateKey('core/Clash.Meta/test/config/example.org-key.pem');
      final server = await HttpServer.bindSecure(
        InternetAddress.loopbackIPv4,
        0,
        context,
      );
      addTearDown(() => server.close(force: true));
      server.listen((request) async {
        await request.response.close();
      }, onError: (Object _) {});
      final permissive = HttpClient()..badCertificateCallback = (_, _, _) => true;
      await HttpOverrides.runZoned(
        () async {
          final transport = ConfigTransport.direct();
          addTearDown(transport.close);
          await expectLater(
            transport.get(
              Uri.parse('https://127.0.0.1:${server.port}'),
              token: 'test',
              minimumVersion: 1,
            ),
            throwsA(isA<HandshakeException>()),
          );
        },
        createHttpClient: (_) => permissive,
      );
    },
  );

  test('closing a transport interrupts an active request', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    final entered = Completer<void>();
    server.listen((request) {
      entered.complete();
    });
    final transport = ConfigTransport.direct();
    final pending = transport.get(
      Uri.parse('http://127.0.0.1:${server.port}'),
      token: 'test',
      minimumVersion: 1,
    );
    final expected = expectLater(pending, throwsA(anything));
    await entered.future;
    transport.close();
    await expected.timeout(const Duration(seconds: 2));
  });

  test('oversized response is rejected before parsing', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    server.listen((request) async {
      request.response.contentLength = 1500001;
      request.response.add(List.filled(1500001, 32));
      await request.response.close();
    });
    final transport = ConfigTransport.direct();
    addTearDown(transport.close);
    await expectLater(
      transport.get(
        Uri.parse('http://127.0.0.1:${server.port}'),
        token: 'test',
        minimumVersion: 1,
      ),
      throwsA(anything),
    );
  });
  test('redirect is returned without forwarding credentials', () async {
    final api = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(api.close);
    var requests = 0;
    api.listen((request) async {
      requests++;
      request.response.statusCode = 302;
      request.response.headers.set('location', '/other');
      await request.response.close();
    });
    final transport = ConfigTransport.direct();
    addTearDown(transport.close);
    final response = await transport.get(
      Uri.parse('http://127.0.0.1:${api.port}'),
      token: 'test',
      minimumVersion: 1,
    );
    expect(response.status, 302);
    expect(requests, 1);
  });
  test(
    'selected proxy receives request for an unreachable direct target',
    () async {
      final proxy = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(proxy.close);
      var requests = 0;
      proxy.listen((request) async {
        requests++;
        expect(request.headers.value('Authorization'), 'Bearer test');
        request.response.write('{"ok":true}');
        await request.response.close();
      });
      final transport = ConfigTransport.core(port: proxy.port, mode: 'vk');
      addTearDown(transport.close);
      final response = await transport.get(
        Uri.parse('http://unreachable.invalid/api/device/config'),
        token: 'test',
        minimumVersion: 1,
      );
      expect(response.status, 200);
      expect(requests, 1);
      expect(transport.mode, 'vk');
    },
  );

  test('dead proxy never falls back to reachable direct API', () async {
    final api = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(api.close);
    var requests = 0;
    api.listen((request) async {
      requests++;
      await request.response.close();
    });
    final reserved = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final port = reserved.port;
    await reserved.close();
    final transport = ConfigTransport.core(port: port, mode: 'dns');
    addTearDown(transport.close);
    await expectLater(
      transport.get(
        Uri.parse('http://127.0.0.1:${api.port}'),
        token: 'test',
        minimumVersion: 1,
      ),
      throwsA(anything),
    );
    expect(requests, 0);
  });
}
