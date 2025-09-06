#!/usr/bin/env sh
set -euf

echo "Kick Off Kings — interactive setup (POSIX sh)"
echo "---------------------------------------------"

printf "Domain to use (e.g., picks.example.com) [leave blank for none]: "
read -r DOMAIN || true
printf "Season year [2025]: "
read -r NFL_YEAR || true
[ -z "${NFL_YEAR:-}" ] && NFL_YEAR=2025

printf "Season type (1=Pre, 2=Regular, 3=Post) [2]: "
read -r NFL_SEASONTYPE || true
[ -z "${NFL_SEASONTYPE:-}" ] && NFL_SEASONTYPE=2

printf "How many users? [2]: "
read -r N || true
[ -z "${N:-}" ] && N=2

USERS=""
i=1
while [ "$i" -le "$N" ]; do
  printf "  Username #$i (letters/numbers/_- only): "
  read -r U || true
  # normalize: lowercase, strip invalid
  U=$(printf "%s" "$U" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')
  if [ -n "$U" ]; then
    if [ -z "$USERS" ]; then USERS="$U"; else USERS="$USERS,$U"; fi
  fi
  i=$((i+1))
done

if [ -z "$USERS" ]; then
  echo "No users entered; defaulting to user1,user2"
  USERS="user1,user2"
fi

# Secrets
if command -v openssl >/dev/null 2>&1; then
  FLASK_SECRET=$(openssl rand -hex 32)
  BUILD_ID=$(date +%Y%m%d%H%M%S)
else
  FLASK_SECRET="changeme-$(date +%s)"
  BUILD_ID=$(date +%Y%m%d%H%M%S)
fi

echo "Writing .env ..."
{
  echo "FLASK_SECRET=$FLASK_SECRET"
  echo "BUILD_ID=$BUILD_ID"
  echo "NFL_YEAR=$NFL_YEAR"
  echo "NFL_SEASONTYPE=$NFL_SEASONTYPE"
  echo "USERS=$USERS"
} > .env

# Generate tokens per user
IFS=,; for u in $USERS; do
  # uppercase username without ${u^^}
  UUP=$(printf "%s" "$u" | tr '[:lower:]' '[:upper:]')
  if command -v openssl >/dev/null 2>&1; then
    tok=$(openssl rand -hex 24)
  else
    tok="tok-$(date +%s)-$u"
  fi
  echo "TOKEN_${UUP}=$tok" >> .env
done
unset IFS

# Update Caddyfile domain if provided
if [ -n "${DOMAIN:-}" ] && [ -f Caddyfile ]; then
  echo "Updating Caddyfile domain -> $DOMAIN"
  # replace first line like 'picks.example.com {'
  # Use sed portable in-place via temp file
  tmpf="$(mktemp)"
  sed "1s|^.*{|$DOMAIN {|" Caddyfile > "$tmpf" && mv "$tmpf" Caddyfile
fi

echo "Login URLs:"
IFS=,; for u in $USERS; do
  UUP=$(printf "%s" "$u" | tr '[:lower:]' '[:upper:]')
  tok=$(grep "^TOKEN_${UUP}=" .env | cut -d= -f2-)
  if [ -n "${DOMAIN:-}" ]; then
    echo "  https://$DOMAIN/login/$u/$tok"
  else
    echo "  http://<host>:8000/login/$u/$tok"
  fi
done
unset IFS

echo ""
echo "Next:"
echo "  docker compose -f docker-compose.basic.yml up -d --build   # local"
echo "or"
echo "  docker compose -f docker-compose.caddy.yml up -d --build   # HTTPS (requires DNS to this host)"
