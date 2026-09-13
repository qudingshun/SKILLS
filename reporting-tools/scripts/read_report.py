import openpyxl
from pathlib import Path

# 读取生成的报表文件
file_path = r"E:/OneDrive/桌面/生产情况日报/成品库存 2026-08-19.xlsx"

print("=" * 50)
print("产销存日报 - 数据摘要")
print("=" * 50)
print(f"\n读取文件：{file_path}\n")

try:
    wb = openpyxl.load_workbook(file_path)
    
    # 获取工作表列表
    sheet_names = [ws.title for ws in wb.worksheets]
    print("工作表:", sheet_names)
    
    # 读取"汇总"Sheet（如果有）或第一个 Sheet
    if "汇总" in sheet_names:
        ws = wb["汇总"]
    else:
        ws = wb.active
    
    print("\n=== 核心数据摘要 ===\n")
    
    # 打印表头和数据
    for row_num, row in enumerate(ws.iter_rows(min_row=1, max_col=5), start=1):
        if row_num == 1:
            print(f"列{row[0].column_letter}: {row[0]}")
        elif row_num >= 2 and row_num <= 6:
            data = [cell.value for cell in row]
            print(f"{chr(65 + row[0].column_letter - 1)}: {data}")
    
    # 提取关键指标
    print("\n" + "=" * 50)
    print("关键指标汇总")
    print("=" * 50)
    
    # 查找产量、出货、库存等关键字段
    data_rows = list(ws.iter_rows(min_row=2, max_col=5))
    
    for row in data_rows:
        values = [cell.value if cell else "" for cell in row]
        print(f"  {chr(65 + row[0].column_letter - 1)}: {values}")
        
except Exception as e:
    print(f"\n读取文件失败：{e}")

print("\n报表生成成功！")
