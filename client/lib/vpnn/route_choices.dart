import 'dart:async';

import 'package:fl_clash/common/context.dart';
import 'package:fl_clash/ui/ui.dart';
import 'package:fl_clash/ui/icons/icons.dart';
import 'package:material_ui/material_ui.dart';

import 'build_variant.dart';
import 'controller.dart';
import 'contract.dart';

String managedRouteLabel(BuildContext context, ManagedProfile profile) {
  if (profile.id != profile.kind) return profile.name;
  final l = context.appLocalizations;
  return switch (profile.kind) {
    'direct' => l.vpnnDirect,
    'vk' => l.vpnnVK,
    _ => l.vpnnDNS,
  };
}

class ManagedRouteChoices extends StatelessWidget {
  const ManagedRouteChoices({
    super.key,
    required this.controller,
    this.admin = vpnnAdminBuild,
  });
  final VpnnController controller;
  final bool admin;

  @override
  Widget build(BuildContext context) {
    final l = context.appLocalizations;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final profiles =
            controller.configuration?.profiles
                .where((p) => p.available)
                .toList() ??
            [];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (!admin)
              _RouteCard(
                id: 'auto',
                title: l.vpnnAutoMode,
                hint: l.vpnnAutoModeHint,
                glyph: AppGlyphs.sparkle,
                selected: controller.automaticSelection,
                onTap: profiles.isEmpty
                    ? null
                    : () => unawaited(controller.selectAutomatically()),
              ),
            for (final profile in profiles) ...[
              const SizedBox(height: 10),
              _RouteCard(
                id: profile.id,
                title: managedRouteLabel(context, profile),
                hint: switch (profile.kind) {
                  'direct' => l.vpnnDirectUserHint,
                  'vk' => l.vpnnVKUserHint,
                  _ => l.vpnnDNSUserHint,
                },
                glyph: switch (profile.kind) {
                  'direct' => AppGlyphs.proxies,
                  'vk' => AppGlyphs.connections,
                  _ => AppGlyphs.dns,
                },
                selected:
                    !controller.automaticSelection &&
                    controller.selectedMode == profile.id,
                onTap: () => unawaited(
                  admin
                      ? controller.selectMode(profile.id)
                      : controller.selectManualMode(profile.id),
                ),
              ),
            ],
            if (profiles.isEmpty) Text(l.vpnnNoRoutes),
          ],
        );
      },
    );
  }
}

class _RouteCard extends StatelessWidget {
  const _RouteCard({
    required this.id,
    required this.title,
    required this.hint,
    required this.glyph,
    required this.selected,
    this.onTap,
  });
  final String id;
  final String title;
  final String hint;
  final Glyph glyph;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    key: ValueKey('route:$id'),
    button: true,
    selected: selected,
    enabled: onTap != null,
    child: Material(
      shape: AppShape.lg,
      color: SurfaceLevel.block.colorOf(Theme.of(context).colorScheme),
      child: InkWell(
        customBorder: AppShape.lg,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              GlyphIcon(glyph),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: AppTextStyle.headline.of(context)),
                    const SizedBox(height: 4),
                    Text(hint, style: AppTextStyle.footnote.of(context)),
                  ],
                ),
              ),
              if (selected) ...[
                const SizedBox(width: 12),
                const SelectionCheck(),
              ],
            ],
          ),
        ),
      ),
    ),
  );
}
