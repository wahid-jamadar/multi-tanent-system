import requests
import urllib3
import re
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create a session to persist cookies
session = requests.Session()

# 1. Login to Central Auth Portal
login_url = "https://172.100.30.191:8000/api/auth/login"
login_payload = {
    "email": "admin",
    "password": "admin@123"
}

print("Attempting to login to Central Auth Portal...")
r = session.post(login_url, json=login_payload, verify=False)
print("Login Status:", r.status_code)
print("Login Response:", r.json())

# 2. Launch FileBridge System
launch_url = "https://172.100.30.191:8000/api/auth/launch"
r_launch = session.post(launch_url, json={"system": "filebridge"}, verify=False)
print("Launch Status:", r_launch.status_code)
launch_data = r_launch.json()
print("Launch Response:", launch_data)

if "launch_url" in launch_data:
    print("Waiting 6 seconds for the background FileBridge server to start...")
    time.sleep(6)
    
    sso_url = launch_data["launch_url"]
    print("SSO Token URL:", sso_url)
    
    # 3. Authenticate with FileBridge via SSO
    print("Authenticating with FileBridge via SSO...")
    r_sso = session.get(sso_url, verify=False)
    print("SSO Auth Status:", r_sso.status_code)
    
    # 4. Request the FileBridge Dashboard
    dashboard_url = "https://172.100.30.191:5001/dashboard"
    r_dash = session.get(dashboard_url, verify=False)
    print("Dashboard Status:", r_dash.status_code)
    
    html = r_dash.text
    print("Length of HTML retrieved:", len(html))
    
    # Save retrieved HTML to file for inspection
    with open("scratch/filebridge_output.html", "w", encoding="utf-8") as f_out:
        f_out.write(html)
    print("Saved retrieved HTML to scratch/filebridge_output.html")
    
    # Search for our widget in the retrieved HTML
    if "quick-nav-widget" in html:
        print("[SUCCESS] Found 'quick-nav-widget' in the rendered HTML!")
        
        # Print the widget section
        start_idx = html.find("<!-- Floating Navigation Widget -->")
        if start_idx != -1:
            print("\n--- Rendered Widget HTML ---")
            print(html[start_idx:start_idx+1200])
            print("----------------------------\n")
        else:
            print("[WARNING] 'quick-nav-widget' was found, but the comment start tag was not.")
    else:
        print("[FAIL] 'quick-nav-widget' is NOT present in the retrieved HTML!")
else:
    print("[FAIL] SSO launch URL not found in response.")
