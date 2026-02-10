import requests

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")

def brave_search(query):
    url = f"https://api.search.brave.com/res/v1/web/search?q={query}"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY
    }

    res = requests.get(url, headers=headers)

    print(f"🔍 Brave Query: {query}")
    print(f"🔍 Status Code: {res.status_code}")
    
    if res.status_code != 200:
        print(f"❌ Brave Search failed. Response:\n{res.text}")
        return

    data = res.json()
    results = data.get("web", {}).get("results", [])
    
    if not results:
        print("⚠️ No results found.")
    else:
        print("\n🧠 Top Results:\n")
        for r in results[:5]:
            print(f"Title: {r.get('title')}")
            print(f"Description: {r.get('description')}")
            print("-" * 40)

# Test the function
if __name__ == "__main__":
    test_query = input("Enter a Brave search query: ")
    brave_search(test_query)
