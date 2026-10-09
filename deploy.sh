#!/usr/bin/env bash
# Upload public_html/ to https://home.cc.umanitoba.ca/~opumni/
#
#   ./deploy.sh      show what will change on the server, ask, then upload
#   ./deploy.sh -y   upload without asking
#
# Asks for your UManitoba (IST Linux) password once per run, unless you have set up
# an SSH key (see README). Files you deleted locally are also deleted on the server.
set -euo pipefail
cd "$(dirname "$0")"

HOST="opumni@ccl.cc.umanitoba.ca"
SOCKET="$HOME/.ssh/deploy-%r@%h:%p"
SSH="ssh -o ControlMaster=auto -o ControlPath=$SOCKET -o ControlPersist=60"
# Directories 755, files 644, CGI scripts stay 755 (they are executable in git).
RSYNC_OPTS=(-rlptz --delete --chmod=go-w,a+rX --exclude=_template.html --exclude=.DS_Store --exclude='*~')

trap '$SSH -O exit "$HOST" 2>/dev/null || true' EXIT

echo "Connecting to $HOST ..."
# One-time setup is repeated safely on every run: the private data folder for the
# visitor stats, and the permissions IST requires for ~/public_html.
remote_rsync=$($SSH "$HOST" 'mkdir -p -m 700 ~/site-data && chmod a+x ~ \
  && mkdir -p ~/public_html && chmod 755 ~/public_html \
  && (command -v rsync >/dev/null && echo yes || echo no)')

if [ "$remote_rsync" != "yes" ]; then
  echo "rsync is not available on the server, so copying everything with scp instead."
  echo "(Files you deleted locally will stay on the server; remove them by hand.)"
  scp -o ControlPath="$SOCKET" -rp public_html/. "$HOST:public_html/"
  $SSH "$HOST" 'rm -f ~/public_html/blog/_template.html; chmod -R go-w,a+rX ~/public_html'
  echo "Done: https://home.cc.umanitoba.ca/~opumni/"
  exit 0
fi

echo
echo "Changes on the server (+ new, s/t changed, *deleting removed):"
rsync "${RSYNC_OPTS[@]}" -e "$SSH" --dry-run --itemize-changes public_html/ "$HOST:public_html/" \
  | grep -v '^\.' || echo "  (nothing to upload)"
echo

if [ "${1:-}" != "-y" ]; then
  read -r -p "Upload these changes? [y/N] " answer
  case "$answer" in
    y|Y|yes) ;;
    *) echo "Nothing uploaded."; exit 0 ;;
  esac
fi

rsync "${RSYNC_OPTS[@]}" -e "$SSH" public_html/ "$HOST:public_html/"
echo "Done: https://home.cc.umanitoba.ca/~opumni/"
