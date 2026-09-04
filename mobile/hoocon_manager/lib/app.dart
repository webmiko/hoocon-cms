import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:hoocon_manager/features/auth/login_screen.dart';
import 'package:hoocon_manager/features/chat/chat_thread_screen.dart';
import 'package:hoocon_manager/features/crm/client_detail_screen.dart';
import 'package:hoocon_manager/features/leads/lead_detail_screen.dart';
import 'package:hoocon_manager/features/shell/home_shell.dart';
import 'package:hoocon_manager/push/push_service.dart';
import 'package:hoocon_manager/state/auth_state.dart';
import 'package:hoocon_manager/theme.dart';

final _routerProvider = Provider<GoRouter>((ref) {
  // read, not watch — recreating GoRouter resets navigation.
  final auth = ref.read(authControllerProvider);
  final router = GoRouter(
    initialLocation: '/login',
    refreshListenable: auth,
    redirect: (context, state) {
      final loggedIn = auth.token != null;
      final loc = state.matchedLocation;
      if (loggedIn) {
        if (loc == '/login' || loc == '/otp') return '/leads';
        return null;
      }
      // OTP is in-place on LoginScreen; keep user on /login.
      if (loc == '/otp') return '/login';
      if (loc != '/login') return '/login';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      // Legacy deep link → same login flow (OTP step is state-driven).
      GoRoute(path: '/otp', builder: (_, __) => const LoginScreen()),
      GoRoute(
        path: '/leads/:id',
        builder: (_, state) =>
            LeadDetailScreen(id: int.parse(state.pathParameters['id']!)),
      ),
      GoRoute(
        path: '/conversations/:id',
        builder: (_, state) =>
            ChatThreadScreen(id: int.parse(state.pathParameters['id']!)),
      ),
      GoRoute(
        path: '/clients/:id',
        builder: (_, state) =>
            ClientDetailScreen(id: int.parse(state.pathParameters['id']!)),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            HomeShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(path: '/leads', builder: (_, __) => const LeadsTab()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/chat', builder: (_, __) => const ChatTab()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/clients', builder: (_, __) => const ClientsTab()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/more', builder: (_, __) => const MoreTab()),
          ]),
        ],
      ),
    ],
  );

  // Wire FCM / local notification taps → routes.
  ref.read(pushServiceProvider).onDeepLink = (link) {
    final path = _pathFromDeepLink(link);
    if (path != null) router.go(path);
  };

  ref.onDispose(router.dispose);
  return router;
});

String? _pathFromDeepLink(String link) {
  final uri = Uri.tryParse(link);
  if (uri == null) return null;
  if (uri.scheme == 'hoocon-manager') {
    final host = uri.host;
    final id = uri.pathSegments.isNotEmpty ? uri.pathSegments.first : '';
    if (host == 'lead' && id.isNotEmpty) return '/leads/$id';
    if (host == 'conversation' && id.isNotEmpty) return '/conversations/$id';
    if (host == 'leads' || host == 'chat') return '/$host';
  }
  if (link.startsWith('/')) return link;
  return null;
}

class HooconManagerApp extends ConsumerWidget {
  const HooconManagerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(_routerProvider);
    return MaterialApp.router(
      title: 'Hoocon Manager',
      theme: hooconTheme,
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}
