import uvicorn
import time
import multiprocessing
from playwright.sync_api import sync_playwright


def run_server():
    from api.router import create_app

    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="error")


if __name__ == "__main__":
    proc = multiprocessing.Process(target=run_server)
    proc.start()
    time.sleep(2)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto("http://127.0.0.1:8001")
            page.wait_for_timeout(2000)
            page.screenshot(path="dashboard_redesign.png", full_page=True)
            browser.close()
        print("Screenshot saved to dashboard_redesign.png")
    finally:
        proc.terminate()
        proc.join()
