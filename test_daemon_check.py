#!/usr/bin/env python
"""Teste rápido do daemon - verifica se o backend está respondendo"""
import sys
import os

# Configurar path
sys.path.insert(0, 'C:\\Compart\\Projetos\\Printgest/desktop')

try:
    from printgest.core import daemon
    
    print("=" * 60)
    print("TESTE DO DAEMON")
    print("=" * 60)
    
    print("\n1. Testando conexão com backend (127.0.0.1:8000)...")
    saude = daemon.saude(timeout=2.0)
    print(f"   Status: {'✅ SAUDÁVEL' if saude else '❌ INDISPONÍVEL'}")
    
    if not saude:
        print("\n2. Verificando porta 8000...")
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        result = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        print(f"   Porta 8000: {'✅ ABERTA' if result == 0 else '❌ FECHADA'}")
    
    print("\n" + "=" * 60)
    print("RESULTADO:", "✅ BACKEND FUNFANDO" if saude else "❌ BACKEND PARADO")
    print("=" * 60)
    
except Exception as e:
    import traceback
    print(f"ERRO: {e}")
    traceback.print_exc()
    sys.exit(1)