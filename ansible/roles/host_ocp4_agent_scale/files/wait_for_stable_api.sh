#!/bin/bash
# Require 120 seconds of consecutive healthy samples within a 15-minute bound.
# Read-only: never restarts nodes, approves CSRs or retries ISO generation.
set -euo pipefail
command -v oc >/dev/null
command -v jq >/dev/null
start=$SECONDS
stable_since=-1
previous_revision=''
while (( SECONDS - start < 900 )); do
  healthy=false
  revision=''
  if oc --request-timeout=10s get --raw=/readyz >/dev/null 2>&1 &&
     operators=$(oc --request-timeout=10s get clusteroperators kube-apiserver authentication ingress -o json 2>/dev/null) &&
     jq -e '
       (.items | length == 3) and
       all(.items[];
         any(.status.conditions[]; .type == "Available" and .status == "True") and
         any(.status.conditions[]; .type == "Progressing" and .status == "False") and
         any(.status.conditions[]; .type == "Degraded" and .status == "False"))
     ' <<< "$operators" >/dev/null &&
     apiserver=$(oc --request-timeout=10s get kubeapiserver.operator.openshift.io cluster -o json 2>/dev/null) &&
     jq -e '
       (.status.latestAvailableRevision > 0) and
       (.status.nodeStatuses | length > 0) and
       all(.status.nodeStatuses[];
         .currentRevision > 0 and .currentRevision == .targetRevision) and
       (.status.latestAvailableRevision as $latest |
         all(.status.nodeStatuses[]; .currentRevision == $latest))
     ' <<< "$apiserver" >/dev/null; then
    healthy=true
    revision=$(jq -c '[.status.latestAvailableRevision,
      (.status.nodeStatuses | sort_by(.nodeName) | map({nodeName, currentRevision, targetRevision}))]' <<< "$apiserver")
  fi

  if "$healthy"; then
    if [[ "$revision" != "$previous_revision" ]] || (( stable_since < 0 )); then
      stable_since=$SECONDS
    fi
    previous_revision=$revision
    if (( SECONDS - stable_since >= 120 )); then
      echo 'API ready, operators healthy and kube-apiserver revisions settled for at least 120 seconds.'
      exit 0
    fi
    echo "API healthy; stability window $((SECONDS - stable_since))/120 seconds."
  else
    stable_since=-1
    previous_revision=''
    echo 'API not yet stable; waiting for readiness, operator health and settled revisions.'
  fi
  sleep 20
done

echo 'Timed out waiting for a stable API after 15 minutes; ISO generation was not attempted.' >&2
exit 1
