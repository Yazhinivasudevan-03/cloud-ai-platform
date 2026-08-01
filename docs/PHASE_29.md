# Phase 29 — Automatic AWS Resource Discovery, Persistence & Live Dashboard

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 29 (triggered by a direct incident report: a real EC2 instance created in AWS Console did not
appear anywhere in the platform, despite the AWS account showing as successfully connected)
Status: **Complete**

---

## 1. Root cause

AWS credentials genuinely were already being used by real `boto3` calls end-to-end - that part worked
correctly before this phase (`app/integrations/providers/aws_provider.py`, `app/integrations/
aws_cloudwatch.py`; no mocks anywhere in the production path). Real, live resource discovery also
already existed - `AwsCloudProviderClient.list_resources()` called real `ec2.describe_instances()` -
but it was wired as an **on-demand-only, never-persisted browse endpoint** (`GET /cloud-provider-
accounts/{id}/resources`, Phase 25C) that nothing else in the platform ever called automatically.

Meanwhile, the Dashboard's "Projects" stat card counted `Project` rows a user must manually create via
`POST /projects`, and the entire CloudWatch-metrics/alerting pipeline (`CloudSyncService`,
`ResourceUsage`, `Alert`) was keyed off a `Deployment` row a user had to manually create (Project ->
Microservice -> Deployment) and manually type an EC2 instance ID into
(`Deployment.cloud_provider_account_id` + `Deployment.cloud_resource_identifier`). **Connecting an AWS
account and having real resources exist in it had zero automatic effect on the platform** - nothing
bridged "account connected" -> "a persisted record exists for each real resource."

## 2. What was built

A purely additive bridge, leaving every existing Project/Microservice/Deployment/Pod/Alert code path and
the Phase 25C on-demand browse endpoint completely untouched:

- **New persistence**: `CloudResource` (13 resource types: EC2/ECS/EKS/Lambda/RDS/S3/EBS/ELB/ASG/VPC/
  Subnets/SecurityGroups/CloudWatch Alarms) and `CloudResourceMetric` (EC2 CloudWatch datapoints) tables,
  plus `CloudProviderAccount.last_discovery_at`/`last_discovery_error`.
