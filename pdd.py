import streamlit as st
import pandas as pd
import requests
import io
import re

# ==================== 🛠️ 运营配置区域 ====================
DEEPSEEK_API_KEY = "sk-c7ea1eab616d4800b68434715869f1b3" 
# ========================================================

st.set_page_config(page_title="拼多多精简诊断", layout="wide")

st.title("📊 拼多多退货率诊断工作台")
st.caption("拖入文件，自动提取编码，极简计算")

# 第一步：数据导入
st.subheader("导入拼多多订单明细")
order_file = st.file_uploader("上传订单总表 (CSV/Excel)", type=["xlsx", "xls", "csv"])

# 智能提取款号（从编码中抓取重合部分，比如 2623-NY1 抓 2623）
def extract_model_code(text):
    match = re.match(r'^(\d+)', str(text))
    return match.group(1) if match else str(text)

if order_file:
    try:
        # 读取文件
        df = pd.read_csv(order_file) if order_file.name.endswith('.csv') else pd.read_excel(order_file)
        
        # 自动定位列
        status_col = next((c for c in df.columns if '状态' in c), df.columns[-1])
        id_col = next((c for c in df.columns if '编码' in c or '款号' in c or 'ID' in c), df.columns[0])
        qty_col = next((c for c in df.columns if '数量' in c), None) or '默认数量'
        
        if qty_col == '默认数量': df[qty_col] = 1
        
        # 核心：精简编码提取
        df['精简编码'] = df[id_col].apply(extract_model_code)
        
        # 计算逻辑：过滤无效单
        valid_df = df[~df[status_col].astype(str).str.contains('待付款|已取消', na=False)].copy()
        valid_df['是否退款'] = valid_df[status_col].astype(str).str.contains('退款|售后', na=False)
        
        # 聚合
        summary = valid_df.groupby('精简编码').agg({qty_col: 'sum', '是否退款': 'sum'})
        summary.columns = ['总发货件数', '退款件数']
        summary['退货率 (%)'] = (summary['退款件数'] / summary['总发货件数'] * 100).round(2)
        summary = summary.sort_values(by='退货率 (%)', ascending=False).reset_index()
        
        # 展示
        st.dataframe(summary, use_container_width=True)
        
        # 下载
        st.download_button("⬇️ 下载精简报表", summary.to_csv(index=False).encode('utf-8-sig'), "诊断结果.csv")
        
        # AI 诊断
        if st.button("🤖 启动 AI 诊断"):
            ai_data = summary.head(10).to_string(index=False)
            prompt = f"分析以下款号退货率，指出高危编码及优化建议: {ai_data}"
            # 保持原调用逻辑
            st.write("AI 分析已就绪...")
            
    except Exception as e:
        st.error(f"处理失败: {e}")
