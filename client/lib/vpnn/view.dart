import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:fl_clash/common/common.dart';
import 'package:fl_clash/providers/providers.dart';
import 'package:fl_clash/state.dart';
import 'package:fl_clash/ui/ui.dart';
import 'package:fl_clash/ui/icons/icons.dart';
import 'package:fl_clash/views/dashboard/dashboard.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';
import 'package:url_launcher/url_launcher.dart';

import 'contract.dart';
import 'controller.dart';
import 'provider.dart';
import 'bootstrap.dart';
import 'health.dart';
import 'diagnostics.dart';
import 'build_variant.dart';
import 'route_choices.dart';

class VpnnView extends ConsumerStatefulWidget {
  const VpnnView({super.key});
  @override
  ConsumerState<VpnnView> createState() => _VpnnViewState();
}

class _VpnnViewState extends ConsumerState<VpnnView> {
  final _invitation = TextEditingController();
  bool _checking = false;

  Future<void> _exportDiagnostics(VpnnController controller) async {
    await globalState.safeRun(() async {
      final info = globalState.packageInfo;
      final report = controller.diagnosticReport(
        version: '${info.version}+${info.buildNumber}',
      );
      final bytes = Uint8List.fromList(
        utf8.encode(const JsonEncoder.withIndent('  ').convert(report)),
      );
      await picker.saveFile('VPNN-diagnostics.json', bytes);
    });
  }

  String _stageText(BuildContext context, ConnectionStage stage) {
    final l = context.appLocalizations;
    return switch (stage) {
      ConnectionStage.idle => l.vpnnOff,
      ConnectionStage.settings => l.vpnnStageSettings,
      ConnectionStage.selecting => l.vpnnStageSelecting,
      ConnectionStage.systemTunnel => l.vpnnStageTunnel,
      ConnectionStage.transport => l.vpnnTransportConnecting,
      ConnectionStage.captcha => l.vpnnCaptcha,
      ConnectionStage.checking => l.vpnnStageChecking,
      ConnectionStage.ready => l.vpnnTransportReady,
      ConnectionStage.failed => l.vpnnTransportError,
    };
  }

  @override
  void dispose() {
    _invitation.dispose();
    super.dispose();
  }

  Future<void> _enroll(VpnnController controller) async {
    if (await controller.enroll(_invitation.text) && mounted) {
      _invitation.clear();
    }
  }

  Future<void> _importBootstrap(VpnnController controller) async {
    await globalState.safeRun(() async {
      final file = await picker.pickerFile();
      if (file == null || !mounted) return;
      final bytes = await file.length() > maxBootstrapBytes
          ? const <int>[]
          : await file.readBytes();
      if (!mounted) return;
      await controller.importBootstrap(bytes);
    });
  }

  Future<void> _check() async {
    setState(() => _checking = true);
    try {
      await ref.read(vpnnControllerProvider).checkInternet();
    } finally {
      if (mounted) {
        setState(() {
          _checking = false;
        });
      }
    }
  }

  Future<void> _captcha(String text) async {
    final uri = Uri.tryParse(text);
    final safe =
        uri != null &&
        uri.userInfo.isEmpty &&
        ((uri.scheme == 'http' &&
                const ['127.0.0.1', 'localhost', '::1'].contains(uri.host)) ||
            (uri.scheme == 'https' &&
                (const ['vk.com', 'vk.ru'].contains(uri.host) ||
                    uri.host.endsWith('.vk.com') ||
                    uri.host.endsWith('.vk.ru'))));
    if (!safe) return;
    try {
      final opened = await launchUrl(
        uri,
        mode: system.isAndroid
            ? LaunchMode.inAppWebView
            : LaunchMode.externalApplication,
        webViewConfiguration: const WebViewConfiguration(
          enableJavaScript: true,
          enableDomStorage: true,
        ),
      );
      if (!opened) throw StateError('Verification page could not open');
    } catch (_) {
      if (mounted) {
        await dialogs.showMessage(
          message: TextSpan(text: context.appLocalizations.vpnnErrorNetwork),
        );
      }
    }
  }

