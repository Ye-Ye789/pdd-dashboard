import streamlit as st
import pandas as pd
import requests
import json
import io

# ==================== 🛠️ 全局安全配置 ====================
try:
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    DEEPSEEK_API_KEY = "" # 防止本地报错
# ========================================================

st.set_page_config(page_title="极简退货率诊断工作台", layout="wide")

st.title("📊 极简退货率 AI 诊断工作台（纯净版）")
st.caption("极致精简：只看核心指标。自动提取款号、计算真实退货率，剔除一切无效冗余数据！")

with st.sidebar:
    st.header("⚙️ 参数设置")
    alert_threshold = st.slider("综合退货率预警阈值 (%)", min_value=0, max_value=100, value=25, step=1)
    st.info("提示：系统会自动剔除“待付款/已取消”的无效单，并抓取包含“退款”状态的订单计算退货率。")

st.subheader("第一步：导入订单大表")
master_file = st.file_uploader("📂 上传近30天【订单总表】（需包含“订单状态”列）", type=["xlsx", "xls", "csv"])

# 强力防乱码读取引擎
def load_file(file):
    if file.name.endswith('.csv'):
        content = file.read() 
        for enc in ['gb18030', 'gbk', 'utf-8-sig', 'utf-8']:
            try:
                return pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine='python')
            except:
                continue
        return pd.read_csv(io.BytesIO(content), encoding='gb18030', on_bad_lines='skip', sep=None, engine='python')
    else:
        return pd.read_excel(file)

def find_column(df, possible_names):
    for col in possible_names:
        if col in df.columns:
            return col
    return None

