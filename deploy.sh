#!/usr/bin/env bash
# Publish public_html/ to https://home.cc.umanitoba.ca/~opumni/
#
#   ./deploy.sh --here   when logged in to the UManitoba server: copy into ~/public_html
#   ./deploy.sh          from another machine: upload over ssh to ccl.cc.umanitoba.ca
#   add -y to skip the "Publish these changes?" question
#
# Shows what will change, asks, then copies. Files you deleted from public_html/
# are also deleted from the live site.
set -euo pipefail
cd "$(dirname "$0")"

HOST="opumni@ccl.cc.umanitoba.ca"
SOCKET="$HOME/.ssh/deploy-%r@%h:%p"
SSH="ssh -o ControlMaster=auto -o ControlPath=$SOCKET -o ControlPersist=60"
# Directories 755, files 644, CGI scripts stay 755 (they are executable in git).
RSYNC_OPTS=(-rlptz --delete --chmod=go-w,a+rX --exclude=_template.html --exclude=.DS_Store --exclude='*~')
# Safe to repeat on every run: the private data folder for the visitor stats and the
# permissions IST requires. Written so it also works if the server's shell is tcsh.
SETUP='mkdir -p -m 700 ~/site-data && chmod a+x ~ && mkdir -p ~/public_html && chmod 755 ~/public_html && (test -x /usr/bin/rsync && echo yes || echo no)'

HERE=no
ASK=yes
for arg in "$@"; do
  case "$arg" in
    --here) HERE=yes ;;
    -y) ASK=no ;;
    *) echo "Unknown option: $arg (use --here and/or -y)"; exit 1 ;;
  esac
done

if [ "$HERE" = yes ]; then
  DEST="$HOME/public_html/"
  have_rsync=$(bash -c "$SETUP")
  RSYNC=(rsync "${RSYNC_OPTS[@]}")
else
  DEST="$HOST:public_html/"
  trap '$SSH -O exit "$HOST" 2>/dev/null || true' EXIT
  echo "Connecting to $HOST ..."
  have_rsync=$($SSH "$HOST" "$SETUP")
  RSYNC=(rsync "${RSYNC_OPTS[@]}" -e "$SSH")
fi

if [ "$have_rsync" != yes ]; then
  echo "rsync is not available, so copying everything instead."
  echo "(Files you deleted from public_html/ stay on the live site; remove them by hand.)"
  if [ "$HERE" = yes ]; then
    cp -R public_html/. "$HOME/public_html/"
    rm -f "$HOME/public_html/blog/_template.html"
    chmod -R go-w,a+rX "$HOME/public_html"
  else
    scp -o ControlPath="$SOCKET" -rp public_html/. "$DEST"
    $SSH "$HOST" 'rm -f ~/public_html/blog/_template.html; chmod -R go-w,a+rX ~/public_html'
  fi
  echo "Done: https://home.cc.umanitoba.ca/~opumni/"
  exit 0
fi

echo
echo "Changes on the live site (+ new, s/t changed, *deleting removed):"
"${RSYNC[@]}" --dry-run --itemize-changes public_html/ "$DEST" | grep -v '^\.' || echo "  (nothing to copy)"
echo

if [ "$ASK" = yes ]; then
  read -r -p "Publish these changes? [y/N] " answer
  case "$answer" in
    y|Y|yes) ;;
    *) echo "Nothing changed."; exit 0 ;;
  esac
fi

"${RSYNC[@]}" public_html/ "$DEST"
echo "Done: https://home.cc.umanitoba.ca/~opumni/"
