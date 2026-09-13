"""
Debug script - test SCM login and see what happens
"""
import asyncio
from playwright.async_api import async_playwright
import base64
import ddddocr

USERNAME = "hsa697"
PASSWORD = "***REMOVED***"
SCM_URL = "https://scm.whirlpool-china.com:7580/websrm/"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="msedge")
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto(SCM_URL, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3)

        print("URL:", page.url)

        # Fill login
        el = await page.wait_for_selector("#username", timeout=10000)
        await el.click()
        await el.fill("")
        await el.fill(USERNAME)

        el = await page.wait_for_selector("#password", timeout=5000)
        await el.fill("")
        await el.fill(PASSWORD)

        # Get captcha
        img_b64 = await page.evaluate("""async () => {
            var img = document.querySelector('#changeCode');
            if (!img) return null;
            var r = await fetch(img.src + '?' + Date.now(), {cache: 'no-cache'});
            var b = await r.blob();
            return new Promise(function(resolve) {
                var reader = new FileReader();
                reader.onloadend = function() { resolve(reader.result); };
                reader.readAsDataURL(b);
            });
        }""")

        if img_b64 and "," in img_b64:
            img_bytes = base64.b64decode(img_b64.split(",")[1])
            with open("C:\\Users\\qudin\\.openclaw\\workspace\\captcha.png", "wb") as f:
                f.write(img_bytes)
            ocr = ddddocr.DdddOcr(show_ad=False)
            result = ocr.classification(img_bytes)
            captcha_text = result.strip() if result else ""
            print(f"Captcha image size: {len(img_bytes)} bytes")
            print(f"OCR result: [{captcha_text}] (len={len(captcha_text)})")

            # Fill captcha
            el = await page.query_selector("#kaptcha")
            if el:
                await el.fill("")
                await el.fill(captcha_text)
        else:
            print("Failed to get captcha image")
            await browser.close()
            return

        # Click login
        for sel in [
            "input[name='CPCLogin']",
            ".sub_btn",
            "input[type='submit']",
        ]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    print(f"Clicked: {sel}")
                    break
            except Exception:
                continue
        else:
            await page.keyboard.press("Enter")

        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3)

        print(f"After login URL: {page.url}")

        # Check what elements exist
        info = await page.evaluate(
            """() => {
            var u = document.querySelector('#username');
            var p = document.querySelector('input[type="password"]');
            var k = document.querySelector('#kaptcha');
            return {
                hasUsername: u !== null,
                usernameVisible: u ? u.offsetParent !== null : false,
                hasPassword: p !== null,
                hasKaptcha: k !== null,
                pageText: document.body.innerText.substring(0, 500)
            };
        }"""
        )
        print(f"Login state: {info}")

        await page.screenshot(
            path="C:\\Users\\qudin\\.openclaw\\workspace\\scm_after_login.png"
        )
        await browser.close()


asyncio.run(main())
