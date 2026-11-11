#!/usr/bin/env bash
# Audit helper: run the L suite on real Linux (WSL Ubuntu on ext4, Docker Desktop engine).
#
# Why: bind mounts on Windows map ownership and modes, so file-ownership bugs and the
# executable bit only show on Linux. This copies the working tree (tracked + untracked,
# not ignored) into ~/saam inside the WSL distro and runs scripts/test-l.sh there as an
# ordinary user (uid 1000), against the same Docker engine.
#
# Usage (from Git Bash at the repository root):
#   audit/tools/linux_check.sh rootclean       # remove root-owned node_modules/dist left by containers
#   audit/tools/linux_check.sh sync            # copy the tree, commit it in the WSL copy
#   audit/tools/linux_check.sh run [args...]   # ./scripts/test-l.sh args... in the copy
#   audit/tools/linux_check.sh sh 'command'    # any command in the copy
#
# pytest is not installed in the distro (no pip, no sudo): the pure-Python wheels
# (pytest and its dependencies) are downloaded once with the Windows pip into
# $TEMP/saam-linux/wheels and unpacked to ~/pylibs, then used through PYTHONPATH.
set -euo pipefail

DISTRO=${WSL_DISTRO:-Ubuntu-22.04}
WORK=$(cygpath -u "${TEMP}")/saam-linux
WIN_WORK=$(cygpath -m "${TEMP}")/saam-linux
WIN_WORK_WSL=$(echo "${WIN_WORK}" | sed 's#^\([A-Za-z]\):#/mnt/\L\1#')

wsl_run() {
  wsl.exe -d "${DISTRO}" -- bash -lc "$1" 2>&1 | tr -d '\0' | grep -v 'Failed to translate'
  return "${PIPESTATUS[0]}"
}

cmd=${1:-}
shift || true
case "${cmd}" in
  libs)
    mkdir -p "${WORK}"
    rm -rf "${WORK}/wheels"
    py -3 -m pip download pytest exceptiongroup tomli typing_extensions \
      --dest "${WORK}/wheels" --python-version 3.10 --only-binary=:all: \
      --platform any --implementation py >/dev/null
    wsl_run "rm -rf ~/pylibs; mkdir -p ~/pylibs; python3 -c \"
import glob, os, zipfile
for w in glob.glob('${WIN_WORK_WSL}/wheels/*.whl'):
    zipfile.ZipFile(w).extractall(os.path.expanduser('~/pylibs'))\""
    ;;
  rootclean)
    # Containers run as root: remove what they left in the WSL copy (node_modules, dist)
    # through the same compose services that created it.
    wsl_run "cd ~/saam/fabric 2>/dev/null || exit 0
      for svc in cc-build gw-build; do
        docker compose --project-name saam-medtrace -f compose/compose.yaml --profile spike run -T --rm --no-deps --entrypoint sh \$svc -c 'rm -rf node_modules dist' >/dev/null 2>&1 || true
      done
      docker ps -a --filter name=saam-medtrace -q | xargs -r docker rm -f >/dev/null 2>&1 || true
      docker network rm saam-medtrace >/dev/null 2>&1 || true
      cd ..; echo root-owned files left: \$(find . -user root 2>/dev/null | wc -l)"
    ;;
  sync)
    mkdir -p "${WORK}"
    git ls-files -co --exclude-standard -z | tar --null -T - -cf "${WORK}/tree.tar"
    wsl_run "set -e; mkdir -p ~/saam; cd ~/saam
      [ -d .git ] || { git init -q; git config user.email a@b.c; git config user.name audit; }
      find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
      tar -xf '${WIN_WORK_WSL}/tree.tar'
      git add -A; git commit -qm snapshot --allow-empty; git ls-files | wc -l"
    ;;
  run)
    wsl_run "cd ~/saam && export PYTHONPATH=\$HOME/pylibs && ./scripts/test-l.sh $*"
    ;;
  sh)
    wsl_run "cd ~/saam && export PYTHONPATH=\$HOME/pylibs && $*"
    ;;
  *)
    echo "usage: $0 libs|sync|run [args]|sh 'command'" >&2
    exit 2
    ;;
esac
