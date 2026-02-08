import socket
import requests
import sys
import time

def check_port(host, port, service_name):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f"✅ [PASS] {service_name} Port {port} is OPEN.")
            return True
        else:
            print(f"❌ [FAIL] {service_name} Port {port} is CLOSED.")
            return False
    except Exception as e:
        print(f"❌ [FAIL] Error checking {service_name}: {e}")
        return False

def check_http(url, service_name):
    print(f"   Testing HTTP {url}...")
    try:
        resp = requests.get(url, timeout=10) # Increased timeout for model loading
        if resp.status_code in [200, 401, 403, 404]: # Any response means service is up
            print(f"✅ [PASS] {service_name} is responding (Status {resp.status_code}).")
            return True
        else:
            print(f"⚠️ [WARN] {service_name} returned unexpected status {resp.status_code}.")
            return True
    except requests.exceptions.ConnectionError:
        print(f"❌ [FAIL] {service_name} Connection Refused.")
        return False
    except Exception as e:
        print(f"❌ [FAIL] {service_name} Error: {e}")
        return False

def main():
    print("="*40)
    print("      DOCKER STACK VERIFICATION")
    print("="*40)
    
    all_pass = True
    
    # 1. MinIO
    if not check_port("localhost", 9000, "MinIO API"): all_pass = False
    if not check_port("localhost", 9001, "MinIO Console"): all_pass = False
    # MinIO Health Check
    # if not check_http("http://localhost:9000/minio/health/live", "MinIO Health"): all_pass = False

    print("-" * 40)

    # 2. API Server
    if check_port("localhost", 8000, "API Server"):
        # Check Endpoint
        if not check_http("http://localhost:8000/docs", "API Docs"): all_pass = False
        # if not check_http("http://localhost:8000/health", "API Health"): all_pass = False
    else:
        all_pass = False

    print("="*40)
    if all_pass:
        print("🎉 SUCCESS: All services appear to be running.")
        print("   - API Docs: http://localhost:8000/docs")
        print("   - MinIO Console: http://localhost:9001 (minioadmin/minioadmin)")
        sys.exit(0)
    else:
        print("❌ FAILURE: Some services are not accessible.")
        print("   Tip: Check 'docker-compose logs' for errors.")
        sys.exit(1)

if __name__ == "__main__":
    main()
