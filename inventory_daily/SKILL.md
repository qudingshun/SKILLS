---
name: "inventory-daily"
description: "生成成品库存日报。触发词：产销存报表"
---

# Inventory Daily Report Generator

**Description:** 自动生成成品库存日报。触发词：产销存报表。自动执行 VBA 宏刷新 Excel 数据，从"汇总"Sheet 提取关键指标，生成格式化日报摘要。

**Steps:**
1. 检查当前日期和时间（使用 `date` 命令）
2. 定位到成品库存 Excel 文件路径
3. 执行 VBA 宏刷新数据：打开 Excel → 运行"RefreshData"宏 → 等待完成
4. 从"汇总"Sheet 提取关键指标：总库存、已发货、待发货、安全水位、异常 SKU
5. 生成日报摘要报告，包含日期、关键指标表格、异常项列表及建议
6. 将报告保存到指定目录（如 C:\Users\qudin\Documents\Inventory_Daily_YYYYMMDD.xlsx）
7. 输出报告内容到终端供用户查看

**Verification:**
- 确认 Excel 文件已打开且宏执行成功
- 验证日报包含所有关键指标
- 检查异常项列表是否准确
- 确保报告文件保存成功并可正常打开

**Pitfalls:**
- VBA 宏可能需要启用宏安全设置（File > Options > Trust Center）
- Excel 文件路径可能因版本不同而变化，需确认完整路径
- 某些公司网络可能限制 Excel 访问，需检查网络连接