if master_file:
    try:
        df = load_file(master_file)
        st.success("✅ 数据读取成功！正在生成纯净版大盘数据...")
        
        # 智能锁定核心列（彻底去除了原因列的抓取）
        id_col = find_column(df, ['商品id', '商品ID', '商品名称']) or df.columns[0]
        style_col = find_column(df, ['商家编码-商品维度', '商家编码-规格维度', '款号', '商家编码'])
        qty_col = find_column(df, ['商品数量(件)', '商品数量', '件数'])
        status_col = find_column(df, ['订单状态', '售后状态', '退款状态'])
        
        if not status_col:
            st.error("❌ 找不到【订单状态】列，请检查表格。")
            st.stop()

        df[status_col] = df[status_col].fillna('无')
        if qty_col:
            df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(1)
        else:
            df['默认数量'] = 1
            qty_col = '默认数量'

        # ---------------- 核心计算逻辑 ----------------
        # 1. 剔除完全没付钱和一开始就取消的无效订单
        valid_orders_df = df[~df[status_col].str.contains('待付款|已取消', na=False)].copy()
        
        # 2. 抓取退款订单
        valid_orders_df['是否退款'] = valid_orders_df[status_col].str.contains('退款|售后', na=False)

        # 提取款号映射
        style_mapping = pd.DataFrame()
        if style_col:
            style_mapping = df[[id_col, style_col]].drop_duplicates(subset=[id_col])
            style_mapping.columns = ['商品标识', '款号编码']
            
        # 统计单品总有效销量
        order_summary = valid_orders_df.groupby(id_col)[qty_col].sum().reset_index(name='有效订单件数')
        order_summary.rename(columns={id_col: '商品标识'}, inplace=True)
        
        # 统计单品退款量
        returns_df = valid_orders_df[valid_orders_df['是否退款']].copy()
        if not returns_df.empty:
            refund_summary = returns_df.groupby(id_col)[qty_col].sum().reset_index(name='退款件数')
        else:
            refund_summary = pd.DataFrame(columns=[id_col, '退款件数'])
        refund_summary.rename(columns={id_col: '商品标识'}, inplace=True)
        
        # 合并大表
        final_df = pd.merge(order_summary, refund_summary, on='商品标识', how='left').fillna(0)
        final_df['退款件数'] = final_df['退款件数'].astype(int)
        final_df['有效订单件数'] = final_df['有效订单件数'].astype(int)
        
        # 挂载款号编码
        if not style_mapping.empty:
            final_df = pd.merge(final_df, style_mapping, on='商品标识', how='left')
            cols = final_df.columns.tolist()
            cols = [cols[0], cols[-1]] + cols[1:-1]
            final_df = final_df[cols]
            
        final_df['综合退货率 (%)'] = ((final_df['退款件数'] / final_df['有效订单件数']) * 100).round(2)

        # 过滤掉没人买的废数据，并按退货率降序
        final_df = final_df[final_df['有效订单件数'] > 0]
        final_df = final_df.sort_values(by='综合退货率 (%)', ascending=False)
        
        # ---------------- 呈现结果 ----------------
        st.subheader("第二步：核心指标报表")
        
        total_orders = int(final_df['有效订单件数'].sum())
        total_refunds = int(final_df['退款件数'].sum())
        avg_rate = round((total_refunds / total_orders * 100), 2) if total_orders > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("总有效订单数", f"{total_orders} 件")
        m2.metric("总退款件数", f"{total_refunds} 件")
        m3.metric("大盘真实退款率", f"{avg_rate} %")
        
        def color_high_refund(val):
            try:
                v = float(str(val).replace('%', ''))
                return 'background-color: #ffcccc; color: #900;' if v >= alert_threshold else ''
            except:
                return ''

        st.dataframe(
            final_df.style.map(color_high_refund, subset=['综合退货率 (%)']),
            use_container_width=True
        )
        
        # 报表下载区
        col_down1, col_down2 = st.columns([1, 4])
        with col_down1:
            csv = final_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="⬇️ 下载纯净版 CSV 报表", data=csv, file_name="拼多多核心退货率明细.csv", mime="text/csv")
            
        # ---------------- AI 深度诊断 ----------------
        st.subheader("第三步：AI 全类目运营诊断")
        ai_data_summary = final_df.head(15).to_string(index=False)
        
        if st.button("🤖 启动 AI 爆款诊断", type="primary"):
            if not DEEPSEEK_API_KEY:
                st.warning("⚠️ 请先在后台的 Secrets 中配置 DEEPSEEK_API_KEY。")
            else:
                with st.spinner("AI 正在深度剖析高危款数据，请稍候..."):
                    try:
                        prompt = f"""
                        你是一位资深的拼多多全类目运营专家。下面是我们提取出的核心高危退货款式数据（已过滤无效冗余数据）：
                        
                        {ai_data_summary}
                        
                        当前全店有效订单平均退货率：{avg_rate}%。高危警报阈值设定为：{alert_threshold}%。
                        
                        请结合上述数据进行客观的大盘诊断：
                        1. 揪出退货率严重超标的高危【款号】。
                        2. 凭借你的经验，推测这些超高退货率的商品可能在【品控/材质】、【版型/规格】或者【详情页视觉展示】上踩了什么共性坑。
                        3. 给出针对前端客服挽单话术、页面视觉优化、供应链改良的 3 条极具落地性的建议。
                        
                        请直接输出大白话的诊断结论，排版清晰易读，让任何类目的运营都能直接看懂并执行。
                        """
                        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
                        payload = {
                            "model": "deepseek-chat",
                            "messages": [{"role": "system", "content": "你是一位眼光毒辣、精通各品类爆款操盘的资深电商运营专家。"}, {"role": "user", "content": prompt}],
                            "stream": False
                        }
                        response = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers)
                        if response.status_code == 200:
                            st.markdown(response.json()['choices'][0]['message']['content'])
                        else:
                            st.error(f"❌ AI 接口调用失败，状态码: {response.status_code}")
                    except Exception as e:
                        st.error(f"❌ 运行中出现错误: {e}")
                        
    except Exception as e:
        st.error(f"❌ 解析表格时出错。请确保上传的表格带有类似截图中的【订单状态】列。错误详情: {e}")
else:
    st.info("💡 提示：请将拼多多的完整【订单总表】拖入上方虚线框内（系统将自动计算纯净版退款率）。")
