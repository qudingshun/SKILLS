import selenium
from selenium import webdriver
from selenium.webdriver.edge.options import Options

options = Options()
options.use_chromium = True
driver = webdriver.Edge(options=options)

try:
    driver.get('https://w1.v2free.cyou/user')
    
    # 获取整个页面源码
    page_source = driver.page_source
    print("Page source (first 5000 chars):")
    print(page_source[:5000])
    
finally:
    driver.quit()
