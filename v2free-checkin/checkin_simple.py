"""
v2free 自动登录 - 简化版（仅到登录确认）
只运行到点击确认按钮完成登录，不处理后续弹窗
"""

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


def main():
    # 获取凭据
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

    # 启动浏览器
    options = Options()
    options.use_chromium = True
    driver = webdriver.Edge(options=options)

    try:
        print(f"Opening login page: {URL}")
        driver.get(URL)

        wait = WebDriverWait(driver, 10)

        # 等待登录按钮并填充凭据
        print("Waiting for login form...")

        # 检查是否有 Cloudflare 验证码页面
        time.sleep(3)
        current_url = driver.current_url

        if "cf-turnstile" in str(driver.page_source):
            print("Detected Cloudflare captcha!")
            # 等待验证码输入框出现
            try:
                # 查找验证码输入框
                captcha_input = driver.find_element(By.CSS_SELECTOR, "#cf-turnstile-root input")
                print("Found captcha input field")

                # 等待用户输入验证码（或者自动获取）
                time.sleep(2)
                user_captcha = input("Please enter Cloudflare captcha code: ").strip()
                if user_captcha:
                    captcha_input.send_keys(user_captcha)
                    print("Captcha entered!")
                    time.sleep(1)
            except Exception as e:
                print(f"Could not find captcha field: {e}")

        btn = wait.until(EC.element_to_be_clickable((By.ID, "login")))
        email = driver.find_element(By.ID, "email")
        passwd = driver.find_element(By.ID, "passwd")

        email.clear()
        email.send_keys(account)
        passwd.clear()
        passwd.send_keys(password)

        print("Filling credentials...")
        btn.click()
        print("Clicked login button!")

        # 等待登录结果（成功或失败）
        time.sleep(5)

        # 检查是否有 Cloudflare 验证码弹窗
        current_url = driver.current_url
        print(f"\nCurrent URL: {current_url}")

        # 检查当前页面是否有验证码输入框
        captcha_inputs = driver.execute_script('''
            return Array.from(document.querySelectorAll('#cf-turnstile-root input'));
        ''')

        if len(captcha_inputs) > 0:
            print("Found Cloudflare captcha input!")
            user_captcha = input("Please enter Cloudflare captcha code: ").strip()
            if user_captcha:
                try:
                    captcha_input = driver.find_element(By.ID, "cf-turnstile-root")
                    # 使用 JavaScript 输入验证码
                    driver.execute_script('''
                        var inputs = arguments[0].querySelectorAll('input');
                        for (var i = 0; i < inputs.length; i++) {
                            inputs[i].value = arguments[1];
                        }
                    ''', captcha_input, user_captcha)
                    print("Captcha entered!")
                    time.sleep(2)

                    # 尝试点击提交按钮
                    submit_btn = driver.find_element(By.CSS_SELECTOR, "#cf-turnstile-root button")
                    if submit_btn:
                        submit_btn.click()
                        print("Clicked captcha submit!")
                except Exception as e:
                    print(f"Could not handle captcha: {e}")

        # 检查当前 URL，判断是否登录成功
        current_url = driver.current_url
        print(f"\nCurrent URL: {current_url}")

        if "/user" in current_url or "user" in current_url.lower():
            print("✓ Login successful!")

            # 尝试点击确认按钮（如果存在）
            try:
                confirm_btn = driver.find_element(By.ID, "result_ok")
                print("Found result_ok button, clicking...")
                confirm_btn.click()
                time.sleep(2)
            except Exception as e:
                print(f"No result_ok button found: {e}")

        else:
            print("✗ Login may have failed. URL:", current_url)

        # 检查是否有弹窗（流量用完提示等）
        time.sleep(3)

        modals = driver.execute_script('''
            return Array.from(document.querySelectorAll('.modal'));
        ''')

        if len(modals) > 0:
            print(f"Found {len(modals)} modal(s)")

            # 尝试点击 result_ok 按钮关闭弹窗
            try:
                ok_btn = driver.find_element(By.ID, "result_ok")
                print("Found result_ok button in modal, clicking...")
                ok_btn.click()
                time.sleep(2)
            except Exception as e:
                print(f"Could not click result_ok: {e}")

        # 持续检查新打开的标签页（最多检查 3 次）
        for i in range(3):
            time.sleep(2)

            # 获取所有标签页
            windows = driver.execute_script("return window.parent.window.windows || window.top.windows;")
            if not windows:
                windows = [driver]

            print(f"Current tabs after {i+1} check: {len(windows)} tab(s)")

            # 如果有多个标签页，关闭多余的（只保留第一个）
            if len(windows) > 1:
                print(f"Found {len(windows)-1} extra tab(s), closing...")
                for win in windows[1:]:
                    try:
                        # 获取当前 URL
                        current_url = win.execute_script("return window.location.href;")
                        print(f"Closing extra tab at: {current_url}")
                        # 关闭标签页（通过 JavaScript）
                        win.execute_script("window.close();")
                        time.sleep(1)
                    except Exception as e:
                        print(f"Could not close tab: {e}")

        # 浏览器保持打开，按 Enter 关闭
        print("\n浏览器已保持打开，按 Enter 键关闭。")
        input()

    finally:
        pass


if __name__ == "__main__":
    main()
