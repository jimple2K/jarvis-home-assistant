#!/usr/bin/env bash
# Jarvis 10-prompt soak test with deliberate idle pauses.
set -u
BASE=http://127.0.0.1:5757
OUT=/tmp/jarvis-soak.log
: > "$OUT"

prompts=(
  "Hi Jarvis, how are you doing today?"
  "What time is it right now?"
  "Tell me a quick one-sentence joke."
  "What is two hundred forty-seven times sixteen?"
  "Who wrote Pride and Prejudice, in one sentence?"
  "Briefly check this machine's CPU and tell me if anything looks concerning."
  "Add a topic called soak test so I can track this conversation."
  "Remember that we ran a 10-prompt soak test tonight."
  "What is the capital of Australia, in one sentence?"
  "Thanks Jarvis, we are done with the test."
)
# pauses[i] = seconds to sleep AFTER prompts[i] resolves (last entry unused)
pauses=(5 5 30 5 5 5 5 40 5 0)

# Reset conversation to start clean.
echo "[$(date +%H:%M:%S)] === RESET ===" | tee -a "$OUT"
curl -sX POST "$BASE/chat" -H 'Content-Type: application/json' \
  -d '{"reset":true}' >/dev/null

for i in "${!prompts[@]}"; do
  n=$((i+1))
  q="${prompts[$i]}"
  pause="${pauses[$i]}"
  echo "" | tee -a "$OUT"
  echo "[$(date +%H:%M:%S)] --- Q$n: $q" | tee -a "$OUT"
  t0=$(date +%s.%N)
  resp=$(curl -s -X POST "$BASE/chat" \
    -H 'Content-Type: application/json' \
    -d "$(jq -nc --arg m "$q" '{message:$m}')" \
    --max-time 90)
  t1=$(date +%s.%N)
  elapsed=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.2f", b-a}')
  reply=$(echo  "$resp" | jq -r '.reply // .error // "(no reply)"')
  tools=$(echo  "$resp" | jq -r '.tools // [] | map(.tool) | join(",")')
  err=$(  echo  "$resp" | jq -r '.error // empty')
  echo "[$(date +%H:%M:%S)]    elapsed=${elapsed}s tools=[${tools}]" | tee -a "$OUT"
  if [ -n "$err" ]; then
    echo "[$(date +%H:%M:%S)]    ERROR: $err" | tee -a "$OUT"
  fi
  # Show reply truncated to ~200 chars
  echo "[$(date +%H:%M:%S)]    A: $(echo "$reply" | head -c 200)" | tee -a "$OUT"

  if [ "$pause" -gt 0 ]; then
    echo "[$(date +%H:%M:%S)]    ...sleeping ${pause}s (void time)..." | tee -a "$OUT"
    sleep "$pause"
  fi
done

# Quick "speak" probe so the activity panel shows a SPEAK event without playing audio.
# We do this by hitting /tts with an empty body, which short-circuits to 204 No Content
# and does NOT record a speak event. To get a speak event without producing sound,
# temporarily mute via setting volume to 0 — but config is process-wide. Skip and let
# the natural reply events stand on their own.

echo "" | tee -a "$OUT"
echo "[$(date +%H:%M:%S)] === DONE ===" | tee -a "$OUT"
