import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hoocon_manager/api/client.dart';
import 'package:hoocon_manager/push/push_service.dart';
import 'package:hoocon_manager/state/auth_state.dart';

final badgesControllerProvider =
    ChangeNotifierProvider<BadgesController>((ref) {
  final c = BadgesController(ref);
  ref.onDispose(c.dispose);
  return c;
});

class BadgesController extends ChangeNotifier {
  BadgesController(this._ref);

  final Ref _ref;
  int leadsNew = 0;
  int supportUnread = 0;
  Timer? _timer;
  bool _started = false;
  bool _haveBaseline = false;

  void start() {
    if (_started) return;
    _started = true;
    unawaited(refresh());
    _timer = Timer.periodic(const Duration(seconds: 12), (_) {
      unawaited(refresh());
    });
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    _started = false;
    _haveBaseline = false;
    leadsNew = 0;
    supportUnread = 0;
    notifyListeners();
  }

  Future<void> refresh() async {
    if (_ref.read(authControllerProvider).token == null) return;
    try {
      final data = await _ref.read(apiClientProvider).badges();
      final nextLeads = (data['leads_new'] as num?)?.toInt() ?? 0;
      final nextSupport = (data['support_unread'] as num?)?.toInt() ?? 0;

      final leadsUp = nextLeads > leadsNew;
      final supportUp = nextSupport > supportUnread;
      leadsNew = nextLeads;
      supportUnread = nextSupport;
      notifyListeners();

      // Local sticker alert while app is open (skip first baseline fetch).
      if (_haveBaseline && (leadsUp || supportUp)) {
        final push = _ref.read(pushServiceProvider);
        if (leadsUp) {
          unawaited(
            push.showLocal(
              title: 'Новые заявки',
              body: 'Непросмотренных: $nextLeads',
              deepLink: 'hoocon-manager://leads',
              id: 1001,
            ),
          );
        }
        if (supportUp) {
          unawaited(
            push.showLocal(
              title: 'Чат поддержки',
              body: 'Непрочитанных: $nextSupport',
              deepLink: 'hoocon-manager://chat',
              id: 1002,
            ),
          );
        }
      }
      _haveBaseline = true;
    } catch (e) {
      debugPrint('badges_refresh_failed: $e');
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
