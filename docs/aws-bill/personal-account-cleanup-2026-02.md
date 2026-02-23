# AWS Personal Account Cleanup — 2026-02-23

## Summary

All resources in the AWS **personal** account have been terminated. The Weather AI project has been fully migrated to the **GCC** account.

## February 2026 Bill (Personal Account)

| Service | Cost (USD) |
|---------|-----------|
| EC2 Compute (t3.medium + t3.xlarge + g4dn.xlarge) | $95.56 |
| S3 Storage (satellite .npy + models) | $70.67 |
| EC2 Other (EBS 270GB + EIP + network) | $27.51 |
| VPC | $6.88 |
| Tax (GST 9%) | $18.06 |
| Cost Explorer | $0.02 |
| **Total** | **$218.71** |

## Resources Deleted

### EC2 Instances (all terminated)

| Instance ID | Name | Type | EBS |
|------------|------|------|-----|
| i-004dffd96ed716316 | weather-ai-api-server | t3.medium | 20GB gp3 |
| i-0edc956bf2dc0c197 | weather-ai-download-server | t3.xlarge | 50GB gp2 |
| i-015b892aee4af2e6d | weather-ai-gpu-training | g4dn.xlarge | 200GB gp3 |

### Elastic IP

| IP | Allocation ID |
|----|---------------|
| 3.0.28.161 | eipalloc-0ef582dbbfe81fd2c |

### S3 Buckets

| Bucket | Size | Status |
|--------|------|--------|
| weather-ai-frontend-jinhui-20260126 | ~500KB | Deleted |
| weather-ai-models-de08370c | ~10GB+ | Deleting |

### CloudFront

| Distribution ID | Domain | Status |
|----------------|--------|--------|
| E3NTCXM5BZ2EUY | d1em23i2wkbin3.cloudfront.net | Disabled (pending delete) |

### Not Found (no resources)

- RDS: none
- Lambda: none
- NAT Gateway: none
- ALB/NLB: none

## GCC Account Resources (active)

All production resources now run on the GCC account:

| Resource | Instance | IP |
|----------|----------|-----|
| API Server | EC2 | 13.228.95.52 |
| Download Server | EC2 | 52.221.178.169 |
| S3 Bucket | weather-ai-models-gcc | — |

## Expected Savings

- **Before cleanup**: ~$220/month (Feb actual)
- **After cleanup**: $0/month on personal account
- **GCC account**: managed separately under government billing
