import ddddocr

ocr = ddddocr.DdddOcr(show_ad=False)

# 改成你图片的实际路径
with open(r'E:\SKILLS\WHP-scm-huihuo-import\scripts\test.png', 'rb') as f:
    result = ocr.classification(f.read())
    print(result)