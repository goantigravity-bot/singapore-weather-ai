import boto3
s3 = boto3.client('s3', region_name='ap-southeast-1')
bucket = 'weather-ai-models-de08370c'

# Check what months of satellite data exist in S3
print('=== S3 Satellite Data (processed/) ===')
r = s3.list_objects_v2(Bucket=bucket, Prefix='processed/', Delimiter='/', MaxKeys=100)
for p in r.get('CommonPrefixes', []):
    print(f"  {p['Prefix']}")
    # Check sub-months
    r2 = s3.list_objects_v2(Bucket=bucket, Prefix=p['Prefix'], Delimiter='/', MaxKeys=100)
    for p2 in r2.get('CommonPrefixes', []):
        # Count files per month
        r3 = s3.list_objects_v2(Bucket=bucket, Prefix=p2['Prefix'], Delimiter='/', MaxKeys=100)
        dirs = r3.get('CommonPrefixes', [])
        print(f"    {p2['Prefix']} ({len(dirs)} days)")
        # List actual days
        for d in dirs:
            r4 = s3.list_objects_v2(Bucket=bucket, Prefix=d['Prefix'], MaxKeys=300)
            file_count = r4.get('KeyCount', 0)
            print(f"      {d['Prefix'].split('/')[-2]}: {file_count} files")

print('\n=== S3 Raw Satellite ===')
r = s3.list_objects_v2(Bucket=bucket, Prefix='satellite/', Delimiter='/', MaxKeys=100)
for p in r.get('CommonPrefixes', []):
    print(f"  {p['Prefix']}")
    r2 = s3.list_objects_v2(Bucket=bucket, Prefix=p['Prefix'], Delimiter='/', MaxKeys=100)
    for p2 in r2.get('CommonPrefixes', []):
        r3 = s3.list_objects_v2(Bucket=bucket, Prefix=p2['Prefix'], Delimiter='/', MaxKeys=100)
        print(f"    {p2['Prefix']} ({len(r3.get('CommonPrefixes', []))} days)")

print('\n=== S3 Gov Data (sensor) ===')
r = s3.list_objects_v2(Bucket=bucket, Prefix='govdata/', Delimiter='/', MaxKeys=100)
for p in r.get('CommonPrefixes', []):
    r2 = s3.list_objects_v2(Bucket=bucket, Prefix=p['Prefix'], Delimiter='/', MaxKeys=100)
    months = r2.get('CommonPrefixes', [])
    print(f"  {p['Prefix']} ({len(months)} months)")
    for m in months:
        r3 = s3.list_objects_v2(Bucket=bucket, Prefix=m['Prefix'], Delimiter='/', MaxKeys=100)
        days = r3.get('CommonPrefixes', [])
        print(f"    {m['Prefix']} ({len(days)} days)")
