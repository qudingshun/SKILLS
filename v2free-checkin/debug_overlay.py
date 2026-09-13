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
    
    # 查找所有包含 overlay/modal 的元素
    overlays = driver.execute_script('''
        return Array.from(document.querySelectorAll('.overlay, .modal, [class*="overlay"], [class*="modal"]'));
    ''')
    print(f'Found {len(overlays)} overlay/modal elements')
    
    for overlay in overlays:
        print(f'\nOverlay element:')
        print(f'  - Tag: {overlay.tag_name}')
        print(f'  - Class: {overlay.get_attribute("class")}')
        print(f'  - Text: {overlay.text[:100] if overlay.text else "None"}')
        
        # 查找 overlay 内的所有元素
        children = driver.execute_script('''
            return Array.from(parent.querySelectorAll("*"));
        ''', overlay)
        for child in children:
            print(f'    - Child: {child.tag_name} ({child.get_attribute("class") or "no class"})')
    
finally:
    driver.quit()
