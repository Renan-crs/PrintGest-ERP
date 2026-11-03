# Script para padronizar nomenclatura de releases
# Execute do diretório do projeto

# Lista de releases a atualizar com seus títulos padronizados
releases=(
    "v0.1.0|Initial Release"
    "v0.2.0|Features and Modules"
    "v0.2.1|Agendamento e Correções"
    "v0.2.2|Melhorias UI/UX"
    "v0.3.0|Projetos Kanban e PDV"
    "v0.3.1|Sistema de Atualização"
    "v0.3.2|Refatoração de UI"
    "v0.3.3|Sessão Persistente"
    "v0.3.4|Timeout de Sessão e WinError 10061"
    "v0.3.5|Neon Database - PostgreSQL Gerenciado"
    "v0.3.6|PermissionError SSL Corrigido"
    "v0.3.7|Neon Database Estável"
    "v0.3.8|Neon Database Estável com Correções"
)

echo "Release names padronizados:"
for release in "${releases[@]}"; do
    tag="${release%%|*}"
    title="${release##*|}"
    echo "- $tag: $title"
done