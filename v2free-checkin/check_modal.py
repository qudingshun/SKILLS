import selenium
from selenium import webdriver
from selenium.webdriver.edge.options import Options

options = Options()
options.use_chromium = True
driver = webdriver.Edge(options=options)

try:
    driver.get('https://w1.v2free.cyou/user')
    
    # 检查是否有 modal/overlay
    modals = driver.execute_script('''
        return Array.from(document.querySelectorAll('.modal, .overlay'));
    ''')
    print(f'Modal count: {len(modals)}')
    
    for m in modals:
        print(f"Modal class: {m.get_attribute('class')}")
        # 检查 modal 内是否有按钮
        btns = driver.execute_script('''
            var modal = arguments[0];
            return Array.from(modal.querySelectorAll('button, [role="button"]'));
        ''', m)
        print(f"Buttons in modal: {len(btns)}")
    
    # 检查页面标题和可见元素
    title = driver.title
    print(f"\nPage title: {title}")
    
finally:
    driver.quit()
