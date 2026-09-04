import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hoocon_manager/api/client.dart';
import 'package:hoocon_manager/push/push_service.dart';
import 'package:hoocon_manager/state/badges_state.dart';

final authControllerProvider = ChangeNotifierProvider<AuthController>((ref) {
  final c = AuthController(ref);
  c.bootstrap();
  return c;
});

class AuthController extends ChangeNotifier {
  AuthController(this._ref);

  final Ref _ref;
  String? token;
  String? challengeId;
  String? emailMasked;
  Map<String, dynamic>? user;
  String? pendingLogin;

  Future<void> bootstrap() async {
    try {
      token = await _ref.read(secureStorageProvider).read(key: 'token');
    } catch (e, st) {
      // EncryptedSharedPreferences can fail on some Android installs.
      debugPrint('secure_storage_read_failed: $e\n$st');
      token = null;
    }
    if (token != null) {
      try {
        user = await _ref.read(apiClientProvider).me();
        _ref.read(badgesControllerProvider).start();
        unawaited(_ref.read(pushServiceProvider).syncAfterLogin());
      } catch (_) {
        await logout();
      }
    }
    notifyListeners();
  }

  Future<void> startOtp(String login) async {
    pendingLogin = login.trim();
    final data = await _ref.read(apiClientProvider).otpStart(pendingLogin!);
    challengeId = data['challenge_id'] as String?;
    emailMasked = data['email_masked'] as String?;
    notifyListeners();
  }

  void clearChallenge() {
    challengeId = null;
    emailMasked = null;
    notifyListeners();
  }

  Future<void> verifyOtp(String code) async {
    final id = challengeId;
    if (id == null) throw StateError('Нет challenge_id');
    final data = await _ref.read(apiClientProvider).otpVerify(id, code.trim());
    token = data['token'] as String?;
    user = Map<String, dynamic>.from(data['user'] as Map);
    challengeId = null;
    try {
      await _ref.read(secureStorageProvider).write(key: 'token', value: token);
    } catch (e, st) {
      debugPrint('secure_storage_write_failed: $e\n$st');
      // Keep session in memory even if disk write fails.
    }
    notifyListeners();
    // Stickers + FCM registration after successful login.
    _ref.read(badgesControllerProvider).start();
    unawaited(_ref.read(pushServiceProvider).syncAfterLogin());
  }

  Future<void> logout() async {
    try {
      await _ref.read(pushServiceProvider).disablePush();
    } catch (_) {}
    _ref.read(badgesControllerProvider).stop();
    try {
      await _ref.read(apiClientProvider).logout();
    } catch (_) {}
    token = null;
    user = null;
    challengeId = null;
    try {
      await _ref.read(secureStorageProvider).delete(key: 'token');
    } catch (_) {}
    notifyListeners();
  }
}
