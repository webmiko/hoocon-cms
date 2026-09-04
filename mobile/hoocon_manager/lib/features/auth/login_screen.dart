import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hoocon_manager/api/client.dart';
import 'package:hoocon_manager/state/auth_state.dart';
import 'package:hoocon_manager/theme.dart';

/// Login + OTP on one route so go_router cannot drop the code step.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _loginCtrl = TextEditingController();
  final _otpCtrl = TextEditingController();
  final _loginFocus = FocusNode();
  final _otpFocus = FocusNode();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final auth = ref.read(authControllerProvider);
      if (auth.challengeId != null) {
        _otpFocus.requestFocus();
      } else {
        _loginFocus.requestFocus();
      }
    });
  }

  @override
  void dispose() {
    _loginFocus.dispose();
    _otpFocus.dispose();
    _loginCtrl.dispose();
    _otpCtrl.dispose();
    super.dispose();
  }

  Future<void> _requestCode() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(authControllerProvider).startOtp(_loginCtrl.text);
      if (!mounted) return;
      _otpCtrl.clear();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _otpFocus.requestFocus();
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = StaffApiClient.errorMessage(
            e,
            fallback: 'Не удалось отправить код',
          );
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verifyCode() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(authControllerProvider).verifyOtp(_otpCtrl.text);
      // redirect → /leads via auth.token + refreshListenable
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = StaffApiClient.errorMessage(
            e,
            fallback: 'Неверный или просроченный код',
          );
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _backToLogin() {
    ref.read(authControllerProvider).clearChallenge();
    _otpCtrl.clear();
    setState(() => _error = null);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _loginFocus.requestFocus();
    });
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final awaitingOtp =
        auth.challengeId != null && auth.challengeId!.isNotEmpty;

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 48),
              Text(
                'Hoocon',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: hooconInk,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                awaitingOtp ? 'Введите код из письма' : 'Вход для менеджеров',
                style: const TextStyle(color: hooconMuted),
              ),
              const SizedBox(height: 32),
              if (!awaitingOtp) ...[
                TextField(
                  controller: _loginCtrl,
                  focusNode: _loginFocus,
                  autofocus: true,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.done,
                  autofillHints: const [
                    AutofillHints.username,
                    AutofillHints.email,
                  ],
                  enableSuggestions: false,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: 'Email или логин',
                  ),
                  onSubmitted: (_) {
                    if (!_busy) _requestCode();
                  },
                ),
              ] else ...[
                Text(
                  'Код отправлен на ${auth.emailMasked ?? "почту"}',
                  style: const TextStyle(color: hooconMuted),
                ),
                const SizedBox(height: 16),
                TextField(
                  key: const ValueKey('otp-field'),
                  controller: _otpCtrl,
                  focusNode: _otpFocus,
                  autofocus: true,
                  keyboardType: TextInputType.number,
                  textInputAction: TextInputAction.done,
                  maxLength: 6,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  autofillHints: const [AutofillHints.oneTimeCode],
                  enableSuggestions: false,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: '6 цифр',
                    counterText: '',
                  ),
                  onSubmitted: (_) {
                    if (!_busy) _verifyCode();
                  },
                ),
                TextButton(
                  onPressed: _busy ? null : _backToLogin,
                  child: const Text('Другой email'),
                ),
              ],
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!, style: const TextStyle(color: Colors.red)),
              ],
              const Spacer(),
              FilledButton(
                onPressed: _busy
                    ? null
                    : (awaitingOtp ? _verifyCode : _requestCode),
                child: _busy
                    ? const SizedBox(
                        height: 22,
                        width: 22,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(awaitingOtp ? 'Войти' : 'Получить код'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
