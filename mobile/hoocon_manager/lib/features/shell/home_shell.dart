import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:hoocon_manager/api/client.dart';
import 'package:hoocon_manager/features/chat/party_label.dart';
import 'package:hoocon_manager/push/push_service.dart';
import 'package:hoocon_manager/state/auth_state.dart';
import 'package:hoocon_manager/state/badges_state.dart';
import 'package:hoocon_manager/theme.dart';

class HomeShell extends ConsumerWidget {
  const HomeShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final badges = ref.watch(badgesControllerProvider);
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: (i) {
          navigationShell.goBranch(i);
          ref.read(badgesControllerProvider).refresh();
        },
        destinations: [
          NavigationDestination(
            icon: _NavBadge(
              count: badges.leadsNew,
              child: const Icon(Icons.inbox_outlined),
            ),
            selectedIcon: _NavBadge(
              count: badges.leadsNew,
              child: const Icon(Icons.inbox),
            ),
            label: 'Заявки',
          ),
          NavigationDestination(
            icon: _NavBadge(
              count: badges.supportUnread,
              child: const Icon(Icons.chat_bubble_outline),
            ),
            selectedIcon: _NavBadge(
              count: badges.supportUnread,
              child: const Icon(Icons.chat_bubble),
            ),
            label: 'Чат',
          ),
          const NavigationDestination(
            icon: Icon(Icons.people_outline),
            label: 'Клиенты',
          ),
          const NavigationDestination(
            icon: Icon(Icons.more_horiz),
            label: 'Ещё',
          ),
        ],
      ),
    );
  }
}

class _NavBadge extends StatelessWidget {
  const _NavBadge({required this.count, required this.child});

  final int count;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (count <= 0) return child;
    final label = count > 99 ? '99+' : '$count';
    return Badge(
      backgroundColor: hooconRed,
      label: Text(label),
      child: child,
    );
  }
}

class LeadsTab extends ConsumerStatefulWidget {
  const LeadsTab({super.key});

  @override
  ConsumerState<LeadsTab> createState() => _LeadsTabState();
}

