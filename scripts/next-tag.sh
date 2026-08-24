#!/bin/bash
# Pega a última tag ou começa em v0.0.0
CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
# Remove o 'v' para calcular
VERSION=${CURRENT_TAG#v}
MAJOR=$(echo $VERSION | cut -d. -f1)
MINOR=$(echo $VERSION | cut -d. -f2)
PATCH=$(echo $VERSION | cut -d. -f3)

case "$1" in
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    feat)  MINOR=$((MINOR + 1)); PATCH=0 ;;
    fix)   PATCH=$((PATCH + 1)) ;;
    *)     echo "Uso: $0 {major|feat|fix}"; exit 1 ;;
esac

echo "v$MAJOR.$MINOR.$PATCH"
