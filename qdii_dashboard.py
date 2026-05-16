import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

# ==================== 1. 基础配置与自动刷新 ====================
st.set_page_config(page_title="QDII 智投工作台", layout="wide", initial_sidebar_state="collapsed")

# 激活自动刷新 (60秒刷新一次，安全防封)
st_autorefresh(interval=60000, limit=1000, key="data_refresh")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Referer": "http://fund.eastmoney.com/"
}

FUND_POOL = {
    "000834": {"name": "大成纳指100(QDII)A", "baseline": 300, "max_limit": 5000, "etf": "105.QQQ"},
    "017641": {"name": "摩根标普500(QDII)A", "baseline": 100, "max_limit": 100, "etf": "105.SPY"},
    "018738": {"name": "博时标普500(QDII)A", "baseline": 300, "max_limit": 2000, "etf": "105.SPY"}
}

# ==================== 2. 核心算法数据抓取 ====================
def get_data(fund_code, etf_id):
    try:
        f_url = f"http://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex=1&pageSize=20"
        res = requests.get(f_url, headers=HEADERS, timeout=5).json()
        nav_data = res['Data']['LSJZList']
        latest_nav = float(nav_data[0]['DWJZ'])
        prev_nav = float(nav_data[1]['DWJZ'])
        high_nav = max([float(i['DWJZ']) for i in nav_data])
        daily_gain = (latest_nav - prev_nav) / prev_nav * 100
    except:
        return None

    try:
        e_url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={etf_id}&fields=f3,f192"
        e_res = requests.get(e_url, headers=HEADERS, timeout=5).json()
        f3, f192 = e_res['data']['f3'], e_res['data']['f192']
        reg_pct = float(f3) if f3 not in ["-", None] else 0.0
        ext_pct = float(f192) if f192 not in ["-", None] else 0.0
        
        if reg_pct == 0:
            k_url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={etf_id}&fields1=f1&fields2=f59&klt=101&lmt=1"
            k_res = requests.get(k_url, timeout=5).json()
            reg_pct = float(k_res['data']['klines'][0].split(',')[1])
    except:
        reg_pct, ext_pct = 0.0, 0.0

    return {"nav": latest_nav, "high": high_nav, "daily": daily_gain, "reg": reg_pct, "ext": ext_pct}

def get_strategy(drop_pct, baseline, limit):
    if drop_pct >= 15: buy, tag = baseline + 8000, "🔴 15% 深度回撤"
    elif drop_pct >= 10: buy, tag = baseline + 5000, "🟠 10% 中度回撤"
    elif drop_pct >= 5: buy, tag = baseline + 3000, "🟡 5% 常规回撤"
    elif drop_pct >= 2: buy, tag = baseline + 1000, "🔹 小幅回调"
    else: buy, tag = baseline, "🟢 正常震荡"
    
    final_buy = min(buy, limit)
    is_max = " (触顶!)" if buy >= limit else ""
    return final_buy, f"{tag}{is_max}"

# ==================== 3. 网页布局与时区对齐 ====================
st.title("📈 美股 QDII 智投工作台")

# 获取北京时间和纽约时间
now_bj = datetime.now(ZoneInfo("Asia/Shanghai"))
now_ny = datetime.now(ZoneInfo("America/New_York"))

bj_time_str = now_bj.strftime('%Y-%m-%d %H:%M:%S')
ny_time_str = now_ny.strftime('%Y-%m-%d %H:%M:%S')

# 判断美股盘面阶段
ny_time_float = now_ny.hour + now_ny.minute / 60.0
if now_ny.weekday() >= 5:
    market_status = " 💤 周末休市中"
elif 4.0 <= ny_time_float < 9.5:
    market_status = " 🌅 美股盘前交易 (Pre-market)"
elif 9.5 <= ny_time_float < 16.0:
    market_status = " 🟢 美股正盘交易 (Regular Session)"
elif 16.0 <= ny_time_float < 20.0:
    market_status = " 🌆 美股盘后交易 (After-hours)"
else:
    market_status = " 🌙 美股夜盘/停盘时段"

# 渲染顶部双时区仪表盘
st.markdown(f"""
| 📍 观察哨位置 | 📅 实时当前时间 | 🕒 当前盘面状态 |
| :--- | :--- | :--- |
| **北京时间 (CN)** | `{bj_time_str}` | 截单倒计时/隔夜复盘 |
| **纽约时间 (US)** | `{ny_time_str}` | **{market_status}** |
""")
st.divider() 

