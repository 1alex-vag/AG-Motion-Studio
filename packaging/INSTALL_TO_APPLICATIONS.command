#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
source_app="$PWD/AG Astro Motion Studio.app"
if [[ ! -d "$source_app" ]]; then
  printf 'AG Astro Motion Studio.app is missing. Extract the entire release ZIP first.\n'
  exit 1
fi
if [[ "${APP_INSTALL_SCOPE:-user}" == system ]]; then
  destination_root=/Applications
else
  destination_root="$HOME/Applications"
fi
mkdir -p "$destination_root"
if [[ ! -w "$destination_root" ]]; then
  printf 'Applications folder is not writable. Run without APP_INSTALL_SCOPE=system to install for your user.\n'
  exit 1
fi
staging=$(mktemp -d "$destination_root/.AGAstroInstall.XXXXXX")
trap 'rm -rf -- "$staging"' EXIT
ditto "$source_app" "$staging/AG Astro Motion Studio.app"
destination="$destination_root/AG Astro Motion Studio.app"
if [[ -e "$destination" ]]; then
  mv "$destination" "$destination_root/AG Astro Motion Studio.previous.$(date +%Y%m%d%H%M%S).app"
fi
mv "$staging/AG Astro Motion Studio.app" "$destination"
printf 'Installed: %s\nUser data was preserved. Siril and other applications were not changed.\n' "$destination"
