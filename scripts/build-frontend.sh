#!/bin/bash
set -e
cd "$(dirname "$0")/../frontend-vite"
npm run build
# Copy index.html to Django templates
mkdir -p ../frontend/templates/frontend
cp ../frontend/static/frontend/index.html ../frontend/templates/frontend/index.html
echo "Frontend built and copied to Django."
