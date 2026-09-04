import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hoocon_manager/api/client.dart';
import 'package:hoocon_manager/features/chat/party_label.dart';
import 'package:hoocon_manager/state/badges_state.dart';
import 'package:hoocon_manager/theme.dart';

class ChatThreadScreen extends ConsumerStatefulWidget {
  const ChatThreadScreen({super.key, required this.id});

  final int id;

  @override
  ConsumerState<ChatThreadScreen> createState() => _ChatThreadScreenState();
}

class _ChatThreadScreenState extends ConsumerState<ChatThreadScreen> {
  final _ctrl = TextEditingController();
  final _messages = <Map<String, dynamic>>[];
  Timer? _poll;
  bool _sending = false;
  String _title = 'Диалог';

  @override
  void initState() {
    super.initState();
    _loadMeta();
    _load();
    _poll = Timer.periodic(const Duration(seconds: 4), (_) => _pollNew());
    ref.read(apiClientProvider).markRead(widget.id).then((_) {
      ref.read(badgesControllerProvider).refresh();
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _loadMeta() async {
    final api = ref.read(apiClientProvider);
    try {
      final row = Map<String, dynamic>.from(await api.conversation(widget.id));
      await _enrichFromLinks(api, row);
      if (!mounted) return;
      setState(() => _title = conversationPartyTitle(row));
    } catch (_) {
      // Older API without GET /conversations/{id}/ — keep fallback title.
    }
  }

  Future<void> _enrichFromLinks(
    StaffApiClient api,
    Map<String, dynamic> row,
  ) async {
    if (_s(row['company']).isNotEmpty || _s(row['phone']).isNotEmpty) {
      return;
    }
    final title = conversationPartyTitle(row);
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
    } catch (_) {}
  }

  String _s(Object? v) => (v ?? '').toString().trim();

  Future<void> _load() async {
    final rows = await ref.read(apiClientProvider).messages(widget.id);
    setState(() {
      _messages
        ..clear()
        ..addAll(rows.map((e) => Map<String, dynamic>.from(e as Map)));
    });
  }

  Future<void> _pollNew() async {
    final after = _messages.isEmpty ? null : _messages.last['id'] as int?;
    final rows =
        await ref.read(apiClientProvider).messages(widget.id, after: after);
    if (rows.isEmpty || !mounted) return;
    setState(() {
      _messages.addAll(rows.map((e) => Map<String, dynamic>.from(e as Map)));
    });
  }

  Future<void> _send() async {
    final text = _ctrl.text.trim();
    if (text.isEmpty) return;
    setState(() => _sending = true);
    try {
      final msg = await ref.read(apiClientProvider).reply(widget.id, text);
      _ctrl.clear();
      setState(() => _messages.add(msg));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_title)),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (context, i) {
                final m = _messages[i];
                final mine = m['direction'] == 'outbound';
                return Align(
                  alignment:
                      mine ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 8,
                    ),
                    constraints: BoxConstraints(
                      maxWidth: MediaQuery.sizeOf(context).width * 0.78,
                    ),
                    decoration: BoxDecoration(
                      color: mine ? hooconRed : const Color(0xFFF0F0F0),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      m['body']?.toString() ?? '',
                      style: TextStyle(
                        color: mine ? Colors.white : Colors.black87,
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _ctrl,
                      decoration: const InputDecoration(hintText: 'Ответ…'),
                      minLines: 1,
                      maxLines: 4,
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _sending ? null : _send,
                    icon: const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
