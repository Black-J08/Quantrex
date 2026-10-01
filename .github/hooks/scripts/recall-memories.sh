#!/usr/bin/env bash
# Recall relevant memories from Hindsight before starting a task
# This hook runs at UserPromptSubmit
# Logs to log.log for debugging

set -euo pipefail

# Setup logging
LOG_FILE="logs/hindsight-usersubmitprompt-hook.log"

# Create logs directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

exec 3>&1  # Save stdout to fd 3
exec 1>>"$LOG_FILE" 2>&1  # Redirect stdout/stderr to log file

log() {
  local msg="[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
  echo "$msg" >&3   # Also print to terminal (fd 3)
  echo "$msg" >&1   # Write to log file (stdout is redirected to log file)
}

log "=== recall-memories.sh started ==="

# Read the hook input from stdin
input=$(cat)
log "Input: $input"

# Extract the user's prompt from the input (UserPromptSubmit has .prompt)
prompt=""
if echo "$input" | jq -e '.prompt' >/dev/null 2>&1; then
  prompt=$(echo "$input" | jq -r '.prompt')
  log "Found prompt: $prompt"
fi

# If no prompt found, exit gracefully
if [ -z "$prompt" ] || [ "$prompt" = "null" ]; then
  log "No prompt found, exiting gracefully"
  echo '{"continue": true}' >&3
  exit 0
fi

# Check if Hindsight CLI is available
if ! command -v hindsight &> /dev/null; then
  log "Hindsight CLI not found"
  echo '{"continue": true, "systemMessage": "Hindsight CLI not found. Skipping memory recall."}' >&3
  exit 0
fi

# Check if Hindsight config exists
if [ ! -f "$HOME/.hindsight/config" ]; then
  log "Hindsight config not found"
  echo '{"continue": true, "systemMessage": "Hindsight not configured. Skipping memory recall."}' >&3
  exit 0
fi

# Get the bank ID from environment or config
BANK_ID="${HINDSIGHT_BANK_ID:-}"
if [ -z "$BANK_ID" ]; then
  # Try to read from a project config file (skip comments and empty lines)
  if [ -f ".hindsight-bank" ]; then
    BANK_ID=$(grep -v '^#' .hindsight-bank | grep -v '^$' | head -1)
  fi
fi

if [ -z "$BANK_ID" ]; then
  log "No bank ID configured"
  echo '{"continue": true, "systemMessage": "No Hindsight bank ID configured. Skipping memory recall."}' >&3
  exit 0
fi

log "Bank ID: $BANK_ID"

# Recall memories relevant to the prompt
log "Recalling memories for: $prompt"
recalled=$(hindsight memory recall "$BANK_ID" "$prompt" --max-tokens 2000 2>&1)
recall_exit_code=$?
log "Recall exit code: $recall_exit_code"
log "Recalled: $recalled"

if [ $recall_exit_code -eq 0 ] && [ -n "$recalled" ] && [ "$recalled" != "null" ]; then
  # UserPromptSubmit uses systemMessage
  output=$(jq -n \
    --arg msg "Relevant memories from Hindsight:\n$recalled" \
    '{continue: true, systemMessage: $msg}')
  
  log "Output: $output"
  echo "$output" >&3
else
  log "No memories recalled or error occurred"
  echo '{"continue": true}' >&3
fi

log "=== recall-memories.sh completed ==="