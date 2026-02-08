import boto3
import os
import sys

def test_s3():
    bucket = os.environ.get("S3_BUCKET")
    region = os.environ.get("AWS_DEFAULT_REGION")
    print(f"Testing S3 Connection to Actual AWS...")
    print(f"Bucket: {bucket}")
    print(f"Region: {region}")
    
    if not bucket:
        print("❌ Error: S3_BUCKET not set. Did you source prod_env_setup.sh?")
        return

    try:
        # Create client (picks up env vars automatically)
        s3 = boto3.client('s3')
        
        # 1. Check Bucket Existence (Head)
        print("1. Checking Bucket Access...")
        try:
            s3.head_bucket(Bucket=bucket)
            print("   ✅ Bucket found and accessible.")
        except Exception as e:
            print(f"   ❌ Access Failed: {e}")
            if "403" in str(e):
                print("      (Tip: Check AWS Access Key permissions)")
            if "404" in str(e):
                print("      (Tip: Bucket does not exist in this region)")
            return

        # 2. List Objects
        print("2. Listing Objects...")
        try:
            resp = s3.list_objects_v2(Bucket=bucket, MaxKeys=5)
            count = resp.get('KeyCount', 0)
            print(f"   ✅ Listed {count} objects.")
        except Exception as e:
            print(f"   ❌ List Failed: {e}")

        # 3. Write Test
        print("3. Writing Test Object (test_connection.txt)...")
        try:
            s3.put_object(Bucket=bucket, Key="test_connection.txt", Body=b"Hello S3")
            print("   ✅ Write successful.")
        except Exception as e:
            print(f"   ❌ Write Failed: {e}")
            return
        
        # 4. Read Test
        print("4. Reading Test Object...")
        try:
            obj = s3.get_object(Bucket=bucket, Key="test_connection.txt")
            content = obj['Body'].read().decode('utf-8')
            if content == "Hello S3":
                print("   ✅ Read successful.")
            else:
                print("   ❌ Read content mismatch.")
        except Exception as e:
            print(f"   ❌ Read Failed: {e}")
            
        # 5. Delete Test
        try:
            s3.delete_object(Bucket=bucket, Key="test_connection.txt")
            print("   ✅ Cleanup successful.")
        except Exception as e:
            print(f"   ⚠️ Cleanup Failed: {e}")
        
        print("\n🎉 Connection Verified! Your environment is correctly using AWS S3.")
        
    except Exception as e:
        print(f"\n❌ Client Initialization Failed: {e}")
        print("Please check 'aws configure' or your exported keys.")

if __name__ == "__main__":
    test_s3()
