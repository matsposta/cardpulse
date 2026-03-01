"""
CardPulse backend — eBay Finding + Trading API with credentials from env.
Run: uvicorn app.main:app --reload
"""
import os
import base64
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx

load_dotenv()

app = FastAPI(title="CardPulse API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# eBay config from env
EBAY_ENV = os.getenv("EBAY_ENV", "production").lower()
CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")

URLS = {
    "sandbox": {
        "token": "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
        "finding": "https://svcs.sandbox.ebay.com/services/search/FindingService/v1",
        "trading": "https://api.sandbox.ebay.com/ws/api.dll",
    },
    "production": {
        "token": "https://api.ebay.com/identity/v1/oauth2/token",
        "finding": "https://svcs.ebay.com/services/search/FindingService/v1",
        "trading": "https://api.ebay.com/ws/api.dll",
    },
}

SPORTS_CARDS_CATEGORY = "212"
TRADING_API_VERSION = "967"
BATCH_SIZE = 20

_token: Optional[str] = None


def _get_token() -> str:
    """OAuth client_credentials token (cached in memory)."""
    global _token
    if _token:
        return _token
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in .env",
        )
    urls = URLS.get(EBAY_ENV, URLS["production"])
    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    with httpx.Client() as client:
        r = client.post(
            urls["token"],
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope",
        )
    r.raise_for_status()
    data = r.json()
    _token = data["access_token"]
    return _token


def _find_items(keyword: str) -> list[dict]:
    """Finding API findItemsAdvanced — auctions, sports cards, ending soonest."""
    urls = URLS.get(EBAY_ENV, URLS["production"])
    params = {
        "OPERATION-NAME": "findItemsAdvanced",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": CLIENT_ID,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": keyword or "sports card rookie",
        "categoryId": SPORTS_CARDS_CATEGORY,
        "sortOrder": "EndTimeSoonest",
        "paginationInput.entriesPerPage": "48",
        "itemFilter(0).name": "ListingType",
        "itemFilter(0).value": "Auction",
        "outputSelector(0)": "PictureURLLarge",
        "outputSelector(1)": "SellerInfo",
    }
    qs = urlencode(params, safe="()")
    with httpx.Client() as client:
        r = client.get(f"{urls['finding']}?{qs}")
    if r.status_code != 200:
        err_body = r.text[:500] if r.text else r.reason_phrase
        hint = "If 500: ensure your app has Production access (developer.ebay.com → Your app → Request Production). Use EBAY_ENV=sandbox + Sandbox keys to test."
        raise HTTPException(status_code=502, detail=f"eBay Finding API {r.status_code}. {hint} Response: {err_body}")
    data = r.json()
    root = data.get("findItemsAdvancedResponse", [{}])[0]
    ack = root.get("ack", [""])[0]
    if ack not in ("Success", "Warning"):
        msg = (root.get("errorMessage", [{}])[0].get("error", [{}])[0].get("message", [""])[0]) or ack
        raise HTTPException(status_code=502, detail=msg)
    items = root.get("searchResult", [{}])[0].get("item", [])
    now_sec = time.time()
    listings = []
    for item in items:
        end_str = (item.get("listingInfo") or [{}])[0].get("endTime", [""])[0]
        try:
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            end_min = max(0, int((end_dt.timestamp() - now_sec) / 60))
        except Exception:
            end_min = 0
        selling = (item.get("sellingStatus") or [{}])[0]
        curr = (selling.get("currentPrice") or [{}])[0]
        price = float(curr.get("__value__") or 0)
        bids = int((selling.get("bidCount") or ["0"])[0])
        listings.append({
            "id": (item.get("itemId") or [""])[0],
            "title": (item.get("title") or ["Untitled"])[0],
            "price": price,
            "bids": bids,
            "watches": None,
            "watchesLoading": False,
            "endMin": end_min,
            "img": (item.get("galleryURL") or item.get("pictureURLLarge") or [None])[0],
            "url": (item.get("viewItemURL") or ["#"])[0],
            "condition": (item.get("condition") or [{}])[0].get("conditionDisplayName", [""])[0] or "",
        })
    return listings


def _enrich_watch_counts(listings: list[dict]) -> None:
    """Trading API GetMultipleItems — fill watches in batches of 20."""
    if not listings:
        return
    token = _get_token()
    urls = URLS.get(EBAY_ENV, URLS["production"])
    for i in range(0, len(listings), BATCH_SIZE):
        batch = listings[i : i + BATCH_SIZE]
        id_list = "".join(f"<ItemID>{l['id']}</ItemID>" for l in batch)
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMultipleItemsRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  {id_list}
  <IncludeSelector>Details</IncludeSelector>
</GetMultipleItemsRequest>"""
        with httpx.Client() as client:
            r = client.post(
                urls["trading"],
                headers={
                    "X-EBAY-API-SITEID": "0",
                    "X-EBAY-API-COMPATIBILITY-LEVEL": TRADING_API_VERSION,
                    "X-EBAY-API-CALL-NAME": "GetMultipleItems",
                    "X-EBAY-API-IAF-TOKEN": token,
                    "Content-Type": "text/xml",
                },
                content=body,
            )
        if r.status_code != 200:
            continue
        root = ET.fromstring(r.text)
        # eBay uses default ns; ElementTree adds it as {url}LocalName
        ns = "urn:ebay:apis:eBLBaseComponents"
        for item_el in root.findall(f".//{{{ns}}}Item") or root.findall(".//Item"):
            item_id_el = item_el.find(f"{{{ns}}}ItemID") or item_el.find("ItemID")
            watch_el = item_el.find(f"{{{ns}}}WatchCount") or item_el.find("WatchCount")
            if item_id_el is not None and item_id_el.text and watch_el is not None and watch_el.text:
                item_id = item_id_el.text.strip()
                try:
                    watch_count = int(watch_el.text.strip())
                except ValueError:
                    watch_count = None
                for l in listings:
                    if l["id"] == item_id:
                        l["watches"] = watch_count
                        break


@app.get("/api/status")
def api_status():
    """Check if backend and eBay API are configured and working. Use this to verify live data."""
    has_creds = bool(CLIENT_ID and CLIENT_SECRET)
    if not has_creds:
        return {
            "ok": False,
            "message": "EBAY_CLIENT_ID or EBAY_CLIENT_SECRET not set in env",
            "live_data": False,
        }
    try:
        listings = _find_items("sports card")
        count = len(listings)
        # Real eBay items have long numeric id and ebay.com url
        sample = listings[0] if listings else {}
        live_data = count > 0 and isinstance(sample.get("id"), str) and "ebay.com" in str(sample.get("url", ""))
        return {
            "ok": True,
            "message": "eBay API connected",
            "live_data": live_data,
            "listings_count": count,
            "env": EBAY_ENV,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
            "live_data": False,
        }


@app.get("/api/listings")
def get_listings(keyword: str = "sports card rookie"):
    """Return sports card auction listings with watch counts (eBay Finding + Trading API)."""
    try:
        listings = _find_items(keyword)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not listings:
        return {"listings": []}
    _enrich_watch_counts(listings)
    return {"listings": listings}


# Serve frontend at / (card-tracker.html auto-uses /api when served from this host)
FRONTEND_PATH = os.path.join(os.path.dirname(__file__), "..", "card-tracker.html")

@app.get("/")
def index():
    return FileResponse(FRONTEND_PATH)
