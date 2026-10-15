---
alert_type: CLOUDTRAIL_DISABLED
title: CloudTrail Logging Disabled
owner: cloud-security
last_reviewed: 2025-11-02
---

# Runbook: CloudTrail Logging Disabled

## Overview
CloudTrail logging was stopped or the trail was deleted. Attackers commonly
disable logging right before doing something they don't want recorded, so
this alert is often a precursor to a larger incident.

MITRE ATT&CK: T1562.008 (Impair Defenses: Disable or Modify Cloud Logs)

## Triage
1. Find the `StopLogging`, `DeleteTrail`, or `UpdateTrail` event and record
   who performed it and from which IP.
2. Check whether it was an organization trail (all accounts affected) or a
   single-account trail.
3. Check for a matching change ticket. Logging should never be stopped
   without one.

## Containment
1. Restart logging immediately:
   `aws cloudtrail start-logging --name <trail-name>`
2. Suspend the principal that stopped logging until it is explained.

## Remediation
1. Add an SCP that denies `cloudtrail:StopLogging` and `cloudtrail:DeleteTrail`
   for everyone except a tightly controlled break-glass role.
2. Enable CloudTrail log file validation and confirm logs are delivered to the
   central log-archive account.

## Escalation
- No change ticket: SEV-1, page the incident commander.
- Change ticket exists: confirm with the requester and close.
