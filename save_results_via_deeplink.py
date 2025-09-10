import asyncio
import os
import urllib.parse
import argparse
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent

# Define potential output paths for the HTML file
OUT_PATHS = [
    HERE / "manual_search.html",
    Path("/tmp/manual_search.html"),
]

async def main(args):
    """
    Main function to launch browser, navigate, and save page content.
    """
    base = "[https://www.southwest.com/air/booking/select.html](https://www.southwest.com/air/booking/select.html)"
    params = {
        "originationAirportCode": args.origin,
        "destinationAirportCode": args.destination,
        "departureDate": args.depart_date,
        "tripType": args.trip_type,
        "adultPassengersCount": "1",
        "reset": "true",
    }

    if args.trip_type.lower() == "roundtrip":
        params["returnDate"] = args.return_date

    url = base + "?" + urllib.parse.urlencode(params)
    print(f"Navigating to: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # Wait for either the flight results or the "no flights" message
            await page.locator(
                '[data-qa*="flight"], [role="table"] [role="row"], .swa-g-p-10-md-15'
            ).first.wait_for(timeout=60000)
            
            html = await page.content()

            wrote_path = None
            for pth in OUT_PATHS:
                try:
                    pth.write_text(html, encoding="utf-8")
                    os.chmod(pth, 0o666)
                    print(f"[OK] Wrote search results to {pth}")
                    wrote_path = pth
                    break 
                except Exception as e:
                    print(f"[WARN] Could not write to {pth}: {e}")

            if not wrote_path:
                print("[ERROR] Failed to write HTML output to any path.")

        except Exception as e:
            print(f"[ERROR] An error occurred during scraping: {e}")
            await page.screenshot(path="error_screenshot.png")
            print("Screenshot saved to error_screenshot.png")

        finally:
            await ctx.close()
            await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Southwest flight results.")
    parser.add_argument("--trip-type", required=True, help="oneway or roundtrip")
    parser.add_argument("--origin", required=True, help="Origin airport code (e.g., IND)")
    parser.add_argument("--destination", required=True, help="Destination airport code (e.g., PHX)")
    parser.add_argument("--depart-date", required=True, help="Departure date (YYYY-MM-DD)")
    parser.add_argument("--return-date", help="Return date (YYYY-MM-DD), required for roundtrip")

    args = parser.parse_args()

    if args.trip_type.lower() == "roundtrip" and not args.return_date:
        parser.error("--return-date is required for roundtrip")

    asyncio.run(main(args))