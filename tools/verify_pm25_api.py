import requests
import json
import datetime

# Try the standard v1 endpoint first
BASE_URL = "https://api.data.gov.sg/v1/environment/pm25"

def check_pm25():
    # Use yesterday's date
    date_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    params = {"date": date_str}
    
    print(f"Checking {BASE_URL} for {date_str}...")
    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            # print(json.dumps(data, indent=2)[:500]) # Print first 500 chars
            
            if 'items' in data and len(data['items']) > 0:
                print("Examples item structure:")
                item = data['items'][0]
                print(json.dumps(item, indent=2))
                return True
            else:
                print("No items found.")
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Exception: {e}")
        
    return False

if __name__ == "__main__":
    check_pm25()
