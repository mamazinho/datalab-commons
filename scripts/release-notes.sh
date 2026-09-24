#!/bin/bash
# Imprime a seção do CHANGES.rst da versão informada, sem o título. Sai com erro se não houver.
if [ -z "$1" ]; then
    echo "Uso: $0 X.Y.Z" >&2; exit 1
fi

# O título de seção é "X.Y.Z (data)" sublinhado com "-"; a seção vai até o próximo título.
awk -v version="$1" '
    $1 == version { found = 1; getline; next }
    found && /^[0-9]+\.[0-9]+\.[0-9]+ / { exit }
    found && NF { printf "%s", blanks; blanks = ""; print; started = 1; next }
    found && started { blanks = blanks "\n" }
    END { exit !found }
' "$(dirname "$0")/../CHANGES.rst"
