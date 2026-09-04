import 'package:flutter_test/flutter_test.dart';
import 'package:hoocon_manager/features/chat/party_label.dart';

void main() {
  test('party title never uses channel Сайт as identity', () {
    expect(
      conversationPartyTitle({
        'display_name': '',
        'channel_label': 'Сайт',
      }),
      'Пользователь',
    );
    expect(
      conversationPartyTitle({
        'display_name': 'Сайт',
        'channel_label': 'Сайт',
      }),
      'Пользователь',
    );
    expect(
      conversationPartyTitle({
        'title': 'Пётр · АО Ветер',
        'channel_label': 'Сайт',
      }),
      'Пётр · АО Ветер',
    );
    expect(
      conversationPartyTitle({
        'visitor_name': '',
        'phone': '+79001112233',
        'channel_label': 'Сайт',
      }),
      'Пользователь · +79001112233',
    );
  });

  test('subtitle keeps channel once without duplicating phone', () {
    expect(
      conversationPartySubtitle({
        'title': 'Пользователь · +79001112233',
        'phone': '+79001112233',
        'channel_label': 'Сайт',
      }),
      'Сайт',
    );
  });

  test('asApiId accepts int num and string', () {
    expect(asApiId(12), 12);
    expect(asApiId(12.0), 12);
    expect(asApiId('7'), 7);
    expect(asApiId(null), isNull);
  });
}
