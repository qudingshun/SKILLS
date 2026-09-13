import os, sys, json, base64, time
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CRED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cred.json")
URL = "https://w1.v2free.cyou/auth/login"


def save_cred(account, password):
    data = {
        "account": base64.b64encode(account.encode()).decode(),
        "password": base64.b64encode(password.encode()).decode(),
    }
    with open(CRED_FILE, "w") as f:
        json.dump(data, f)
    print("Credentials saved to cred.json (base64 encoded)")


def load_cred():
    if not os.path.exists(CRED_FILE):
        return None, None
    with open(CRED_FILE) as f:
        data = json.load(f)
    account = base64.b64decode(data["account"]).decode()
    password = base64.b64decode(data["password"]).decode()
    return account, password


def click_confirm_button(driver, selector=None):
    """点击确认按钮，防止跳转，仅关闭弹窗"""
    if selector is None:
        selector = "result_ok"

    try:
        current_url = driver.current_url
        btn = driver.find_element(By.ID, selector)

        # 使用 JavaScript 点击，绕过元素不可交互/零大小的问题
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(2)

        # 如果点击后 URL 变了（跳转到了 FAQ），恢复原页面
        if driver.current_url != current_url:
            print(f"Button caused navigation to {driver.current_url}, restoring to {current_url}")
            driver.get(current_url)
            time.sleep(2)

        print(f"Clicked confirm button (id={selector})")
        return True
    except Exception as e:
        print(f"Could not click confirm button ({selector}): {e}")
        return False


def find_and_click_overlay_button(driver):
    """查找并点击公告/弹窗的确认按钮"""
    
    # 尝试用 JavaScript 找到 modal 内的按钮
    buttons = driver.execute_script('''
        var modals = document.querySelectorAll('.modal');
        for (var i = 0; i < modals.length; i++) {
            var modal = modals[i];
            // 查找 modal 内的所有按钮
            var btns = modal.querySelectorAll('button, [role="button"]');
            if (btns.length > 0) {
                console.log("Found buttons in modal:", Array.from(btns).map(function(b) { return b.outerHTML; }));
                // 返回第一个按钮
                return btns[0];
            }
        }
        return null;
    ''')
    
    if buttons:
        print(f"Found overlay button via JavaScript!")
        try:
            # 使用 JavaScript 点击找到的按钮
            driver.execute_script("arguments[0].click();", buttons)
            print("Clicked announcement modal confirmation!")
            time.sleep(2)
            return True
        except Exception as e:
            print(f"Could not click via JS: {e}")
    
    # 尝试其他选择器作为备选
    selectors = [
        ".modal button",
        "[class*='modal'] button",
        "button.close, .close-btn",
        "button.confirm, .confirm-btn"
    ]
    
    for selector in selectors:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            print(f"Found overlay button via CSS: {selector}")
            
            wait = WebDriverWait(driver, 3)
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            
            # 使用 JavaScript 点击（更可靠）
            driver.execute_script("arguments[0].click();", btn)
            print(f"Clicked overlay button!")
            time.sleep(1)
            return True
        except Exception:
            continue
    
    print("Could not find overlay confirmation button")
    return False


def main():
    account, password = load_cred()

    if not account or not password:
        account = os.environ.get("V2FREE_ACCOUNT")
        password = os.environ.get("V2FREE_PASSWORD")

    if not account or not password:
        print("Credentials not found.")
        account = input("Account (email): ").strip()
        password = input("Password: ").strip()
        save = input("Save to cred.json? (y/N): ").strip().lower()
        if save == "y":
            save_cred(account, password)

    options = Options()
    options.use_chromium = True
    driver = webdriver.Edge(options=options)

    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 10)

        # Wait for login button and fill credentials
        btn = wait.until(EC.element_to_be_clickable((By.ID, "login")))
        email = driver.find_element(By.ID, "email")
        passwd = driver.find_element(By.ID, "passwd")

        email.clear()
        email.send_keys(account)
        passwd.clear()
        passwd.send_keys(password)

        btn.click()
        print("Clicked login button!")

        # Wait for a bit to see if success popup appears
        time.sleep(2)

        # Check current URL
        try:
            current_url = driver.current_url
            print(f"Current URL: {current_url}")

            if "/user" in current_url or "user" in current_url.lower():
                print("Login successful! Looking for confirm button...")

                # Try to click confirm button (login success)
                click_confirm_button(driver)
                
                # Wait longer for page to settle and modal to appear
                time.sleep(5)
                
                # Check if there's an overlay or modal element
                modals = driver.execute_script('''
                    return Array.from(document.querySelectorAll('.modal, .overlay'));
                ''')
                print(f"Found {len(modals)} modal/overlay elements")
                
                if len(modals) > 0:
                    # Try to find close/confirm button in overlay (only first one)
                    try:
                        confirm_btn = driver.find_element(By.CSS_SELECTOR, "button.close, .close-btn, [role='button']")
                        print(f"Found confirm/close button!")
                        confirm_btn.click()
                        print("Clicked announcement confirmation!")
                        time.sleep(3)
                        
                        # Check if modal still exists after clicking
                        remaining_modals = driver.execute_script('''
                            return Array.from(document.querySelectorAll('.modal, .overlay'));
                        ''')
                        if len(remaining_modals) == 0:
                            print("Successfully closed all modals!")
                        else:
                            print(f"Still {len(remaining_modals)} modal(s) remaining")
                    except Exception as e3:
                        print(f"No close button found in modal: {e3}")
        except Exception as e:
            print(f"Could not get URL: {e}")

        # Wait for result page to load
        time.sleep(3)

        # Try to get user info from page
        try:
            name_elem = driver.find_element(By.ID, "name")
            print(f"User name: {name_elem.text}")
        except Exception as e:
            pass

        try:
            email_elem = driver.find_element(By.ID, "email")
            print(f"User email: {email_elem.text}")
        except Exception as e:
            pass
        
        # Wait longer for the page to settle after login confirmation
        time.sleep(3)
        
        # Check if there's still a modal/overlay
        modals = driver.execute_script('''
            return Array.from(document.querySelectorAll('.modal, .overlay'));
        ''')
        
        if len(modals) > 0:
            print("Modal still exists! Trying to close it...")
            if find_and_click_overlay_button(driver):
                print("Successfully closed announcement modal!")
                time.sleep(2)

        print("\n浏览器已保持打开，请手动关闭。")
    finally:
        pass


if __name__ == "__main__":
    main()
