import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hoocon_manager/api/client.dart';
import 'package:hoocon_manager/theme.dart';

class LeadDetailScreen extends ConsumerStatefulWidget {
  const LeadDetailScreen({super.key, required this.id});

  final int id;

  @override
  ConsumerState<LeadDetailScreen> createState() => _LeadDetailScreenState();
}

class _LeadDetailScreenState extends ConsumerState<LeadDetailScreen> {
  late Future<Map<String, dynamic>> _future;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _future = ref.read(apiClientProvider).lead(widget.id);
  }

  Future<void> _reload() async {
    setState(() => _future = ref.read(apiClientProvider).lead(widget.id));
    await _future;
  }

  Future<void> _take() async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).takeLead(widget.id);
      await _reload();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _done() async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).setLeadStatus(widget.id, 'done');
      await _reload();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Заявка #${widget.id}')),
      body: FutureBuilder(
        future: _future,
        builder: (context, snap) {
          if (!snap.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final lead = snap.data!;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                lead['status_label']?.toString() ?? '',
                style: const TextStyle(color: hooconAccent, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              Text(lead['name']?.toString() ?? '',
                  style: Theme.of(context).textTheme.titleLarge),
              Text(lead['company']?.toString() ?? '', style: const TextStyle(color: hooconMuted)),
              const SizedBox(height: 16),
              Text(lead['email']?.toString() ?? ''),
              Text(lead['phone']?.toString() ?? ''),
              const SizedBox(height: 16),
              Text(lead['message']?.toString() ?? ''),
              const SizedBox(height: 80),
            ],
          );
        },
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _busy ? null : _take,
                  child: const Text('Взять в работу'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  onPressed: _busy ? null : _done,
                  child: const Text('Завершить'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
