import streamlit as st
import pandas as pd
import requests
import io

# ==================== 🛠️ 全局安全配置 ====================
try:
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    DEEPSEEK_API_KEY = ""
# ========================================================

# 页面美化配置：极简专业风格
st.set_page_config(page_title="拼多多·退货率 AI 智能诊断工作台", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    .stButton>button {width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white;}
    h1 {color: #2c3e50; font-size: 28px !important;}
    </style>
    """, unsafe_allow_html=True)

# 顶部导航区
st.title("📊 拼多多 · 退货率 AI 智能诊断工作台")
st.markdown("---")

# 侧边栏：核心控制台
with st.sidebar:
    st.header("⚙️ 运营控制台")
    alert_threshold = st.slider("⚠️ 退货率预警阈值 (%)", 0, 100, 25, 1)
    st.info("系统将自动剔除无效单，并高亮超出阈值的预警款号。")

# 数据导入区
st.subheader("📁 1. 导入数据")
master_file = st.file_uploader("点击上传订单总表 (CSV/Excel)", type=["xlsx", "xls", "csv"])

# 智能化读取引擎
def load_file(file):
    if file.name.endswith('.csv'):
        content = file.read()
        for enc in ['gb18030', 'gbk', 'utf-8-sig', 'utf-8']:
            try: return pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine='python')
            except: continue
        return pd.read_csv(io.BytesIO(content), encoding='gb18030', on_bad_lines='skip', sep=None, engine='python')
    return pd.read_excel(file)

if master_file:
    try:
        df = load_file(master_file)
        # 智能锁定列名
        id_col = next((c for c in df.columns if 'id' in c.lower()), df.columns[0])
        style_col = next((c for c in df.columns if '商家编码' in c or '款号' in c), None)
        qty_col = next((c for c in df.columns if '数量' in c), None) or '默认数量'
        status_col = next((c for c in df.columns if '状态' in c), None)
        
        if qty_col == '默认数量': df[qty_col] = 1
        
        # 剔除无效单 + 计算退款率
        valid_df = df[~df[status_col].astype(str).str.contains('待付款|已取消', na=False)].copy()
        valid_df['是否退款'] = valid_df[status_col].astype(str).str.contains('退款|售后', na=False)
        
        # 聚合核心数据
        summary = valid_df.groupby(id_col).agg({qty_col: 'sum', '是否退款': 'sum'})
        summary.columns = ['总件数', '退款件数']
        summary['退货率 (%)'] = (summary['退款件数'] / summary['总件数'] * 100).round(2)
        
        # 挂载款号
        if style_col:
            style_map = df[[id_col, style_col]].drop_duplicates(subset=[id_col]).set_index(id_col)
            summary = pd.merge(summary, style_map, left_index=True, right_index=True)
            summary = summary[['款号编码' if c==style_col else c for c in summary.columns]]

        # 排序与美化呈现
        summary = summary.sort_values(by='退货率 (%)', ascending=False)
        
        st.subheader("📊 2. 诊断数据看板")
        col1, col2, col3 = st.columns(3)
        col1.metric("总有效订单", f"{int(summary['总件数'].sum())} 件")
        col2.metric("总退款件数", f"{int(summary['退款件数'].sum())} 件")
        col3.metric("大盘平均退货率", f"{round(summary['退款件数'].sum()/summary['总件数'].sum()*100, 2)} %")
        
        # 表格颜色预警
        def highlight_alert(s):
            return ['background-color: #ffeef0' if v >= alert_threshold else '' for v in s]
        
        st.dataframe(summary.style.apply(highlight_alert, subset=['退货率 (%)']), use_container_width=True)
        
        # 下载按钮
        st.download_button("⬇️ 导出精简诊断报表", summary.to_csv().encode('utf-8-sig'), "诊断报表.csv")

        # AI 智能诊断区
        st.subheader("🤖 3. AI 深度决策建议")
        if st.button("启动深度诊断"):
            with st.spinner("AI 正在深度分析中..."):
                payload = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "你是一位眼光毒辣的电商运营专家，专注于数据驱动的爆款诊断与供应链优化。"},
                        {"role": "user", "content": f"基于以下退货数据：{summary.head(10).to_string()}。请以毒辣、简洁的白话给出：1.哪些款是高危款；2.这类退货数据通常指向哪些品控、视觉或版型漏洞；3.给出3条立即执行的挽单/优化建议。"}
                    ]
                }
                headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
                res = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers)
                st.markdown(res.json()['choices'][0]['message']['content'])

    except Exception as e:
        st.error(f"❌ 数据解析出错，请确保上传的是拼多多原版订单总表。")
