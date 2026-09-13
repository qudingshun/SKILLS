---
name: WHP-scm-received-inbound
description: >
  已接收入库导出工具 — 自动登录 SCM，打开送货单查询，设置查询条件
  （接收日期=当月1号~当月最后一天、接收状态=已接收、接收地址=M03、
  最大显示数=99999），导出「已入库.xlsx」。
  独立脚本，代码逻辑参考 WHP-whirlpool-download 技能的 unified_report_downloader.py。
  
  Trigger keywords: 已接收入库, 接收入库, 导出已入库, 跑已接收入库, 已接收送货单
  
  Usage examples:
  - "跑已接收入库"
  - "导出已接收送货单"
  - "下载已入库"
---