  String _failureText(
    BuildContext context,
    ConfigFailure failure,
    VpnnController controller,
  ) {
    final l = context.appLocalizations;
    if (failure == ConfigFailure.network) {
      if (!controller.networkAvailable) return l.vpnnNoNetwork;
      if (controller.routesExhausted) return l.vpnnNoRoutes;
    }
    return switch (failure) {
      ConfigFailure.network => l.vpnnErrorNetwork,
      ConfigFailure.capture => l.vpnnErrorCapture,
      ConfigFailure.malformed => l.vpnnErrorInvalid,
      ConfigFailure.signature => l.vpnnErrorSignature,
      ConfigFailure.device => l.vpnnErrorDevice,
      ConfigFailure.rollback => l.vpnnErrorRollback,
      ConfigFailure.expired => l.vpnnErrorExpired,
      ConfigFailure.revoked => l.vpnnErrorRevoked,
    };
  }

  @override
  Widget build(BuildContext context) {
    final controller = ref.watch(vpnnControllerProvider);
    final running = ref.watch(isStartProvider);
    final safeMode = ref.watch(safeModeProvider);
    final suspended = ref.watch(suspendProvider);
    final internet = ref.watch(vpnnInternetHealthProvider);
    final l = context.appLocalizations;
    final colors = Theme.of(context).colorScheme;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final config = controller.configuration;
        final captcha = controller.transport['captchaUrl'] as String?;
        final transportState = controller.transport['state'];
        final activeProfile = config?.profiles
            .where((profile) => profile.id == controller.selectedMode)
            .firstOrNull;
        final tunnelReady =
            running &&
            !safeMode &&
            !suspended &&
            controller.transport['captureReady'] == true &&
            (activeProfile?.kind == 'direct' ||
                transportState == 'ready' ||
                transportState == 'connected');
        return CommonScaffold(
          title: vpnnAdminBuild ? 'VPNN Admin' : 'VPNN',
          iconActions: [
            IconButtonData(
              glyph: AppGlyphs.export,
              tooltip: l.vpnnExportDiagnostics,
              onPressed: () => unawaited(_exportDiagnostics(controller)),
            ),
            if (vpnnAdminBuild)
              IconButtonData(
                glyph: AppGlyphs.dashboard,
                tooltip: l.vpnnAdvanced,
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => const DashboardView(),
                  ),
                ),
              ),
          ],
          body: Builder(
            builder: (context) => SingleChildScrollView(
              padding: EdgeInsets.fromLTRB(
                24,
                context.contentTopPadding + 24,
                24,
                context.bottomInset + 24,
              ),
              child: Align(
                alignment: Alignment.topCenter,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 800),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (controller.enrollment == null ||
                          MediaQuery.sizeOf(context).width >= 620) ...[
                        Text(
                          vpnnAdminBuild ? l.vpnnTagline : l.vpnnUserTagline,
                          style: AppTextStyle.title1.of(context),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          l.vpnnIntro,
                          style: AppTextStyle.body
                              .of(context)
                              .copyWith(color: colors.onSurfaceVariant),
                        ),
                        const SizedBox(height: 28),
                      ],
                      if (controller.enrollment != null)
                        _Panel(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Row(
                                children: [
                                  GlyphIcon(
                                    running && !safeMode
                                        ? AppGlyphs.verified
                                        : AppGlyphs.vpn,
                                    size: 44,
                                    color: tunnelReady
                                        ? colors.primary
                                        : colors.onSurfaceVariant,
                                  ),
                                  const SizedBox(width: 18),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          suspended && running
                                              ? l.suspended
                                              : controller.busy
                                              ? _stageText(
                                                  context,
                                                  controller.stage,
                                                )
                                              : tunnelReady
                                              ? l.vpnnOn
                                              : running && !safeMode
                                              ? transportState == 'error'
                                                    ? l.vpnnTransportError
                                                    : transportState ==
                                                          'captcha'
                                                    ? l.vpnnCaptcha
                                                    : l.vpnnTransportConnecting
                                              : l.vpnnOff,
                                          style: AppTextStyle.title2.of(
                                            context,
                                          ),
                                        ),
                                        if (vpnnAdminBuild && config != null)
                                          Text(
                                            '${l.vpnnVersion}: ${config.version}',
                                            style: AppTextStyle.footnote
                                                .of(context)
                                                .copyWith(
                                                  color:
                                                      colors.onSurfaceVariant,
                                                ),
                                          ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 24),
                              Text(_stageText(context, controller.stage)),
                              const SizedBox(height: 8),
                              ManagedRouteChoices(controller: controller),
                              if (running && activeProfile != null)
                                Padding(
                                  padding: const EdgeInsets.only(top: 12),
                                  child: Text(
                                    l.vpnnActiveRoute(
                                      managedRouteLabel(context, activeProfile),
                                    ),
                                  ),
                                ),
                              const SizedBox(height: 18),
                              if (vpnnAdminBuild)
                                SwitchListTile(
                                  contentPadding: EdgeInsets.zero,
                                  value: controller.automaticFallback,
                                  onChanged: controller.busy
                                      ? null
                                      : (value) => unawaited(
                                          controller.setAutomaticFallback(
                                            value,
                                          ),
                                        ),
                                  title: Text(l.vpnnAutoFallback),
                                  subtitle: Text(
                                    l.vpnnAutoFallbackHint,
                                    style: AppTextStyle.footnote.of(context),
                                  ),
                                ),
                              if (controller.usedFallback)
                                Text(l.vpnnFallbackUsed),
                              FilledButton.icon(
                                onPressed: controller.busy || running
                                    ? () => unawaited(controller.disconnect())
                                    : safeMode || config == null
                                    ? null
                                    : () {
                                        unawaited(controller.connect());
                                      },
                                icon: GlyphIcon(
                                  controller.busy
                                      ? AppGlyphs.close
                                      : AppGlyphs.vpn,
                                  fill: 1,
                                ),
                                label: Padding(
                                  padding: const EdgeInsets.symmetric(
                                    vertical: 10,
                                  ),
                                  child: Text(
                                    controller.busy
                                        ? l.vpnnCancel
                                        : running
                                        ? l.vpnnDisconnect
                                        : l.vpnnConnect,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 12),
                              Text(
                                safeMode
                                    ? l.vpnnSafe
                                    : config == null
                                    ? l.vpnnNoConfig
                                    : l.vpnnSettingsHint,
                                style: AppTextStyle.footnote
                                    .of(context)
                                    .copyWith(color: colors.onSurfaceVariant),
                              ),
                              if (!running && !safeMode)
                                Padding(
                                  padding: const EdgeInsets.only(top: 12),
                                  child: Text(
                                    l.vpnnUnprotected,
                                    style: AppTextStyle.footnote.of(context),
                                  ),
                                ),
                              if (transportState == 'connecting' ||
                                  transportState == 'ready' ||
                                  transportState == 'connected' ||
                                  transportState == 'error') ...[
                                const SizedBox(height: 12),
                                Text(
                                  transportState == 'connecting'
                                      ? l.vpnnTransportConnecting
                                      : transportState == 'error'
                                      ? l.vpnnTransportError
                                      : l.vpnnTransportReady,
                                  style: AppTextStyle.subheadline.of(context),
                                ),
                              ],
                              if (captcha != null && captcha.isNotEmpty) ...[
                                const SizedBox(height: 16),
                                Text(l.vpnnCaptcha),
                                OutlinedButton(
                                  onPressed: () => _captcha(captcha),
                                  child: Text(l.vpnnOpenCaptcha),
                                ),
                              ],
                              if (running && !safeMode && !suspended) ...[
                                const SizedBox(height: 16),
                                OutlinedButton.icon(
                                  onPressed:
                                      _checking ||
                                          controller.checkingInternet ||
                                          controller.busy
                                      ? null
                                      : _check,
                                  icon: const GlyphIcon(AppGlyphs.target),
                                  label: Text(l.vpnnCheck),
                                ),
                                if (internet != null)
                                  Text(
                                    internet
                                        ? l.vpnnCheckOK
                                        : l.vpnnCheckFailed,
                                    style: AppTextStyle.subheadline
                                        .of(context)
                                        .copyWith(
                                          color: internet
                                              ? colors.primary
                                              : colors.error,
                                        ),
                                  ),
                                Text(
                                  vpnnAdminBuild
                                      ? l.vpnnDiagnosticsHint
                                      : l.vpnnUserDiagnosticsHint,
                                  style: AppTextStyle.footnote
                                      .of(context)
                                      .copyWith(color: colors.onSurfaceVariant),
                                ),
                              ],
                            ],
                          ),
                        ),
                      if (controller.failure != null) ...[
                        const SizedBox(height: 16),
                        _Panel(
                          color: colors.errorContainer,
                          child: Text(
                            _failureText(
                              context,
                              controller.failure!,
                              controller,
                            ),
                            style: TextStyle(color: colors.onErrorContainer),
                          ),
                        ),
                      ],
                      if (controller.usingCache) ...[
                        const SizedBox(height: 16),
                        _Panel(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                l.vpnnCached,
                                style: AppTextStyle.headline.of(context),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                l.vpnnCachedHint,
                                style: AppTextStyle.footnote.of(context),
                              ),
                            ],
                          ),
                        ),
                      ],
                      const SizedBox(height: 24),
                      if (controller.enrollment == null ||
                          controller.failure == ConfigFailure.revoked)
                        _Panel(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                l.vpnnInviteTitle,
                                style: AppTextStyle.title2.of(context),
                              ),
                              const SizedBox(height: 8),
                              Text(l.vpnnInviteHint),
                              const SizedBox(height: 18),
                              TextField(
                                controller: _invitation,
                                maxLines: 3,
                                autocorrect: false,
                                decoration: InputDecoration(
                                  labelText: l.vpnnInviteLabel,
                                  hintText: 'vpnn://enroll?…',
                                ),
                              ),
                              const SizedBox(height: 16),
                              FilledButton(
                                onPressed: controller.busy
                                    ? null
                                    : () => _enroll(controller),
                                child: Text(l.vpnnEnroll),
                              ),
                              OutlinedButton(
                                onPressed: controller.busy
                                    ? null
                                    : () => _importBootstrap(controller),
                                child: Text(l.vpnnImportBootstrap),
                              ),
                              Text(
                                l.vpnnBootstrapHint,
                                style: AppTextStyle.footnote.of(context),
                              ),
                            ],
                          ),
                        )
                      else
                        _Panel(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                vpnnAdminBuild
                                    ? controller
                                          .enrollment!
                                          .endpoints
                                          .first
                                          .host
                                    : l.vpnnHelp,
                                style: AppTextStyle.headline.of(context),
                              ),
                              if (config != null)
                                Text(
                                  '${l.vpnnExpires}: ${MaterialLocalizations.of(context).formatShortDate(config.expiresAt.toLocal())}',
                                  style: AppTextStyle.footnote.of(context),
                                ),
                              const SizedBox(height: 16),
                              OutlinedButton.icon(
                                onPressed: controller.busy
                                    ? null
                                    : () => unawaited(controller.refresh()),
                                icon: const GlyphIcon(AppGlyphs.refresh),
                                label: Text(l.vpnnUpdate),
                              ),
                              OutlinedButton(
                                onPressed: controller.busy
                                    ? null
                                    : () => _importBootstrap(controller),
                                child: Text(l.vpnnImportBootstrap),
                              ),
                              TextButton(
                                onPressed: controller.busy
                                    ? null
                                    : () async {
                                        final result = await dialogs
                                            .showMessage(
                                              message: TextSpan(
                                                text: l.vpnnForgetHint,
                                              ),
                                            );
                                        if (result == true) {
                                          await controller.forget();
                                        }
                                      },
                                child: Text(l.vpnnForget),
                              ),
                            ],
                          ),
                        ),
                      const SizedBox(height: 32),
                      Text(
                        'VPNN $managedClientVersion',
                        style: AppTextStyle.footnote.of(context),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.child, this.color});
  final Widget child;
  final Color? color;
  @override
  Widget build(BuildContext context) => Material(
    color: color ?? Theme.of(context).colorScheme.surfaceContainerLow,
    shape: AppShape.xl,
    child: Padding(padding: const EdgeInsets.all(24), child: child),
  );
}
