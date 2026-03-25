import pandas as pd
import requests

def test_screener():
    url = "https://www.screener.in/company/HINDUNILVR/consolidated/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        try:
            tables = pd.read_html(response.text)
            print(f"Success! Found {len(tables)} tables.")
            if tables:
                print("First table columns:", tables[0].columns.tolist())
        except Exception as e:
            print(f"Error parsing tables: {e}")
            
if __name__ == "__main__":
    test_screener()
