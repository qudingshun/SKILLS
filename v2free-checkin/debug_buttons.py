import selenium
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

options = Options()
options.use_chromium = True
driver = webdriver.Edge(options=options)

try:
    driver.get('https://w1.v2free.cyou/user')
    
    # 执行 JavaScript 获取所有按钮
    all_buttons = driver.execute_script('return Array.from(document.querySelectorAll("button"))')
    print('All buttons on page:')
    for btn in all_buttons:
        print(f'  - {btn.get_attribute("id") or "no id"} ({btn.get_attribute("class") or "no class"})')
    
finally:
    driver.quit()
