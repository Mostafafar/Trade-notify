import requests

API_KEY = "pdb9zpy2vxpdijlyx5x5"

# تست آدرس‌های مختلف
urls_to_test = [
    f"https://freecryptoapi.com/api/v1?api_key={API_KEY}",
    f"https://api.freecryptoapi.com/v1?api_key={API_KEY}",
    f"https://freecryptoapi.com/api/v1/getData.php?api_key={API_KEY}",
    f"https://api.freecryptoapi.com/v1/getData.php?api_key={API_KEY}",
]

for url in urls_to_test:
    try:
        response = requests.get(url, timeout=10)
        print(f"URL: {url}")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Success! Response: {response.text[:200]}")
        else:
            print(f"Error: {response.text[:200]}")
        print("-" * 50)
    except Exception as e:
        print(f"Error with {url}: {e}")
        print("-" * 50)
