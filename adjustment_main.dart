import 'dart:io' if (dart.library.html) 'dart:html' as html;
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() {
  if (kIsWeb) {
    // Web-specific setup (e.g., avoid dart:io)
    print("Running on web");
  } else {
    // Mobile-specific setup
    print("Running on mobile");
  }
  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Beba',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: Scaffold(
        appBar: AppBar(title: Text('Beba')),
        body: Center(child: Text('Welcome to Beba')),
      ),
    );
  }
}

