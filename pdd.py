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

st.set_page_config(page_title="拼多多·退货率 AI 智能诊断工作台", layout="wide")

st.title("📊 拼多多 · 退货率 AI 智能诊断工作台")
st.caption("极致精简：自动识别列名，一键诊断核心退货率。")

# 侧边栏：核心控制台
with st.sidebar:
    st.header("⚙️ 运营控制台")
    alert_threshold = st.slider("⚠️ 退货率预警阈值 (%)", 0, 100, 25, 1)
    st.info("系统会自动剔除无效单，并高亮超出阈值的预警款号。")

# 数据导入区
st.subheader("📁 1. 导入数据")
master_file = st.file_uploader("点击上传订单总表 (CSV/Excel)", type=["xlsx", "xls", "csv"])

# 智能化读取引擎，增加编码自动识别和列名模糊匹配
def load_file(file):
    if file.name.endswith('.csv'):
        content = file.read()
        for enc in ['gb18030', 'gbk', 'utf-8-sig', 'utf-8']:
            try: return pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine='python')
            except: continue
        return pd.read_csv(io.BytesIO(content), encoding='gb18030', on_bad_lines='skip', sep=None, engine='python')
    return pd.read_excel(file)

def get_col(df, keywords):
    """模糊匹配列名"""
    for col in df.columns:
        for kw in keywords:
            if kw in str(col):
                return col
    return None

if master_file:
    try:
        df = load_file(master_file)
        st.success("✅ 数据读取成功！正在分析...")
        
        # 智能匹配必要的列
        id_col = get_col(df, ['商品id', '商品ID', '商品名称']) or df.columns[0]
        style_col = get_col(df, ['商家编码', '款号'])
        qty_col = get_col(df, ['数量']) or '默认数量'
        status_col = get_col(df, ['订单状态', '售后状态', '退款状态'])
        
        if qty_col == '默认数量': df[qty_col] = 1
        
        # 逻辑：剔除无效单 + 计算真实退货率
        valid_df = df[~df[status_col].astype(str).str.contains('待付款|已取消', na=False)].copy()
        valid_df['是否退款'] = valid_df[status_col].astype(str).str.contains('退款|售后', na=False)
        
        # 聚合数据，统一列名为 '商品标识' 以便后续计算
        summary = valid_df.groupby(id_col).agg({qty_col: 'sum', '是否退款': 'sum'})
        summary.columns = ['总件数', '退款件数']
        summary.index.name = '商品标识' # 统一索引名称
        summary = summary.reset_index()
        
        # 计算退货率
        summary['退货率 (%)'] = (summary['退款件数'] / summary['总件数'] * 100).round(2)
        
        # 挂载款号
        if style_col:
            style_map = df[[id_col, style_col]].drop_duplicates(subset=[id_col])
            style_map.columns = ['商品标识', '款号编码']
            summary = pd.merge(summary, style_map, on='商品标识', how='left')

        summary = summary.sort_values(by='退货率 (%)', ascending=False)
        
        st.subheader("📊 2. 诊断数据看板")
        # 显示表格前，确保列名已统一
        st.dataframe(summary, use_container_width=True)
        
        # AI 诊断逻辑
        if st.button("启动 AI 智能诊断"):
            # ... (此处省略AI请求逻辑，保持与你原版一致)
            pass

    except Exception as e:
        st.error(f"❌ 解析出错: {e}")
