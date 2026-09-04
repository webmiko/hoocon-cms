import 'package:flutter/material.dart';

const hooconInk = Color(0xFF1A1D21);
const hooconMuted = Color(0xFF5A626C);
const hooconPrimary = Color(0xFF3D4650);
const hooconAccent = Color(0xFFC45C26);
const hooconRed = Color(0xFFDA0E2B);
const hooconBg = Color(0xFFF4F5F6);

final ThemeData hooconTheme = ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(
    seedColor: hooconPrimary,
    primary: hooconPrimary,
    secondary: hooconAccent,
    surface: Colors.white,
    brightness: Brightness.light,
  ),
  scaffoldBackgroundColor: hooconBg,
  appBarTheme: const AppBarTheme(
    backgroundColor: Colors.white,
    foregroundColor: hooconInk,
    elevation: 0,
    centerTitle: false,
  ),
  cardTheme: CardThemeData(
    color: Colors.white,
    elevation: 0,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(12),
      side: BorderSide(color: Colors.black.withValues(alpha: 0.06)),
    ),
  ),
  filledButtonTheme: FilledButtonThemeData(
    style: FilledButton.styleFrom(
      minimumSize: const Size.fromHeight(48),
      backgroundColor: hooconAccent,
      foregroundColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
  ),
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: Colors.white,
    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
  ),
);
