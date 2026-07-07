import streamlit as st
import pandas as pd
import requests
import json
import io

# ==================== 🛠️ 运营配置区域 ====================
# 请在这里填写你的 DeepSeek API Key (从官网上申请)
DEEPSEEK_API_KEY = "sk-c7ea1eab616d4800b68434715869f1b3" 
# ========================================================

st.set_page_config(page_title="拼多多全能退货率AI工作台", layout="wide")

# 标题区
st.title("📊 拼多多全能退货率 AI 智能工作台（含原因细分与报表下载）")
st.caption("极简、安全。右侧售后框支持同时拖入【退款成功/退款中/售后中】等多张 CSV/Excel 表格！")

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 参数设置")
    alert_threshold = st.slider("综合退货率预警阈值 (%)", min_value=0, max_value=100, value=15, step=1)
    st.info("提示：退货率包含已退款+退款中+售后中的总和。超过该阈值时将红色预警。")

# 第一步：数据导入
st.subheader("第一步：导入拼多多数据（支持CSV和Excel多选拖入）")
col1, col2 = st.columns(2)

with col1:
    order_file = st.file_uploader("📂 上传近30天【订单明细表】（发货大表，传1个文件）", type=["xlsx", "xls", "csv"])
with col2:
    refund_files = st.file_uploader("📂 批量上传近30天【所有售后表】（可多选拖入）", type=["xlsx", "xls", "csv"], accept_multiple_files=True)

# 智能化文件读取函数
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

# 智能列名匹配函数
def find_column(df, possible_names):
    for col in possible_names:
        if col in df.columns:
            return col
    return None

