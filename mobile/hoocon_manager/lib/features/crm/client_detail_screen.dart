import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hoocon_manager/api/client.dart';
import 'package:hoocon_manager/theme.dart';

class ClientDetailScreen extends ConsumerStatefulWidget {
  const ClientDetailScreen({super.key, required this.id});

  final int id;

  @override
  ConsumerState<ClientDetailScreen> createState() => _ClientDetailScreenState();
}

class _ClientDetailScreenState extends ConsumerState<ClientDetailScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = ref.read(apiClientProvider).client(widget.id);
  }

  Future<void> _composeEmail() async {
    final subject = TextEditingController();
    final body = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Письмо клиенту'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: subject, decoration: const InputDecoration(labelText: 'Тема')),
            TextField(
              controller: body,
              decoration: const InputDecoration(labelText: 'Текст'),
              minLines: 3,
              maxLines: 6,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Отмена')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Отправить')),
        ],
      ),
    );
    if (ok != true) return;
    await ref.read(apiClientProvider).sendEmail(
          widget.id,
          subject: subject.text.trim(),
          body: body.text.trim(),
        );
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Письмо поставлено в очередь')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Клиент'),
        actions: [
          IconButton(
            onPressed: _composeEmail,
            icon: const Icon(Icons.email_outlined),
            tooltip: 'Написать',
          ),
        ],
      ),
      body: FutureBuilder(
        future: _future,
        builder: (context, snap) {
          if (!snap.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final c = snap.data!;
          final activities = (c['activities'] as List?) ?? [];
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(c['name']?.toString() ?? '', style: Theme.of(context).textTheme.titleLarge),
              Text(c['email']?.toString() ?? '', style: const TextStyle(color: hooconMuted)),
              Text(c['phone']?.toString() ?? ''),
              Text(c['company']?.toString() ?? ''),
              const SizedBox(height: 24),
              const Text('Активности', style: TextStyle(fontWeight: FontWeight.w600)),
              ...activities.map((a) {
                final row = Map<String, dynamic>.from(a as Map);
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(row['subject']?.toString().isNotEmpty == true
                      ? row['subject'].toString()
                      : row['activity_type']?.toString() ?? ''),
                  subtitle: Text(row['body']?.toString() ?? ''),
                );
              }),
            ],
          );
        },
      ),
    );
  }
}
