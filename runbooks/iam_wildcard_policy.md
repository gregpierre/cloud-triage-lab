---
alert_type: IAM_WILDCARD_POLICY
title: IAM Policy Allows Wildcard Permissions
owner: cloud-security
last_reviewed: 2026-09-02
---

# Runbook: IAM Policy Allows Wildcard Permissions (`*:*`)

## Overview
A customer-managed IAM policy grants `"Action": "*"` on `"Resource": "*"`. Any
principal with this policy attached is effectively an account administrator.
If one of those principals is compromised, the attacker controls the account.

MITRE ATT&CK: T1098.003 (Account Manipulation: Additional Cloud Roles)

## Triage
1. Identify every role, user, and group the policy is attached to:
   `aws iam list-entities-for-policy --policy-arn <policy-arn>`
2. Check CloudTrail for recent use of those principals (last 30 days).
3. Determine whether the policy was created recently or is a legacy policy.
   A brand-new wildcard policy is far more suspicious than an old one.
4. Ask the resource owner whether full admin is actually required.

## Containment
1. If there is any sign of misuse, attach an explicit `Deny *` inline policy
   to the affected principals to stop activity immediately.
2. Rotate access keys for any IAM users the policy is attached to.

## Remediation
1. Replace the wildcard policy with a least-privilege policy. IAM Access
   Analyzer's policy generation can build one from CloudTrail history.
2. Detach and delete the wildcard policy once the replacement is tested.
3. Add an SCP or CI policy check that blocks new `*:*` policies.

## Escalation
- Signs of misuse: page the on-call incident commander (SEV-1).
- No misuse but production account: ticket to the owning team, 48h SLA.