# 核心数据处理逻辑
if order_file and refund_files:
    try:
        # 1. 读取数据
        df_order = load_file(order_file)
        
        refund_dfs = []
        for file in refund_files:
            df_single_refund = load_file(file)
            if not df_single_refund.empty:
                refund_dfs.append(df_single_refund)
        
        if not refund_dfs:
            st.warning("⚠️ 未能成功读取到有效的售后表格数据，请检查文件。")
            st.stop()
            
        df_refund_all = pd.concat(refund_dfs, ignore_index=True)
        st.success(f"✅ 数据读取成功！已自动将 {len(refund_files)} 张售后状态表格合流对齐...")
        
        # 2. 寻找关键列
        id_col_order = find_column(df_order, ['商品id', '商品ID', '商品名称']) or df_order.columns[0]
        id_col_refund = find_column(df_refund_all, ['商品id', '商品ID', '商品名称']) or df_refund_all.columns[0]
        
        # 提取款号映射关系（商家编码-商品维度）
        style_col_order = find_column(df_order, ['商家编码-商品维度', '商家编码-规格维度', '款号', '商家编码'])
        style_mapping = pd.DataFrame()
        if style_col_order:
            # 建立 商品ID 到 款号 的映射去重表
            style_mapping = df_order[[id_col_order, style_col_order]].drop_duplicates(subset=[id_col_order])
            style_mapping.columns = ['商品标识', '款号编码']
            
        # 提取退货原因列
        reason_col = find_column(df_refund_all, ['退款原因', '售后原因', '问题描述', '买家退款原因'])
        
        # 3. 统计汇总
        if '商品数量(件)' in df_order.columns:
            qty_col = '商品数量(件)'
        elif '商品数量' in df_order.columns:
            qty_col = '商品数量'
        else:
            qty_col = None
            
        if qty_col:
            order_summary = df_order.groupby(id_col_order)[qty_col].sum().reset_index(name='总发货件数')
        else:
            order_summary = df_order.groupby(id_col_order).size().reset_index(name='总发货件数')
            
        if '申请退款件数' in df_refund_all.columns:
            refund_summary = df_refund_all.groupby(id_col_refund)['申请退款件数'].sum().reset_index(name='综合退款总数')
        elif '商品数量(件)' in df_refund_all.columns:
            refund_summary = df_refund_all.groupby(id_col_refund)['商品数量(件)'].sum().reset_index(name='综合退款总数')
        elif '商品数量' in df_refund_all.columns:
            refund_summary = df_refund_all.groupby(id_col_refund)['商品数量'].sum().reset_index(name='综合退款总数')
        else:
            refund_summary = df_refund_all.groupby(id_col_refund).size().reset_index(name='综合退款总数')
            
        order_summary.columns = ['商品标识', '总发货件数']
        refund_summary.columns = ['商品标识', '综合退款总数']
        
        # 4. 数据合并与综合计算
        final_df = pd.merge(order_summary, refund_summary, on='商品标识', how='left').fillna(0)
        final_df['综合退款总数'] = final_df['综合退款总数'].astype(int)
        
        # 关联款号
        if not style_mapping.empty:
            final_df = pd.merge(final_df, style_mapping, on='商品标识', how='left')
            # 调整列顺序，把款号放到前面
            cols = final_df.columns.tolist()
            cols = [cols[0], cols[-1]] + cols[1:-1]
            final_df = final_df[cols]
            
        final_df['综合退货率 (%)'] = (final_df['综合退款总数'] / final_df['总发货件数'] * 100).round(2)
        
        # 5. 计算退货原因占比透视
        if reason_col:
            # 统计每个ID下的各个原因数量
            reason_counts = df_refund_all.groupby([id_col_refund, reason_col]).size().reset_index(name='原因计数')
            total_reasons = df_refund_all.groupby(id_col_refund).size().reset_index(name='该款总退货数')
            reason_merged = pd.merge(reason_counts, total_reasons, on=id_col_refund)
            # 计算百分比并转为字符串格式
            reason_merged['占比'] = (reason_merged['原因计数'] / reason_merged['该款总退货数'] * 100).round(2).astype(str) + '%'
            
            # 透视表：行是ID，列是各个原因，值是占比
            reason_pivot = reason_merged.pivot(index=id_col_refund, columns=reason_col, values='占比').fillna('0%')
            reason_pivot.reset_index(inplace=True)
            reason_pivot.rename(columns={id_col_refund: '商品标识'}, inplace=True)
            
            # 拼接到最终大表中
            final_df = pd.merge(final_df, reason_pivot, on='商品标识', how='left').fillna('0%')

        # 排序：按退货率从高到低
        final_df = final_df.sort_values(by='综合退货率 (%)', ascending=False)
        
        # ==========================================
        # 第二步：结果呈现与导出
        # ==========================================
        st.subheader("第二步：近30天综合大盘与细分报表")
        
        total_orders = int(final_df['总发货件数'].sum())
        total_refunds = int(final_df['综合退款总数'].sum())
        avg_rate = round((total_refunds / total_orders * 100), 2) if total_orders > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("近30天店铺总发货", f"{total_orders} 件")
        m2.metric("近30天综合售后总量", f"{total_refunds} 件")
        m3.metric("近30天综合退货率", f"{avg_rate} %")
        
        def color_high_refund(val):
            # 尝试处理数字或带 % 的字符串进行标红
            try:
                v = float(str(val).replace('%', ''))
                return 'background-color: #ffcccc' if v > alert_threshold else ''
            except:
                return ''

        # 展示表格
        st.dataframe(
            final_df.style.map(color_high_refund, subset=['综合退货率 (%)']),
            use_container_width=True
        )
        
        # 🏆 提供 Excel 与 CSV 一键下载
        st.markdown("### 📥 下载报表")
        st.caption("已经为您匹配好【款号】并计算了【各个退货原因占比】，您可以直接下载完整表格进行留档或进一步分析。")
        
        col_down1, col_down2 = st.columns([1, 4])
        
        with col_down1:
            # 方案1：CSV 格式（最稳定，兼容性最强，强制 utf-8-sig 防止 Excel 乱码）
            csv = final_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="⬇️ 下载 CSV 报表",
                data=csv,
                file_name="拼多多退货大盘精细分析表.csv",
                mime="text/csv",
            )
            
        with col_down2:
            # 方案2：Excel 格式 (如果服务器有 openpyxl 库)
            try:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    final_df.to_excel(writer, index=False, sheet_name='退货率大盘与原因拆解')
                
                st.download_button(
                    label="⬇️ 下载 Excel 报表",
                    data=buffer.getvalue(),
                    file_name="拼多多退货大盘精细分析表.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.warning("提示：由于云端缺少 Excel 依赖组件，请使用左侧的【CSV 报表】下载（内容完全一样，可用 Excel 正常打开）。")


        # ==========================================
        # 第三步：DeepSeek 智能化复盘
        # ==========================================
        st.subheader("第三步：DeepSeek AI 运营诊断报告")
        
        # 只取前 15 名的高危款发给 AI 诊断，以节省 Token 并突出重点
        ai_data_summary = final_df.head(15).to_string(index=False)
        
        if st.button("🤖 启动 DeepSeek 诊断高危退货款", type="primary"):
            if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "YOUR_DEEPSEEK_API_KEY":
                st.warning("⚠️ 请先在脚本代码顶部的 `DEEPSEEK_API_KEY` 处填写您申请的 DeepSeek 密钥。")
            else:
                with st.spinner("AI 正在深度分析多维度退货原因，请稍候..."):
                    try:
                        prompt = f"""
                        你是一位资深的拼多多类目运营专家。下面是近30天店铺的综合退货情况（包含【款号】与【具体退款原因占比】）：
                        
                        {ai_data_summary}
                        
                        全店平均退货率：{avg_rate}%。我们设置的危险警报阈值是：{alert_threshold}%。
                        
                        请结合上述精细化数据：
                        1. 直接点名哪些【款号】处于高危状态，并指出它最致命的退货原因是什么（比如尺码、材质还是质量）。
                        2. 结合拼多多女装/内衣的客群特点，推测供应链或商品详情页可能存在什么坑。
                        3. 给出版型改进/前端挽单客服话术/详情页优化 的具体落地建议。
                        
                        请直接给出大白话的诊断结论，排版清晰，让运营直接去干活。
                        """
                        
                        headers = {
                            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                            "Content-Type": "application/json"
                        }
                        payload = {
                            "model": "deepseek-chat",
                            "messages": [
                                {"role": "system", "content": "你是一位精通拼多多规则和爆款操盘的资深电商运营专家。"},
                                {"role": "user", "content": prompt}
                            ],
                            "stream": False
                        }
                        
                        response = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers)
                        
                        if response.status_code == 200:
                            result = response.json()
                            ai_analysis = result['choices'][0]['message']['content']
                            st.markdown(ai_analysis)
                        else:
                            st.error(f"❌ AI 接口调用失败，状态码: {response.status_code}，请检查 API Key 是否有效。")
                    except Exception as e:
                        st.error(f"❌ 运行中出现错误: {e}")
                        
    except Exception as e:
        st.error(f"❌ 读取表格或合流解析时出错。请确保你上传的是拼多多原版表格。错误详情: {e}")
else:
    st.info("💡 提示：请在左边上传1个订单表，在右边【同时选中并拖入】1个或多个不同的售后明细表格以激活综合计算。")