- **8 new real AWS inventory methods** on `AwsCloudProviderClient` (`list_ecs_clusters`,
  `list_serverless_functions`, `list_volumes`, `list_load_balancers`, `list_scaling_groups`,
  `list_subnets`, `list_security_groups`, `list_alarms`) plus `list_ec2_instances_detailed` (adds
  availability_zone/public_ip/private_ip/tags on top of the existing `list_resources()` shape, sharing
  one underlying `describe_instances` call so the existing, already-tested method's output never changes).
- **`fetch_ec2_full_metrics`** (`app/integrations/aws_cloudwatch.py`): adds `DiskReadBytes`,
  `DiskWriteBytes`, `StatusCheckFailed` to the existing CPU/network CloudWatch query, plus a best-effort
  `CWAgent` memory reading converted from `mem_used_percent` using the instance's real total memory
  (a genuine `DescribeInstanceTypes` call, never a fabricated conversion) - `None` when the agent isn't
  installed, matching this module's existing disclosed-limitation convention.
- **`CloudResourceDiscoveryService`** (new): discovers every category across every relevant region,
  upserts `CloudResource` rows keyed by (account, type, region, external_id), and flips any
  previously-active row not seen in a fresh pass to `is_active=False` - the generic mechanism behind
  automatic appear/disappear (requirement 9). Collects fresh CloudWatch metrics for every active,
  *running* EC2 instance on the same cycle. A category the provider doesn't support is skipped silently;
  a genuine failure is recorded into `last_discovery_error` and re-raised so a user-triggered call sees
  the real reason (requirement 12) rather than a silent empty result.
- **Automatic triggers**: a best-effort discovery call added to `POST /{id}/validate-credentials`
  (fires the moment an account is connected), plus a new scheduled job
  (`CLOUD_RESOURCE_DISCOVERY_INTERVAL_SECONDS`, default 60s) registered in `app/main.py` alongside the
  existing cloud-sync/region-sync jobs.
- **New endpoints**: `GET /{id}/discovered-resources` (reads only from MySQL - no live call, which is
  what keeps the Dashboard fast), `GET /{id}/discovered-resources/summary` (running/stopped counts,
  per-type counts), `POST /{id}/discover-resources` (force an immediate run, same idea as "Refresh
  Regions").
- **Frontend**: Dashboard gains an EC2 instances/running/stopped stat row (polling every 60s, same
  pattern already used for Active Alerts); a new `CloudAccountDiscoveredResourcesCard` on the Cloud
  Account detail page renders the persisted EC2 table (name/ID/type/region/AZ/public+private IP/state/
  live CPU/memory/network) plus the other 12 resource types, with a "Discover Now" button.

## 3. Every AWS API used

`ec2.describe_instances`, `ec2.describe_volumes`, `ec2.describe_subnets`, `ec2.describe_security_groups`,
`ec2.describe_instance_types`, `ecs.list_clusters`/`describe_clusters`, `lambda.list_functions`,
`elbv2.describe_load_balancers`, `autoscaling.describe_auto_scaling_groups`,
`cloudwatch.describe_alarms`, `cloudwatch.get_metric_data` (`AWS/EC2` and `CWAgent` namespaces) - all
real, paginated where applicable, retried on genuine transient errors only (`tenacity`, same taxonomy as
every existing AWS integration in this project), never mocked in the production code path.

## 4. Logging (requirement 11)

Every discovery call logs before (`account/provider/region/category`) and after (result count) via
`app/utils/logger.py`'s existing structured JSON logging, visible with `docker compose logs backend` -
this project's already-established log-viewing mechanism (Phase 19). Failures are logged with full
tracebacks (`logger.exception`) and also persisted to `CloudProviderAccount.last_discovery_error`.

## 5. Live verification against a real, already-connected AWS account

Using an account already connected to this platform instance before this phase began (real credentials,
already encrypted at rest - no new secrets were requested or exposed), a real discovery run was executed
directly through `CloudResourceDiscoveryService` (the exact code path the API uses):

- **Result**: real VPC, 3 real subnets, and 5 real security groups (including `launch-wizard-1` through
  `launch-wizard-5` - names AWS's own Console auto-generates specifically when an instance is launched
  through the EC2 launch wizard) were discovered and persisted in `ap-south-1`, confirming genuine API
  connectivity, correct credential usage, and correct persistence end-to-end.
- **No EC2 instance was found** in `ap-south-1` (this account's configured region). As a further check,
  every one of this account's 17 enabled AWS regions was scanned with the same real credentials - no
  running or stopped instance was found in any of them. This is the platform working correctly (a real,
  honest "zero instances" result, not a bug) - the `launch-wizard-*` security groups being the only trace
  left behind is consistent with an instance having existed and since been terminated. **If an EC2
  instance is still expected, please confirm in the AWS Console that it's running under this same AWS
  account/credentials** (some AWS setups have multiple accounts, or the instance may have been launched
  under a different IAM user/root account than the access key connected here).
- Full backend regression executed immediately after: **690/690 passed** (663 pre-existing + 27 new
  Phase 29 tests), confirming zero regressions.

## 6. Testing

27 new backend tests: `test_aws_resource_inventory.py` (+9, all 8 new categories plus
`list_ec2_instances_detailed`, moto-verified), `test_aws_cloudwatch.py` (+4, disk/status-check parsing,
real CWAgent-percent-to-MB conversion, no-datapoints, missing-credentials), `test_cloud_resource_
discovery.py` (+8, upsert/appear-disappear, running-vs-stopped metrics gating, per-category failure
tolerance, ownership checks), `test_cloud_resource_discovery_api.py` (+5, the 3 new endpoints end to end
including the exact-failure-reason 422), `test_cloud_credential_validation.py` (+1, discovery fires
alongside region sync on connect). Full regression: 690/690 backend, 87/87 frontend, clean `tsc -b`.

## 7. Known, disclosed limitations

- Automatic discovery (persistence, auto-refresh, CloudWatch metrics) is AWS-only in this phase - every
  other provider's existing Phase 25C on-demand browse endpoint is unaffected and unchanged.
- CloudWatch metrics collection is EC2-only, matching the exact metric set requested (CPU/Network/Disk/
  StatusCheck/Memory) - ECS/Lambda/RDS have their own CloudWatch namespaces, not covered in this pass.
- S3 buckets are account-wide, not region-scoped (a real limitation of the S3 API itself, already
  disclosed since Phase 25C) - a bucket appears once regardless of which region triggered discovery.