# 创建双标签页
tab1, tab2 = st.tabs(["💰 核心建仓与预测", "📅 宏观风向与事件日历"])

# ==================== Tab 1: 核心建仓 (内部已精确缩进) ====================
with tab1:
    for code, info in FUND_POOL.items():
        data = get_data(code, info['etf'])
        if not data:
            st.error(f"{info['name']} 数据加载失败")
            continue

        drop = (data['high'] - data['nav']) / data['high'] * 100
        total_impact = ((1 + data['reg']/100) * (1 + data['ext']/100) - 1) * 100
        est_nav = data['nav'] * (1 + total_impact/100)
        buy_amt, action = get_strategy(drop, info['baseline'], info['max_limit'])

        with st.container(border=True):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader(info['name'])
                st.write(f"最新官方净值: **{data['nav']:.4f}** (昨跌 {data['daily']:.2f}%)")
            with col2:
                st.metric("静态高位回撤", f"{drop:.2f}%")

            c1, c2, c3 = st.columns(3)
            c1.metric("美股正盘", f"{data['reg']:.2f}%")
            c2.metric("盘前/夜盘", f"{data['ext']:.2f}%")
            c3.metric("双重叠加影响", f"{total_impact:.2f}%", delta_color="inverse")

            st.divider()
            c_left, c_right = st.columns([1, 1])
            with c_left:
                st.write(f"🔮 今晚估算净值: **{est_nav:.4f}**")
            with c_right:
                st.info(f"👉 动作: **{action}** -> 申购: **¥{buy_amt}**")

    st.success("提示：15:00 前申购按当晚美股收盘价结算。请结合宏观日历执行定投。")

# ==================== Tab 2: 宏观日历 (内部已精确缩进) ====================
with tab2:
    st.header("🧠 纳指/标普核心驱动因子")
    with st.expander("展开查看：什么事情会引发美股暴涨或暴跌？", expanded=False):
        st.markdown("""
        * **🦅 美联储利率决议 (FOMC会议)：** 现任主席沃什主张缩表。如果放出强缩表信号，流动性收紧，科技股暴跌；反之则暴涨。
        * **🛒 核心通胀数据 (CPI / PCE)：** 如果通胀数据高于预期，市场担忧继续加息，大盘大跌；反之则大涨。
        * **👷 就业数据 (非农 NFP)：** 失业率猛增会引发衰退交易大跌；就业过分火爆引发通胀担忧也会跌；适中则涨。
        * **💻 科技巨头财报 (英伟达等)：** 纳指100权重高度集中。如果巨头对未来的 AI 盈利指引不及预期，纳指将遭遇重挫。
        """)

    st.header("🗓️ 近期重磅宏观事件日历 (未来30天)")
    calendar_data = [
        {"日期 (北京时间)": "2026年5月22日 (周五)", "重磅事件": "🇺🇸 美国5月制造业/服务业PMI", "预期影响等级": "⭐⭐", "多空逻辑预判": "PMI跌破50荣枯线可能引发衰退恐慌，科技股承压。"},
        {"日期 (北京时间)": "2026年5月29日 (周五)", "重磅事件": "🛒 美国4月核心PCE物价指数", "预期影响等级": "⭐⭐⭐⭐", "多空逻辑预判": "美联储通胀金标准。若反弹纳指杀估值，若回落迎来大反弹。"},
        {"日期 (北京时间)": "2026年6月5日  (周五)", "重磅事件": "👷 美国5月非农就业报告 (NFP)", "预期影响等级": "⭐⭐⭐⭐", "多空逻辑预判": "关注失业率。数据若异常强劲，将粉碎降息预期。"},
        {"日期 (北京时间)": "2026年6月11日 (周四)", "重磅事件": "📉 美国5月CPI数据", "预期影响等级": "⭐⭐⭐⭐⭐", "多空逻辑预判": "直接决定次周议息基调。CPI超预期将引发大盘全线抛售。"},
        {"日期 (北京时间)": "2026年6月18日 (周四)", "重磅事件": "🦅 美联储FOMC利率决议 + 沃什讲话", "预期影响等级": "⭐⭐⭐⭐⭐", "多空逻辑预判": "重磅大戏！沃什对缩表的表态将决定标普与纳指长期拐点，波动极剧烈。"}
    ]
    st.dataframe(pd.DataFrame(calendar_data), hide_index=True, use_container_width=True)
    st.info("💡 操作心法：遇到五星级事件前夕切忌追高；若事件落地引发暴跌，按系统提示的高额度果断吸纳筹码！")
