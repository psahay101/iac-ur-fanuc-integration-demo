#!/usr/bin/env bash
# Build the bundled official sources, Python bridge, and web application.
set -eo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
if [[ ! -f /opt/ros/humble/setup.bash ]]; then
    echo 'ROS 2 Humble is required. See README.md for Ubuntu 22.04 prerequisites.' >&2
    exit 1
fi
for program in colcon cmake g++ node npm; do
    command -v "$program" >/dev/null || { echo "Missing $program; see README.md prerequisites." >&2; exit 1; }
done
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<20||(a===20&&b<19)||(a===22&&b<12)) { console.error("Node >=20.19 or >=22.12 required"); process.exit(1) }'
export PYTHONNOUSERSITE=1
export PIP_CACHE_DIR="$project_root/.runtime/pip-cache"
export npm_config_cache="$project_root/.runtime/npm-cache"
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
bash scripts/setup_ur.sh
bash scripts/setup_fanuc.sh
(cd frontend && npm ci && npm run build)
echo 'Setup complete. Start with: bash scripts/run.sh'
