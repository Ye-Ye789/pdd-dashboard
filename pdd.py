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

st.title("📊 极简退货率 AI 诊断工作台（全类目通用版）")
st.caption("丢掉繁琐的表格匹配！只需上传一份包含【订单状态】的总表，自动提取款号、计算退货率与原因拆解！")

with st.sidebar:
    st.header("⚙️ 参数设置")
    alert_threshold = st.slider("综合退货率预警阈值 (%)", min_value=0, max_value=100, value=25, step=1)
    st.info("提示：系统会自动剔除“待付款/已取消”的无效单，并抓取包含“退款”状态的订单计算退货率。")

st.subheader("第一步：导入订单大表")
master_file = st.file_uploader("📂 上传近30天【订单总表】（需包含图中所示的“订单状态”列）", type=["xlsx", "xls", "csv"])

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
        st.success("✅ 数据读取成功！正在自动过滤无效订单并解析退款状态...")
        
        # 智能锁定表头列
        id_col = find_column(df, ['商品id', '商品ID', '商品名称']) or df.columns[0]
        style_col = find_column(df, ['商家编码-商品维度', '商家编码-规格维度', '款号', '商家编码'])
        qty_col = find_column(df, ['商品数量(件)', '商品数量', '件数'])
        status_col = find_column(df, ['订单状态', '售后状态', '退款状态'])
        reason_col = find_column(df, ['买家退款原因', '退款原因', '问题描述', '商家备注'])
        
        if not status_col:
            st.error("❌ 找不到【订单状态】列，请检查表格是否和截图一致。")
            st.stop()

        df[status_col] = df[status_col].fillna('无')
        if qty_col:
            df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(1)
        else:
            df['默认数量'] = 1
            qty_col = '默认数量'

        # ---------------- 核心计算逻辑 ----------------
        # 1. 剔除完全没付钱和一开始就取消的无效订单，计算真实的“有效发货基本盘”
        valid_orders_df = df[~df[status_col].str.contains('待付款|已取消', na=False)].copy()
        
        # 2. 从有效订单中，抓取所有发生过退款的订单
        valid_orders_df['是否退款'] = valid_orders_df[status_col].str.contains('退款|售后', na=False)

        # 提取款号映射（商家编码 -> 商品ID）
        style_mapping = pd.DataFrame()
        if style_col:
            style_mapping = df[[id_col, style_col]].drop_duplicates(subset=[id_col])
            style_mapping.columns = ['商品标识', '款号编码']
            
        # 统计单品总有效销量
        order_summary = valid_orders_df.groupby(id_col)[qty_col].sum().reset_index(name='有效订单件数')
        order_summary.rename(columns={id_col: '商品标识'}, inplace=True) # <-- 修复点：统一下列名
        
        # 统计单品退款量
        returns_df = valid_orders_df[valid_orders_df['是否退款']].copy()
        if not returns_df.empty:
            refund_summary = returns_df.groupby(id_col)[qty_col].sum().reset_index(name='退款件数')
        else:
            refund_summary = pd.DataFrame(columns=[id_col, '退款件数'])
        refund_summary.rename(columns={id_col: '商品标识'}, inplace=True) # <-- 修复点：统一下列名
        
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
        
        # 处理退货原因占比（如果表里有原因列的话）
        if reason_col and not returns_df.empty:
            returns_df[reason_col] = returns_df[reason_col].fillna('未填写原因/默认退款')
            reason_counts = returns_df.groupby([id_col, reason_col])[qty_col].sum().reset_index(name='原因计数')
            total_reasons = returns_df.groupby(id_col)[qty_col].sum().reset_index(name='该款总退货数')
            reason_merged = pd.merge(reason_counts, total_reasons, on=id_col)
            reason_merged['占比'] = ((reason_merged['原因计数'] / reason_merged['该款总退货数']) * 100).round(2).astype(str) + '%'
            
            reason_pivot = reason_merged.pivot(index=id_col, columns=reason_col, values='占比').fillna('0%')
            reason_pivot.reset_index(inplace=True)
            reason_pivot.rename(columns={id_col: '商品标识'}, inplace=True)
            
            final_df = pd.merge(final_df, reason_pivot, on='商品标识', how='left').fillna('0%')

        # 过滤掉没人买的废数据，并按退货率降序
        final_df = final_df[final_df['有效订单件数'] > 0]
        final_df = final_df.sort_values(by='综合退货率 (%)', ascending=False)
        
        # ---------------- 呈现结果 ----------------
        st.subheader("第二步：大盘精细化分析报表")
        
        total_orders = int(final_df['有效订单件数'].sum())
        total_refunds = int(final_df['退款件数'].sum())
        avg_rate = round((total_refunds / total_orders * 100), 2) if total_orders > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("剔除无效后的有效订单总数", f"{total_orders} 件")
        m2.metric("总退款/售后件数", f"{total_refunds} 件")
        m3.metric("大盘平均真实退款率", f"{avg_rate} %")
        
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
            st.download_button(label="⬇️ 一键下载 CSV 结果报表", data=csv, file_name="拼多多单表退货明细.csv", mime="text/csv")
            
        # ---------------- AI 深度诊断 ----------------
        st.subheader("第三步：AI 针对性运营诊断")
        ai_data_summary = final_df.head(15).to_string(index=False)
        
        if st.button("🤖 启动全类目 AI 爆款诊断", type="primary"):
            if not DEEPSEEK_API_KEY:
                st.warning("⚠️ 请先在后台的 Secrets 中配置 DEEPSEEK_API_KEY。")
            else:
                with st.spinner("AI 正在深度剖析致命退款原因，请稍候..."):
                    try:
                        prompt = f"""
                        你是一位资深的拼多多全类目运营专家。下面是我们通过订单总表提取出的核心退货数据（包含款号与各退款原因占比）：
                        
                        {ai_data_summary}
                        
                        当前全店有效订单平均退货率：{avg_rate}%。高危警报阈值设定为：{alert_threshold}%。
                        
                        请结合上述精细化数据进行客观的大盘诊断：
                        1. 揪出退货率严重超标的高危【款号】，并指出其最致命的核心退款原因。
                        2. 根据这些退货原因，推测商品在【品控/材质】、【版型/规格】或者【详情页视觉展示】（如是否存在色差、夸大宣传、描述不符等）上可能踩了什么共性坑。
                        3. 给出针对前端客服挽单话术、页面视觉优化、供应链改良的 3 条极具落地性的毒辣建议。
                        
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
    st.info("💡 提示：请将拼多多的完整【订单总表】拖入上方虚线框内（系统将自动识别图中的订单状态并解析）。")
