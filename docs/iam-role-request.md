# IAM Role Request — Weather AI (Databricks on AWS)

> **Requestor**: Jin Hui
> **Date**: 2026-02-20
> **Target Account**: GCC-sponsored AWS Account
> **Purpose**: Operate Databricks for the Singapore Weather AI project

---

## Role 1: Databricks Cross-Account Role

**Role Name**: `DatabricksCrossAccountRole`
**Trusted Principal**: Databricks AWS Account (provided during Workspace setup)
**Purpose**: Allows the Databricks control plane to provision and manage EC2 clusters in our VPC.

### Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EC2ClusterManagement",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceTypes",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "ec2:CreateSecurityGroup",
        "ec2:DeleteSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:CreateTags",
        "ec2:DescribeImages",
        "ec2:DescribeSpotPriceHistory"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DatabricksRootStorage",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::gcc-databricks-root-storage",
        "arn:aws:s3:::gcc-databricks-root-storage/*"
      ]
    }
  ]
}
```

### Trust Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::414351767826:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<provided-by-databricks-during-setup>"
        }
      }
    }
  ]
}
```

> **Note**: `414351767826` is the Databricks production AWS account ID. The ExternalId will be generated during Workspace creation.

---

## Role 2: EC2 Instance Profile for Clusters

**Role Name**: `DatabricksClusterInstanceRole`
**Attached To**: EC2 Instance Profile used by Databricks cluster nodes
**Purpose**: Grants Databricks cluster nodes access to S3 data (both local and cross-account).

### Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "LocalProjectBucketAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::gcc-weather-ai-*",
        "arn:aws:s3:::gcc-weather-ai-*/*"
      ]
    },
    {
      "Sid": "CrossAccountSourceBucketRead",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::weather-ai-models-de08370c",
        "arn:aws:s3:::weather-ai-models-de08370c/*"
      ]
    }
  ]
}
```

### Trust Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

---

## Role 3: User IAM Role (for CLI and local access)

**Role Name**: `DatabricksUserRole`
**Attached To**: IAM user or assumed via SSO
**Purpose**: Allows the developer to use AWS CLI and Databricks CLI from a local machine.

### Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3DataAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::gcc-weather-ai-*",
        "arn:aws:s3:::gcc-weather-ai-*/*"
      ]
    },
    {
      "Sid": "CrossAccountDataMigration",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::weather-ai-models-de08370c",
        "arn:aws:s3:::weather-ai-models-de08370c/*"
      ]
    },
    {
      "Sid": "PassRoleToDatabricks",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/DatabricksClusterInstanceRole"
    }
  ]
}
```

---

## Summary Table

| Role | Trusted By | Key Permissions | Purpose |
|------|-----------|-----------------|---------|
| **DatabricksCrossAccountRole** | Databricks Control Plane | EC2 management, Root S3 | Databricks provisions clusters |
| **DatabricksClusterInstanceRole** | EC2 Service | S3 read/write (local + cross-account) | Cluster nodes access data |
| **DatabricksUserRole** | IAM User / SSO | S3 access, PassRole | Developer CLI and data migration |
