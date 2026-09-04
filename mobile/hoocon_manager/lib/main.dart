import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hoocon_manager/app.dart';
import 'package:hoocon_manager/push/push_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: _Bootstrap()));
}

class _Bootstrap extends ConsumerStatefulWidget {
  const _Bootstrap();

  @override
  ConsumerState<_Bootstrap> createState() => _BootstrapState();
}

class _BootstrapState extends ConsumerState<_Bootstrap> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await ref.read(pushServiceProvider).init();
    });
  }

  @override
  Widget build(BuildContext context) => const HooconManagerApp();
}
