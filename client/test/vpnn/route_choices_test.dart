import 'package:fl_clash/l10n/l10n.dart';
import 'package:fl_clash/vpnn/contract.dart';
import 'package:fl_clash/vpnn/controller.dart';
import 'package:fl_clash/vpnn/route_choices.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';

import 'controller_test.dart' show StubConnection, StubRepository;

void main() {
  testWidgets(
    'user sees Auto and assigned routes only, at large text in dark mode',
    (tester) async {
      final repository = StubRepository();
      final old = repository.configuration!;
      repository.configuration = ManagedConfiguration(
        version: old.version,
        expiresAt: old.expiresAt,
        profiles: const [ManagedProfile(id: 'vk', name: 'VK', config: '{}')],
      );
      final controller = VpnnController(
        repository: repository,
        connection: StubConnection(),
        poll: false,
        defaultAutomatic: true,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          localizationsDelegates: const [AppLocalizations.delegate],
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: const TextScaler.linear(2)),
            child: child!,
          ),
          home: Scaffold(
            body: SingleChildScrollView(
              child: ManagedRouteChoices(controller: controller, admin: false),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Automatic'), findsOneWidget);
      expect(find.text('Via VK'), findsOneWidget);
      expect(find.text('Via DNS'), findsNothing);
      expect(find.text('Standard'), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.ensureVisible(find.text('Via VK'));
      await tester.tap(find.text('Via VK'));
      await tester.pumpAndSettle();
      expect(controller.automaticSelection, isFalse);
      expect(controller.selectedMode, 'vk');
    },
  );
}
