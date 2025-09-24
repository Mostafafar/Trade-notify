import requests

API_KEY = "pdb9zpy2vxpdijlyx5x5"

# تست با symbol
url = f"https://api.freecryptoapi.com/v1/getData.php?api_key={API_KEY}&symbol=BTC"

response = requests.get(url, timeout=10)
print(f"URL: {url}")
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")

# تست بدون symbol برای گرفتن لیست همه ارزها
url_all = f"https://api.freecryptoapi.com/v1/getData.php?api_key={API_KEY}"
response_all = requests.get(url_all, timeout=10)
print(f"\nURL (all): {url_all}")
print(f"Status: {response_all.status_code}")
print(f"Response: {response_all.text[:500]}")
