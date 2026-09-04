import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Production API base. Override at build: `--dart-define=API_BASE=…`
const kApiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'https://hoocon.ru/api/staff',
);

final secureStorageProvider = Provider((_) {
  return const FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
  );
});

final apiClientProvider = Provider<StaffApiClient>((ref) {
  return StaffApiClient(ref);
});

class StaffApiClient {
  StaffApiClient(this._ref) {
    _dio = Dio(
      BaseOptions(
        baseUrl: kApiBase,
        connectTimeout: const Duration(seconds: 20),
        receiveTimeout: const Duration(seconds: 30),
        headers: {'Accept': 'application/json'},
      ),
    );
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _ref.read(secureStorageProvider).read(key: 'token');
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Token $token';
          }
          handler.next(options);
        },
      ),
    );
  }

  final Ref _ref;
  late final Dio _dio;

  /// Human message from Dio/API errors for UI.
  static String errorMessage(Object error, {String fallback = 'Ошибка запроса'}) {
    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map && data['detail'] != null) {
        return data['detail'].toString();
      }
      if (data is Map && data['login'] is List && (data['login'] as List).isNotEmpty) {
        return (data['login'] as List).first.toString();
      }
      if (error.type == DioExceptionType.connectionTimeout ||
          error.type == DioExceptionType.receiveTimeout ||
          error.type == DioExceptionType.connectionError) {
        return 'Нет связи с сервером';
      }
    }
    return fallback;
  }

  Future<Map<String, dynamic>> otpStart(String login) async {
    final res = await _dio.post('/auth/otp/start/', data: {'login': login});
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> otpVerify(String challengeId, String code) async {
    final res = await _dio.post(
      '/auth/otp/verify/',
      data: {'challenge_id': challengeId, 'code': code},
    );
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<void> logout() async {
    try {
      await _dio.post('/auth/logout/');
    } catch (_) {}
  }

  Future<Map<String, dynamic>> me() async {
    final res = await _dio.get('/me/');
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> badges() async {
    final res = await _dio.get('/badges/');
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> leads({String? status}) async {
    final res = await _dio.get(
      '/leads/',
      queryParameters: {if (status != null && status.isNotEmpty) 'status': status},
    );
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> lead(int id) async {
    final res = await _dio.get('/leads/$id/');
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> takeLead(int id) async {
    final res = await _dio.post('/leads/$id/take/');
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> setLeadStatus(int id, String status) async {
    final res = await _dio.post('/leads/$id/status/', data: {'status': status});
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> clients({String? q}) async {
    final res = await _dio.get(
      '/clients/',
      queryParameters: {if (q != null && q.isNotEmpty) 'q': q},
    );
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> client(int id) async {
    final res = await _dio.get('/clients/$id/');
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> sendEmail(
    int clientId, {
    required String subject,
    required String body,
  }) async {
    final res = await _dio.post(
      '/clients/$clientId/emails/',
      data: {'subject': subject, 'body': body, 'send_now': true},
    );
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> conversations() async {
    final res = await _dio.get('/conversations/');
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<Map<String, dynamic>> conversation(int id) async {
    final res = await _dio.get('/conversations/$id/');
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<List<dynamic>> messages(int id, {int? after}) async {
    final res = await _dio.get(
      '/conversations/$id/messages/',
      queryParameters: {if (after != null) 'after': after},
    );
    return List<dynamic>.from(res.data as List);
  }

  Future<Map<String, dynamic>> reply(int id, String body) async {
    final res = await _dio.post(
      '/conversations/$id/messages/',
      data: {'body': body},
    );
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<void> markRead(int id) async {
    await _dio.post('/conversations/$id/read/');
  }

  Future<void> deleteConversation(int id) async {
    await _dio.delete('/conversations/$id/');
  }

  Future<Map<String, dynamic>> registerDevice(
    String fcmToken, {
    String platform = 'android',
  }) async {
    final res = await _dio.post(
      '/devices/',
      data: {'fcm_token': fcmToken, 'platform': platform},
    );
    return Map<String, dynamic>.from(res.data as Map);
  }

  Future<void> unregisterDevice(int id) async {
    await _dio.delete('/devices/$id/');
  }
}
