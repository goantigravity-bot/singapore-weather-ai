import socket
import requests
import sys
import time

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def check_port_open(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0

def verify_service(name, url):
    print(f"Checking {name} at {url}...")
    try:
        # User-Agent is important for some dev servers
        headers = {'User-Agent': 'VerificationScript'} 
        response = requests.get(url, timeout=2, headers=headers)
        if response.status_code == 200:
            print(f"✅ {name} is reachable and healthy (Status 200).")
            return True
        else:
            print(f"⚠️ {name} is reachable but returned status {response.status_code}.")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ {name} is NOT reachable. Error: {e}")
        return False

def main():
    print("="*40)
    print("      DEPLOYMENT VERIFICATION")
    print("="*40)
    
    local_ip = get_ip_address()
    print(f"Detected LAN IP: {local_ip}")
    print("-" * 40)

    # 1. Check Backend (API)
    api_port = 8000
    if check_port_open('127.0.0.1', api_port):
        print(f"✅ Backend Port {api_port} is OPEN on Localhost.")
    else:
        print(f"❌ Backend Port {api_port} is CLOSED on Localhost.")

    # Check external access
    api_url = f"http://{local_ip}:{api_port}/health"
    backend_ok = verify_service("Backend API (LAN)", api_url)

    print("-" * 40)

    # 2. Check Frontend
    frontend_port = 5173
    if check_port_open('127.0.0.1', frontend_port):
        print(f"✅ Frontend Port {frontend_port} is OPEN on Localhost.")
    else:
        print(f"❌ Frontend Port {frontend_port} is CLOSED on Localhost.")
        
    frontend_url = f"http://{local_ip}:{frontend_port}/"
    frontend_ok = verify_service("Frontend (LAN)", frontend_url)
    
    print("="*40)
    if backend_ok and frontend_ok:
        print("🎉 verification PASSED: System is accessible over network.")
        sys.exit(0)
    else:
        print("failed verification FAILED: One or more services are not accessible.")
        print("Tip: Ensure services are started with '--host 0.0.0.0' or '--host'.")
        sys.exit(1)

if __name__ == "__main__":
    main()
