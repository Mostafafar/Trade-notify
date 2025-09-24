import requests

API_KEY = "pdb9zpy2vxpdijlyx5x5"
base_url = "https://api.freecryptoapi.com/v1"

# تست پارامترهای مختلف
test_params = [
    {"api_key": API_KEY, "symbol": "BTC"},
    {"api_key": API_KEY, "fsym": "BTC", "tsym": "USD"},
    {"api_key": API_KEY, "coin": "BTC"},
    {"api_key": API_KEY, "crypto": "BTC"},
    {"api_key": API_KEY, "currency": "BTC"},
    {"api_key": API_KEY}  # بدون پارامتر اضافی
]

for i, params in enumerate(test_params):
    try:
        url = f"{base_url}/getData.php"
        response = requests.get(url, params=params, timeout=10)
        print(f"Test {i+1}: {params}")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        print("-" * 50)
    except Exception as e:
        print(f"Test {i+1} Error: {e}")
        print("-" * 50)

# تست endpointهای مختلف
endpoints = [
    "/getData.php",
    "/getCryptoList.php", 
    "/getPrice.php",
    "/markets.php",
    "/cryptocurrencies.php"
]

for endpoint in endpoints:
    try:
        url = f"{base_url}{endpoint}"
        params = {"api_key": API_KEY}
        response = requests.get(url, params=params, timeout=10)
        print(f"Endpoint: {endpoint}")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Success! Length: {len(response.text)}")
            print(f"Preview: {response.text[:200]}")
        else:
            print(f"Error: {response.text[:200]}")
        print("=" * 50)
    except Exception as e:
        print(f"Endpoint {endpoint} Error: {e}")
        print("=" * 50)
