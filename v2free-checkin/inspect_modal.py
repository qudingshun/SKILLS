"""调试脚本：登录后提取页面弹窗/按钮信息，不执行任何点击"""
import os, sys, json, base64, time
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CRED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cred.json")
URL = "https://w1.v2free.cyou/auth/login"


def load_cred():
    if not os.path.exists(CRED_FILE):
        return None, None
    with open(CRED_FILE) as f:
        data = json.load(f)
    account = base64.b64decode(data["account"]).decode()
    password = base64.b64decode(data["password"]).decode()
    return account, password


def dump_page_info(driver):
    """提取并输出页面所有弹窗、按钮信息"""
    print("\n" + "=" * 60)
    print("CURRENT URL:", driver.current_url)
    print("PAGE TITLE:", driver.title)
    print("=" * 60)

    # 1. 所有 modal / overlay 元素
    print("\n--- MODAL / OVERLAY 元素 ---")
    modals = driver.execute_script('''
        return Array.from(document.querySelectorAll('.modal, .overlay, [class*="modal"], [class*="overlay"]'));
    ''')
    print(f"共 {len(modals)} 个")

    for i, m in enumerate(modals):
        print(f"\n  [{i}] tag={m.tag_name} class='{m.get_attribute('class')}'")
        print(f"       visible={m.is_displayed()}")
        print(f"       text={m.text[:200] if m.text else '(空)'}")
        inner_html = driver.execute_script("return arguments[0].innerHTML;", m)
        print(f"       innerHTML={inner_html[:500]}")

    # 2. 所有 button
    print("\n--- 所有 BUTTON ---")
    buttons = driver.find_elements(By.TAG_NAME, "button")
    for btn in buttons:
        print(f"  id={btn.get_attribute('id')}  class={btn.get_attribute('class')}  "
              f"text={(btn.text or '').strip()[:50]}  visible={btn.is_displayed()}")

    # 3. 所有 a 标签（可能有点击跳转的链接）
    print("\n--- 所有 A 标签（href 含 modal/result 的） ---")
    links = driver.find_elements(By.TAG_NAME, "a")
    for a in links:
        href = a.get_attribute("href") or ""
        if "faq" in href or "result" in href or "modal" in href:
            print(f"  href={href}  text={(a.text or '').strip()[:50]}  id={a.get_attribute('id')}")

    # 4. result_ok 按钮详细信息
    print("\n--- #result_ok 详细信息 ---")
    try:
        btn = driver.find_element(By.ID, "result_ok")
        print(f"  tag={btn.tag_name}")
        print(f"  text={btn.text.strip()}")
        print(f"  class={btn.get_attribute('class')}")
        print(f"  type={btn.get_attribute('type')}")
        print(f"  data-dismiss={btn.get_attribute('data-dismiss')}")
        print(f"  onclick={btn.get_attribute('onclick')}")
        print(f"  outerHTML={btn.get_attribute('outerHTML')[:500]}")
        print(f"  visible={btn.is_displayed()}")
    except Exception as e:
        print(f"  未找到: {e}")


def main():
    account, password = load_cred()
    if not account or not password:
        print("Credentials not found in cred.json")
        sys.exit(1)

    options = Options()
    options.use_chromium = True
    driver = webdriver.Edge(options=options)

    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 10)

        # 登录
        wait.until(EC.element_to_be_clickable((By.ID, "login")))
        email = driver.find_element(By.ID, "email")
        passwd = driver.find_element(By.ID, "passwd")
        email.clear()
        email.send_keys(account)
        passwd.clear()
        passwd.send_keys(password)
        btn = driver.find_element(By.ID, "login")
        btn.click()
        print("Clicked login button!")

        # 等待跳转
        time.sleep(3)

        current_url = driver.current_url
        print(f"Current URL after login: {current_url}")

        if "user" in current_url.lower():
            print("Login successful!")
            # 等待 result_ok 按钮出现
            time.sleep(3)
            dump_page_info(driver)
        else:
            print("Login may have failed, URL:", current_url)

        print("\n浏览器保持打开，请手动关闭。")
        input("Press Enter to exit...")
    finally:
        pass


if __name__ == "__main__":
    main()
