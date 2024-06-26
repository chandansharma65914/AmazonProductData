from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
import httpx
import re

app = FastAPI()

class ASINRequest(BaseModel):
    asin: str

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.64",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 OPR/77.0.4054.90",
]

@app.get("/")
def read_root():
    return {"message": "Welcome to the Amazon Product Data API"}

@app.head("/")
def head_root():
    pass  # No need to return anything for HEAD requests

@app.options("/")
def options_root():
    return {"methods": ["GET", "HEAD", "OPTIONS"]}  # Provide information about allowed methods

@app.post("/api/product")
async def get_product_details(data: ASINRequest):
    user_agent_index = 0  # Initialize user agent index

    result = await crawl_by_id(data.asin, user_agent_index)

    return result

async def crawl_by_id(id: str, user_agent_index: int):
    o = {}
    target_url = f"https://www.amazon.com/dp/{id}"

    headers = {
        "accept-language": "en-US,en;q=0.9",
        "accept-encoding": "gzip, deflate, br",
        "User-Agent": USER_AGENTS[user_agent_index],
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(target_url, headers=headers)

        if resp.status_code != 200:
            return {'error': f'Failed to fetch data for ASIN: {id}'}

        soup = BeautifulSoup(resp.text, 'html.parser')

        try:
            o["title"] = soup.find('h1', {'id': 'title'}).text.strip()
        except:
            o["title"] = None

        # Extract high-resolution images using regex
        images = re.findall('"hiRes":"(.+?)"', resp.text)
        o["thumbnail"] = images[0] if images else None

        # Additional extraction for 'src', 'data-old-hires', and 'data-a-dynamic-image' attributes
        if not o["thumbnail"]:
            img_tag = soup.find('img', {'id': 'landingImage'})
            if img_tag:
                o["thumbnail"] = img_tag.get('src')
                if not o["thumbnail"]:
                    o["thumbnail"] = img_tag.get('data-old-hires')
                if not o["thumbnail"] and img_tag.get('data-a-dynamic-image'):
                    dynamic_images = re.findall(r'"(https://[^"]+)"', img_tag.get('data-a-dynamic-image'))
                    o["thumbnail"] = dynamic_images[0] if dynamic_images else None

        # Check if the product is unavailable or out of stock
        availability = soup.find("div", {"id": "availability"})
        if availability and "Currently unavailable" in availability.text:
            o["price"] = None
        else:
            try:
                o["price"] = soup.find("span", {"class": "a-price"}).find("span").text
            except:
                o["price"] = None

        try:
            o["productDescription"] = soup.find("div", {"id": "productDescription"}).text.strip()
        except:
            o["productDescription"] = None

        # Rotate user agent index for the next request
        user_agent_index = (user_agent_index + 1) % len(USER_AGENTS)

        return o
    except httpx.RequestError as exc:
        return {'error': f'An error occurred while requesting {exc.request.url!r}.'}
