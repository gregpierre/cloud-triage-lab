---
alert_type: SG_OPEN_SSH
title: Security Group Open to 0.0.0.0/0 on Port 22
owner: platform-engineering
last_reviewed: 2026-07-14
---

# Runbook: Security Group Open to 0.0.0.0/0 on Port 22

## Overview
A security group allows inbound SSH (TCP/22) from any IP address. Instances
using it are exposed to constant internet-wide brute-force and credential
stuffing attempts.

MITRE ATT&CK: T1021.004 (Remote Services: SSH)

## Triage
1. List the instances using the security group:
   `aws ec2 describe-instances --filters Name=instance.group-id,Values=<sg-id>`
2. Check whether those instances have public IPs. No public IP means the rule
   is not reachable from the internet.
3. Review VPC Flow Logs for accepted connections on port 22 from unknown IPs.
4. Check `/var/log/auth.log` (or the SSM session history) for successful logins.

## Remediation
1. Replace `0.0.0.0/0` with the corporate VPN CIDR, or remove the rule
   entirely and use AWS Systems Manager Session Manager instead of SSH.
2. Make sure password authentication is disabled in `sshd_config`.

## Escalation
- Successful login from an unknown IP: SEV-2, page on-call.
- No evidence of access: ticket to the resource owner, 5 business day SLA.
