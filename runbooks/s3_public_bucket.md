---
alert_type: S3_PUBLIC_BUCKET
title: S3 Bucket Publicly Accessible
owner: cloud-security
last_reviewed: 2026-08-19
---

# Runbook: S3 Bucket Publicly Accessible

## Overview
An S3 bucket can be read (and possibly listed or written) by anyone on the
internet. Impact depends entirely on what is stored in the bucket. A public
website bucket may be expected; a bucket of customer exports is a data breach.

MITRE ATT&CK: T1530 (Data from Cloud Storage)

## Triage
1. Check the asset inventory for the bucket's data classification.
2. Confirm whether public access is documented as intentional (for example,
   static website hosting behind CloudFront).
3. Review S3 server access logs or CloudTrail data events for `GetObject`
   requests from unknown IPs.
4. Note whether `s3:ListBucket` is public. Listing makes discovery trivial.

## Containment
1. Enable S3 Block Public Access on the bucket:
   `aws s3api put-public-access-block --bucket <name> --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true`
2. If sensitive data was exposed, preserve access logs before changing
   anything else.

## Remediation
1. Remove `"Principal": "*"` statements from the bucket policy.
2. For intentional public content, serve it through CloudFront with Origin
   Access Control instead of a public bucket.
3. Enable account-level Block Public Access where possible.

## Escalation
- Restricted or confidential data exposed: SEV-1, notify privacy/legal.
- Intentional public content: document the exception and close.
