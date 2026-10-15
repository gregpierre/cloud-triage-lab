---
alert_type: ROOT_ACCOUNT_LOGIN
title: Root Account Login Detected
owner: cloud-security
last_reviewed: 2026-09-28
---

# Runbook: Root Account Login Detected

## Overview
The AWS root user signed in. Root has unrestricted access that cannot be
limited by IAM policies, and day-to-day use of it is almost never legitimate.
Treat every root login as a potential account takeover until proven otherwise.

MITRE ATT&CK: T1078.004 (Valid Accounts: Cloud Accounts)

## Triage
1. Check whether MFA was used for the login (`additionalEventData.MFAUsed`).
2. Look up the source IP. Is it a known corporate egress IP or VPN?
3. Contact the documented root credential custodian and ask if they logged in
   and why. Verify through a second channel, not by replying to an email.
4. List every API call made in the root session in CloudTrail.

## Containment
1. If the login was not authorized, reset the root password and re-register
   the MFA device immediately.
2. Delete any root access keys (`aws iam list-access-keys` while signed in as
   root should return nothing).
3. Review and revert any changes made during the session.

## Remediation
1. Confirm hardware MFA is enabled on root.
2. Store root credentials in the break-glass vault with two-person access.
3. Ensure an SCP denies root actions in member accounts.

## Escalation
- Unauthorized or unverified login: SEV-1, page the incident commander.
- Authorized and documented (for example, billing change): note in ticket and close.
