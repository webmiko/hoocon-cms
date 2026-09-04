/// Hub title for a support conversation row from staff API fields.
///
/// Prefers API ``title`` / enriched ``display_name`` (name·company or
/// Пользователь·phone). Never uses channel label («Сайт») as the title.
String conversationPartyTitle(Map<String, dynamic> row) {
  final channel = _s(row['channel_label']);
  final raw = _firstNonEmpty([row['title'], row['display_name']]);
  if (_isUsefulPartyTitle(raw, channel: channel)) {
    return raw;
  }

  final name = _firstNonEmpty([row['visitor_name'], row['name']]);
  final company = _s(row['company']);
  final phone = _s(row['phone']);
  final email = _s(row['contact_email'] ?? row['email']);

  if (name.isNotEmpty &&
      company.isNotEmpty &&
      name.toLowerCase() != company.toLowerCase()) {
    return '$name · $company';
  }
  if (name.isNotEmpty) return name;
  if (company.isNotEmpty) return company;
  if (phone.isNotEmpty) return 'Пользователь · $phone';
  if (email.isNotEmpty) return 'Пользователь · $email';
  return 'Пользователь';
}

String conversationPartySubtitle(Map<String, dynamic> row) {
  final channel = _s(row['channel_label']);
  final email = _s(row['contact_email'] ?? row['email']);
  final phone = _s(row['phone']);
  final title = conversationPartyTitle(row);
  final parts = <String>[
    if (channel.isNotEmpty) channel,
    if (phone.isNotEmpty && !title.contains(phone)) phone,
    if (email.isNotEmpty && !title.contains(email)) email,
  ];
  return parts.join(' · ');
}

/// Parse API id that may arrive as int or num from JSON.
int? asApiId(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value.trim());
  return null;
}

bool _isUsefulPartyTitle(String value, {required String channel}) {
  if (value.isEmpty) return false;
  if (value == channel) return false;
  const channels = {'Сайт', 'Telegram', 'Max', 'Web', 'WEB'};
  if (channels.contains(value)) return false;
  if (value.startsWith('Пользователь · ') &&
      channels.contains(value.substring('Пользователь · '.length))) {
    return false;
  }
  return true;
}

String _s(Object? v) => (v ?? '').toString().trim();

String _firstNonEmpty(List<Object?> values) {
  for (final v in values) {
    final s = _s(v);
    if (s.isNotEmpty) return s;
  }
  return '';
}
