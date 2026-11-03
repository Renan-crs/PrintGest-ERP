#!/usr/bin/env python
"""Teste de conexão do daemon com o backend"""
import sys
sys.path.insert(0, 'C:\\Compart\\Projetos\\Printgest/desktop')

from printgest.core import daemon

print("=" * 60)
print("TESTE DO DAEMON - PrintGest ERP v0.3.8")
print("=" * 60)

# Testar conexão com backend
print("\n1. Testando conexão com backend (http://127.0.0.1:8000/health)...")
saude = daemon.saude(timeout=3.0)
print(f"   Resultado: {'✅ SAUDÁVEL' if saude else '❌ INDISPONÍVEL'}")

if saude:
    print("\n2. Testando porta fallback TCP...")
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    result = sock.connect_ex(('127.0.0.1', 8000))
    sock.close()
    print(f"   Porta 8000: {'✅ ABERTA' if result == 0 else '❌ FECHADA'}")
else:
    print("\n2. Backend não respondendo - verificando porta...")
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    result = sock.connect_ex(('127.0.0.1', 8000))
    sock.close()
    print(f"   Porta 8000: {'✅ ABERTA' if result == 0 else '❌ FECHADA'}")

print("\n" + "=" * 60)
print("RESULTADO GERAL:", "✅ DAEMON FUNCIONANDO" if saude else "❌ FALHA NO DAEMON")
print("=" * 60)

# Testar caminho do backend
print("\n3. Testando caminho do backend...")
caminho = daemon.caminho_do_backend()
print(f"   Caminho: {caminho if caminho else 'Nenhum (modo dev)'}")