class _LeadsTabState extends ConsumerState<LeadsTab> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = ref.read(apiClientProvider).leads();
  }

  Future<void> _reload() async {
    setState(() {
      _future = ref.read(apiClientProvider).leads();
    });
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Заявки')),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: FutureBuilder(
          future: _future,
          builder: (context, snap) {
            if (!snap.hasData) {
              return const Center(child: CircularProgressIndicator());
            }
            final results = (snap.data!['results'] as List?) ?? [];
            if (results.isEmpty) {
              return ListView(
                children: const [
                  SizedBox(height: 120),
                  Center(child: Text('Нет заявок', style: TextStyle(color: hooconMuted))),
                ],
              );
            }
            return ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: results.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (context, i) {
                final row = Map<String, dynamic>.from(results[i] as Map);
                return Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    title: Text(row['name']?.toString() ?? ''),
                    subtitle: Text(
                      '${row['status_label'] ?? ''} · ${row['company'] ?? row['email'] ?? ''}',
                    ),
                    onTap: () => context.push('/leads/${row['id']}'),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class ChatTab extends ConsumerStatefulWidget {
  const ChatTab({super.key});

  @override
  ConsumerState<ChatTab> createState() => _ChatTabState();
}

class _ChatTabState extends ConsumerState<ChatTab> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() async {
    final api = ref.read(apiClientProvider);
    final page = await api.conversations();
    final results = (page['results'] as List?) ?? [];
    final rows = [
      for (final item in results) Map<String, dynamic>.from(item as Map),
    ];
    // Until API party fields are live, fill name/company/phone from CRM/lead.
    await Future.wait(rows.map((row) => _enrichPartyFields(api, row)));
    return rows;
  }

  Future<void> _enrichPartyFields(
    StaffApiClient api,
    Map<String, dynamic> row,
  ) async {
    if (_s(row['company']).isNotEmpty || _s(row['phone']).isNotEmpty) {
      return;
    }
    final title = conversationPartyTitle(row);
    // Only fetch CRM/lead when the hub title is still anonymous/empty.
    if (title != 'Пользователь' && !title.startsWith('Пользователь · ')) {
      return;
    }
    final clientId = asApiId(row['client_id']);
    final leadId = asApiId(row['lead_id']);
    try {
      if (clientId != null) {
        final c = await api.client(clientId);
        row['visitor_name'] = _s(c['name']);
        row['company'] = _s(c['company']);
        row['phone'] = _s(c['phone']);
        row['contact_email'] = _s(c['email']);
      } else if (leadId != null) {
        final l = await api.lead(leadId);
        row['visitor_name'] = _s(l['name']);
        row['company'] = _s(l['company']);
        row['phone'] = _s(l['phone']);
        row['contact_email'] = _s(l['email']);
      }
    } catch (_) {
      // Keep row as-is if CRM/lead fetch fails.
    }
  }

  String _s(Object? v) => (v ?? '').toString().trim();

  Future<void> _reload() async {
    setState(() => _future = _load());
    await _future;
  }

  bool _isDeletable(Map<String, dynamic> row) {
    if (row['deletable'] == true) return true;
    // Older API without ``deletable``: allow when no CRM client link.
    return row['client_id'] == null;
  }

  Future<void> _confirmDelete(Map<String, dynamic> row) async {
    final title = conversationPartyTitle(row);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Удалить диалог?'),
        content: Text(
          '«$title» будет удалён безвозвратно.\n'
          'Диалоги с клиентом CRM удалить нельзя.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Удалить'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final id = asApiId(row['id']);
    if (id == null) return;
    try {
      await ref.read(apiClientProvider).deleteConversation(id);
      await _reload();
      if (!mounted) return;
      ref.read(badgesControllerProvider).refresh();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Диалог удалён')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            StaffApiClient.errorMessage(e, fallback: 'Не удалось удалить'),
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Чат поддержки')),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: FutureBuilder(
          future: _future,
          builder: (context, snap) {
            if (snap.hasError) {
              return ListView(
                children: [
                  const SizedBox(height: 80),
                  Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      StaffApiClient.errorMessage(
                        snap.error!,
                        fallback: 'Не удалось загрузить чаты',
                      ),
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.red),
                    ),
                  ),
                ],
              );
            }
            if (!snap.hasData) {
              return const Center(child: CircularProgressIndicator());
            }
            final results = snap.data!;
            if (results.isEmpty) {
              return ListView(
                children: const [
                  SizedBox(height: 120),
                  Center(
                    child: Text(
                      'Нет диалогов',
                      style: TextStyle(color: hooconMuted),
                    ),
                  ),
                ],
              );
            }
            return ListView.builder(
              itemCount: results.length,
              itemBuilder: (context, i) {
                final row = results[i];
                final unread = row['staff_unread_count'] as int? ?? 0;
                final title = conversationPartyTitle(row);
                final subtitle = conversationPartySubtitle(row);
                final deletable = _isDeletable(row);
                final tile = ListTile(
                  title: Text(title),
                  subtitle: subtitle.isEmpty ? null : Text(subtitle),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (unread > 0) Badge(label: Text('$unread')),
                      if (deletable)
                        IconButton(
                          tooltip: 'Удалить',
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () => _confirmDelete(row),
                        ),
                    ],
                  ),
                  onTap: () => context.push('/conversations/${row['id']}'),
                  onLongPress: deletable ? () => _confirmDelete(row) : null,
                );
                if (!deletable) return tile;
                return Dismissible(
                  key: ValueKey('conv-${row['id']}'),
                  direction: DismissDirection.endToStart,
                  confirmDismiss: (_) async {
                    await _confirmDelete(row);
                    return false; // reload handles removal
                  },
                  background: Container(
                    alignment: Alignment.centerRight,
                    padding: const EdgeInsets.only(right: 20),
                    color: hooconRed,
                    child: const Icon(Icons.delete, color: Colors.white),
                  ),
                  child: tile,
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class ClientsTab extends ConsumerStatefulWidget {
  const ClientsTab({super.key});

  @override
  ConsumerState<ClientsTab> createState() => _ClientsTabState();
}

class _ClientsTabState extends ConsumerState<ClientsTab> {
  final _q = TextEditingController();
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = ref.read(apiClientProvider).clients();
  }

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  void _search() {
    setState(() {
      _future = ref.read(apiClientProvider).clients(q: _q.text.trim());
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Клиенты')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              controller: _q,
              decoration: InputDecoration(
                labelText: 'Поиск',
                suffixIcon: IconButton(
                  icon: const Icon(Icons.search),
                  onPressed: _search,
                ),
              ),
              onSubmitted: (_) => _search(),
            ),
          ),
          Expanded(
            child: FutureBuilder(
              future: _future,
              builder: (context, snap) {
                if (!snap.hasData) {
                  return const Center(child: CircularProgressIndicator());
                }
                final results = (snap.data!['results'] as List?) ?? [];
                return ListView.builder(
                  itemCount: results.length,
                  itemBuilder: (context, i) {
                    final row = Map<String, dynamic>.from(results[i] as Map);
                    return ListTile(
                      title: Text(row['name']?.toString() ?? row['email']?.toString() ?? ''),
                      subtitle: Text(row['email']?.toString() ?? ''),
                      onTap: () => context.push('/clients/${row['id']}'),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class MoreTab extends ConsumerStatefulWidget {
  const MoreTab({super.key});

  @override
  ConsumerState<MoreTab> createState() => _MoreTabState();
}

class _MoreTabState extends ConsumerState<MoreTab> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final push = ref.watch(pushServiceProvider);
    final badges = ref.watch(badgesControllerProvider);
    final user = auth.user;
    final pushOn = push.deviceId != null;
    return Scaffold(
      appBar: AppBar(title: const Text('Ещё')),
      body: ListView(
        children: [
          ListTile(
            title: Text(user?['display_name']?.toString() ?? ''),
            subtitle: Text(user?['email']?.toString() ?? ''),
          ),
          ListTile(
            title: const Text('Стикеры'),
            subtitle: Text(
              'Заявки: ${badges.leadsNew} · Чат: ${badges.supportUnread}',
            ),
            trailing: IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: () => ref.read(badgesControllerProvider).refresh(),
            ),
          ),
          SwitchListTile(
            secondary: const Icon(Icons.notifications_outlined),
            title: const Text('Push-уведомления'),
            subtitle: Text(
              push.firebaseOk
                  ? (pushOn
                      ? 'FCM включён'
                      : (push.lastError ?? 'Выключены'))
                  : 'Нужен реальный google-services.json (см. DISTRIBUTE.md)',
            ),
            value: pushOn,
            onChanged: _busy
                ? null
                : (v) async {
                    setState(() => _busy = true);
                    try {
                      final messenger = ScaffoldMessenger.of(context);
                      if (v) {
                        final ok =
                            await ref.read(pushServiceProvider).enablePush();
                        if (!ok && mounted) {
                          messenger.showSnackBar(
                            SnackBar(
                              content: Text(
                                ref.read(pushServiceProvider).lastError ??
                                    'Не удалось включить push',
                              ),
                            ),
                          );
                        }
                      } else {
                        await ref.read(pushServiceProvider).disablePush();
                      }
                    } finally {
                      if (mounted) setState(() => _busy = false);
                    }
                  },
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.logout),
            title: const Text('Выйти'),
            onTap: () async {
              await ref.read(authControllerProvider).logout();
              if (context.mounted) context.go('/login');
            },
          ),
        ],
      ),
    );
  }
}
