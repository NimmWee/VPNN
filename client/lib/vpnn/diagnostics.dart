enum ConnectionStage {
  idle,
  settings,
  selecting,
  systemTunnel,
  transport,
  captcha,
  checking,
  ready,
  failed,
}

const diagnosticCounterKeys = {
  'dnsTxPackets',
  'dnsRxPackets',
  'dnsTxBytes',
  'dnsRxBytes',
  'dnsResends',
  'dnsWriteErrors',
  'dnsRxDropped',
  'dnsUploadMTU',
  'dnsDownloadMTU',
  'dnsWindow',
  'dnsDuplication',
  'vkTxBytes',
  'vkRxBytes',
  'vkStreams',
  'vkTotal',
};

Map<String, int> safeDiagnosticCounters(Object? value) {
  if (value is! Map) return const {};
  return {
    for (final key in diagnosticCounterKeys)
      if (value[key] case final int count when count >= 0) key: count,
  };
}
