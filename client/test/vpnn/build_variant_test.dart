import 'package:fl_clash/enum/enum.dart';
import 'package:fl_clash/views/navigation.dart';
import 'package:fl_clash/vpnn/build_variant.dart';
import 'package:fl_clash/providers/state.dart' show shownPageLabelOf;
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('user navigation cannot expose persisted advanced pages', () {
    final items = Navigation.forVariant(
      admin: false,
    ).getItems(openLogs: true, hasProxies: true);
    expect(items.map((item) => item.label), [PageLabel.dashboard]);
    expect(Navigation().getItems().length, vpnnAdminBuild ? greaterThan(1) : 1);
    expect(shownPageLabelOf(PageLabel.tools, items), PageLabel.dashboard);
    expect(shownPageLabelOf(PageLabel.profiles, items), PageLabel.dashboard);
  });
  test('admin keeps existing profile and diagnostic navigation', () {
    final labels = Navigation.forVariant(
      admin: true,
    ).getItems(openLogs: true, hasProxies: true).map((item) => item.label);
    expect(
      labels,
      containsAll([
        PageLabel.dashboard,
        PageLabel.profiles,
        PageLabel.proxies,
        PageLabel.tools,
      ]),
    );
  });
}
