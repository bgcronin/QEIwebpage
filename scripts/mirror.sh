#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:-mirror.config.json}"
REPORTS="${2:-reports}"
RAW="${3:-raw-site}"
SITE="${4:-site}"

if [[ ! -f "$REPORTS/active-hosts.txt" || ! -f "$REPORTS/seed-urls.txt" ]]; then
  echo "Host and URL discovery reports are required." >&2
  exit 2
fi

readarray -t HOSTS < <(grep -E '^[A-Za-z0-9.-]+$' "$REPORTS/active-hosts.txt" | sort -u)
if [[ ${#HOSTS[@]} -eq 0 ]]; then
  echo "No active hosts found." >&2
  exit 3
fi

DOMAINS=$(IFS=,; echo "${HOSTS[*]}")
TIMEOUT=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["request_timeout_seconds"])' "$CONFIG")
DELAY=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["crawl_delay_seconds"])' "$CONFIG")
USER_AGENT=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["user_agent"])' "$CONFIG")
CANONICAL=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["canonical_host"])' "$CONFIG")
MAX_FILE_MB=$(python -c 'import json,sys; print(json.load(open(sys.argv[1])).get("max_single_file_megabytes", 90))' "$CONFIG")
MAX_TOTAL_MB=$(python -c 'import json,sys; print(json.load(open(sys.argv[1])).get("max_total_download_megabytes", 1800))' "$CONFIG")

rm -rf "$RAW" "$SITE"
mkdir -p "$RAW" "$SITE" "$REPORTS"

set +e
wget \
  --input-file="$REPORTS/seed-urls.txt" \
  --directory-prefix="$RAW" \
  --recursive \
  --level=inf \
  --page-requisites \
  --convert-links \
  --adjust-extension \
  --restrict-file-names=windows \
  --quota="${MAX_TOTAL_MB}m" \
  --span-hosts \
  --domains="$DOMAINS" \
  --execute=robots=on \
  --wait="$DELAY" \
  --timeout="$TIMEOUT" \
  --tries=2 \
  --retry-connrefused \
  --user-agent="$USER_AGENT" \
  --reject-regex='/(wp-admin|wp-login\.php|xmlrpc\.php)(/|$)|[?&](s=|preview=|replytocom=)' \
  --no-verbose \
  2>&1 | tee "$REPORTS/wget.log"
WGET_STATUS=${PIPESTATUS[0]}
set -e

echo "$WGET_STATUS" > "$REPORTS/wget-exit-code.txt"
if [[ ! -d "$RAW" ]] || ! find "$RAW" -type f -print -quit | grep -q .; then
  echo "wget produced no files (exit code $WGET_STATUS)." >&2
  exit 4
fi

# Keep each discovered host under _subdomains and promote the canonical host to the preview root.
mkdir -p "$SITE/_subdomains"
for HOST in "${HOSTS[@]}"; do
  if [[ -d "$RAW/$HOST" ]]; then
    mkdir -p "$SITE/_subdomains/$HOST"
    cp -a "$RAW/$HOST/." "$SITE/_subdomains/$HOST/"
  fi
done

SOURCE_DIR=""
for CANDIDATE in "$RAW/$CANONICAL" "$RAW/www.$CANONICAL"; do
  if [[ -d "$CANDIDATE" ]]; then
    SOURCE_DIR="$CANDIDATE"
    break
  fi
done
if [[ -z "$SOURCE_DIR" ]]; then
  for HOST in "${HOSTS[@]}"; do
    if [[ -d "$RAW/$HOST" ]]; then
      SOURCE_DIR="$RAW/$HOST"
      break
    fi
  done
fi

if [[ -n "$SOURCE_DIR" ]]; then
  cp -a "$SOURCE_DIR/." "$SITE/"
fi

if [[ ! -f "$SITE/index.html" ]]; then
  cat > "$SITE/index.html" <<EOF
<!doctype html><meta charset="utf-8"><title>QEI mirror</title>
<h1>QEI mirror snapshot</h1>
<p>The canonical home page was not downloaded. See <a href="_subdomains/">the host snapshots</a> and the audit report.</p>
EOF
fi

find "$SITE" -type f | sort > "$REPORTS/mirrored-files.txt"
echo "wget exit code: $WGET_STATUS"
echo "Mirrored files: $(wc -l < "$REPORTS/mirrored-files.txt")"
