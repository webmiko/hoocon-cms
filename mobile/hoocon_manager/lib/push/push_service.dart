import 'dart:async';
import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hoocon_manager/api/client.dart';
import 'package:hoocon_manager/state/auth_state.dart';

/// Background isolate entry (must be top-level).
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp();
  } catch (_) {}
}

final pushServiceProvider = Provider<PushService>((ref) {
  final service = PushService(ref);
  ref.onDispose(service.dispose);
  return service;
});

class PushService {
  PushService(this._ref);

  final Ref _ref;
  final _local = FlutterLocalNotificationsPlugin();
  bool _ready = false;
  bool firebaseOk = false;
  String? lastError;
  int? deviceId;
  String? fcmToken;
  void Function(String deepLink)? onDeepLink;

  static const _androidChannel = AndroidNotificationChannel(
    'hoocon_staff',
    'Hoocon Manager',
    description: 'Заявки и чат поддержки',
    importance: Importance.high,
  );

  Future<void> init() async {
    if (_ready) return;
    _ready = true;

    const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosInit = DarwinInitializationSettings();
    await _local.initialize(
      settings: const InitializationSettings(android: androidInit, iOS: iosInit),
      onDidReceiveNotificationResponse: (resp) {
        final link = resp.payload;
        if (link != null && link.isNotEmpty) onDeepLink?.call(link);
      },
    );

    final androidPlugin = _local.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    await androidPlugin?.createNotificationChannel(_androidChannel);
    await androidPlugin?.requestNotificationsPermission();

    try {
      await Firebase.initializeApp();
      firebaseOk = true;
      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
      final messaging = FirebaseMessaging.instance;
      await messaging.requestPermission(alert: true, badge: true, sound: true);
      await messaging.setForegroundNotificationPresentationOptions(
        alert: true,
        badge: true,
        sound: true,
      );

      FirebaseMessaging.onMessage.listen(_onForegroundMessage);
      FirebaseMessaging.onMessageOpenedApp.listen(_onOpened);

      final initial = await messaging.getInitialMessage();
      if (initial != null) {
        final link = _deepLinkFrom(initial.data);
        if (link != null) {
          // Defer until router is ready.
          Future<void>.delayed(const Duration(milliseconds: 400), () {
            onDeepLink?.call(link);
          });
        }
      }

      messaging.onTokenRefresh.listen((token) {
        fcmToken = token;
        unawaited(_registerIfLoggedIn(token));
      });
    } catch (e, st) {
      firebaseOk = false;
      lastError = e.toString();
      debugPrint('firebase_init_failed: $e\n$st');
    }
  }

  Future<bool> enablePush() async {
    await init();
    if (!firebaseOk) return false;
    try {
      final token = await FirebaseMessaging.instance.getToken();
      if (token == null || token.isEmpty) {
        lastError = 'FCM token пустой — проверьте google-services.json';
        return false;
      }
      fcmToken = token;
      await _registerIfLoggedIn(token);
      return deviceId != null;
    } catch (e) {
      lastError = e.toString();
      return false;
    }
  }

  Future<void> disablePush() async {
    final id = deviceId;
    deviceId = null;
    fcmToken = null;
    if (id == null) return;
    if (_ref.read(authControllerProvider).token == null) return;
    try {
      await _ref.read(apiClientProvider).unregisterDevice(id);
    } catch (_) {}
  }

  Future<void> syncAfterLogin() async {
    await init();
    if (!firebaseOk) return;
    await enablePush();
  }

  Future<void> showLocal({
    required String title,
    required String body,
    String? deepLink,
    int id = 0,
  }) async {
    await init();
    await _local.show(
      id: id,
      title: title,
      body: body,
      notificationDetails: NotificationDetails(
        android: AndroidNotificationDetails(
          _androidChannel.id,
          _androidChannel.name,
          channelDescription: _androidChannel.description,
          importance: Importance.high,
          priority: Priority.high,
          icon: '@mipmap/ic_launcher',
        ),
        iOS: const DarwinNotificationDetails(),
      ),
      payload: deepLink,
    );
  }

  Future<void> _registerIfLoggedIn(String token) async {
    if (_ref.read(authControllerProvider).token == null) return;
    final platform = Platform.isIOS ? 'ios' : 'android';
    try {
      final data = await _ref.read(apiClientProvider).registerDevice(
            token,
            platform: platform,
          );
      deviceId = data['id'] as int?;
      lastError = null;
    } catch (e) {
      lastError = e.toString();
      debugPrint('device_register_failed: $e');
    }
  }

  void _onForegroundMessage(RemoteMessage message) {
    final n = message.notification;
    final title = n?.title ?? _titleFromData(message.data);
    final body = n?.body ?? _bodyFromData(message.data);
    if (title.isEmpty && body.isEmpty) return;
    unawaited(
      showLocal(
        title: title.isEmpty ? 'Hoocon' : title,
        body: body,
        deepLink: _deepLinkFrom(message.data),
        id: message.hashCode,
      ),
    );
  }

  void _onOpened(RemoteMessage message) {
    final link = _deepLinkFrom(message.data);
    if (link != null) onDeepLink?.call(link);
  }

  String? _deepLinkFrom(Map<String, dynamic> data) {
    final link = data['deep_link']?.toString();
    if (link != null && link.isNotEmpty) return link;
    final type = data['type']?.toString();
    if (type == 'support') {
      final id = data['conversation_id']?.toString();
      if (id != null) return 'hoocon-manager://conversation/$id';
    }
    if (type == 'lead') {
      final id = data['lead_id']?.toString();
      if (id != null) return 'hoocon-manager://lead/$id';
    }
    return null;
  }

  String _titleFromData(Map<String, dynamic> data) {
    final type = data['type']?.toString();
    if (type == 'support') return 'Новое сообщение в поддержке';
    if (type == 'lead') return 'Новая заявка';
    return 'Hoocon';
  }

  String _bodyFromData(Map<String, dynamic> data) {
    return data['body']?.toString() ?? '';
  }

  void dispose() {}
}
