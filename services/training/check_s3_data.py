import boto3
s3 = boto3.client('s3', region_name='ap-southeast-1')
bucket = 'weather-ai-models-gcc'

# List top-level structure
resp = s3.list_objects_v2(Bucket=bucket, Delimiter='/', MaxKeys=100)
print('Top-level prefixes:')
for p in resp.get('CommonPrefixes', []):
    print(f"  {p['Prefix']}")

# Check rainy dates
dates = ['2026-01-07', '2026-01-16', '2026-02-05']
print('\nChecking rainy dates:')
for date in dates:
    y, m, d = date.split('-')
    found = False
    for prefix_tmpl in ['processed/{}/{}/{}/','satellite/{}/{}/{}/','data/{}/{}/{}/']:
        prefix = prefix_tmpl.format(y, m, d)
        try:
            r = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=5)
            if r.get('KeyCount', 0) > 0:
                print(f"  {date}: {r['KeyCount']} files at {prefix}")
                found = True
                break
        except:
            pass
    if not found:
        print(f"  {date}: NO data found")

# List available 2026 dates
print('\nAvailable 2026 months:')
for prefix in ['processed/2026/', 'satellite/2026/', 'data/2026/']:
    try:
        r = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter='/', MaxKeys=100)
        for p in r.get('CommonPrefixes', []):
            print(f"  {p['Prefix']}")
    except:
        pass

# Also check what the training scheduler downloads - look at processed_data dir
import os
print('\nLocal satellite data:')
sat_dir = os.path.expanduser('~/weather-ai/satellite_data')
if os.path.exists(sat_dir):
    files = sorted(os.listdir(sat_dir))[-10:]
    print(f"  Total files: {len(os.listdir(sat_dir))}")
    print(f"  Latest: {files}")
else:
    print("  No local satellite_data dir")

# Check processed_data
proc_dir = os.path.expanduser('~/weather-ai/processed_data')
if os.path.exists(proc_dir):
    files = sorted(os.listdir(proc_dir))[-10:]
    print(f"\nProcessed data: {len(os.listdir(proc_dir))} files")
    print(f"  Latest: {files}")
