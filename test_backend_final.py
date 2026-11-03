#!/usr/bin/env python
"""Script de teste final do backend"""
import urllib.request
import json

try:
    response = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)
    data = response.read().decode()
    print("Status HTTP:", response.status)
    print("Resposta:", data)
    
    if response.status == 200:
        print("\n✅ BACKEND FUNCIONANDO PERFEITAMENTE!")
        
        # Testar outro endpoint
        response2 = urllib.request.urlopen('http://127.0.0.1:8000/v1/licenca', timeout=5)
        print("\nResposta /v1/licenca:", response2.read().decode())
        
    else:
        print("\n❌ Erro na resposta")
except Exception as e:
    print(f"❌ Erro: {e}")
    import traceback
    traceback.print_exc()