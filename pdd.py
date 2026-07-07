import streamlit as st
import pandas as pd
import requests
import io
import re

# ==================== 🛠️ 全局安全配置 ====================
try:
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    DEEPSEEK_API_KEY = ""
# ========================================================

st.set_page_config(page_title="拼多多 · 退货率 AI 智能诊断工作台", layout="wide")

st.title("📊 拼多多 · 退货率 AI 智能诊断工作台")
st.markdown("---")

# 数据导入区
st.subheader("📁 1. 导入订单总表")
master_file = st.file_uploader("上传订单总表 (CSV/Excel)", type=["xlsx", "xls", "csv"])

# 智能提取款号函数
def extract_model_code(text):
    # 逻辑：只提取文本中最前面的数字（例如从 '2623-NY1' 提取出 '2623'）
    match = re.match(r'^(\d+)', str(text))
    return match.group(1) if match else str(text)

if master_file:
    try:
        df = pd.read_csv(master_file) if master_file.name.endswith('.csv') else pd.read_excel(master_file)
        st.success("✅ 数据读取成功！")
        
        # 自动锁定关键列
        status_col = next((c for c in df.columns if '状态' in c), None)
        id_col = next((c for c in df.columns if '编码' in c or '款号' in c), df.columns[0])
        qty_col = next((c for c in df.columns if '数量' in c), None) or '默认数量'
        
        if qty_col == '默认数量': df[qty_col] = 1
        
        # 数据清洗：提取核心款号
        df['精简款号'] = df[id_col].apply(extract_model_code)
        
        # 逻辑：剔除无效单 + 计算真实退货率
        valid_df = df[~df[status_col].astype(str).str.contains('待付款|已取消', na=False)].copy()
        valid_df['是否退款'] = valid_df[status_col].astype(str).str.contains('退款|售后', na=False)
        
        # 聚合数据
        summary = valid_df.groupby('精简款号').agg({qty_col: 'sum', '是否退款': 'sum'})
        summary.columns = ['总件数', '退款件数']
        summary['退货率 (%)'] = (summary['退款件数'] / summary['总件数'] * 100).round(2)
        summary = summary.sort_values(by='退货率 (%)', ascending=False).reset_index()

        st.subheader("📊 2. 诊断数据看板")
        st.dataframe(summary, use_container_width=True)
        
        # 下载报表
        st.download_button("⬇️ 导出纯净版诊断报表", summary.to_csv(index=False).encode('utf-8-sig'), "诊断报表.csv")

        # AI 诊断区
        if st.button("🤖 启动 AI 深度诊断"):
            st.write("AI 正在分析核心款号数据，请稍候...")
            # (省略后续调用代码，保持与之前一致)
            
    except Exception as e:
        st.error(f"解析错误: {e}")
