import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 基础配置 ---
st.set_page_config(page_title="QDII 智投工作台", layout="wide", initial_sidebar_state="collapsed")

# 激活自动刷新 (60秒刷新一次，防止被封)
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


# --- 2. 核心算法 ---
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

        # 周末兜底逻辑
        if reg_pct == 0:
            k_url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={etf_id}&fields1=f1&fields2=f59&klt=101&lmt=1"
            k_res = requests.get(k_url, timeout=5).json()
            reg_pct = float(k_res['data']['klines'][0].split(',')[1])
    except:
        reg_pct, ext_pct = 0.0, 0.0

    return {"nav": latest_nav, "high": high_nav, "daily": daily_gain, "reg": reg_pct, "ext": ext_pct}


def get_strategy(drop_pct, baseline, limit):
    if drop_pct >= 15:
        buy, tag = baseline + 8000, "🔴 深度回撤"
    elif drop_pct >= 10:
        buy, tag = baseline + 5000, "🟠 中度回撤"
    elif drop_pct >= 5:
        buy, tag = baseline + 3000, "🟡 常规回撤"
    elif drop_pct >= 2:
        buy, tag = baseline + 1000, "🔹 小幅回调"
    else:
        buy, tag = baseline, "🟢 正常震荡"

    final_buy = min(buy, limit)
    is_max = " (触顶!)" if buy >= limit else ""
    return final_buy, f"{tag}{is_max}"


# --- 3. 网页布局：双标签页体系 ---
st.title("📈 美股 QDII 智投工作台")

# 👈 11.3 升级：双时区自动夏令时对齐逻辑
from datetime import datetime
from zoneinfo import ZoneInfo # Python 3.9+ 自带，完美处理美东夏令时

# 动态获取北京时间和纽约时间
now_bj = datetime.now(ZoneInfo("Asia/Shanghai"))
now_ny = datetime.now(ZoneInfo("America/New_York"))

bj_time_str = now_bj.strftime('%Y-%m-%d %H:%M:%S')
ny_time_str = now_ny.strftime('%Y-%m-%d %H:%M:%S')

# 判断美股当前处于什么盘面阶段
ny_hour = now_ny.hour
ny_minute = now_ny.minute
ny_time_float = ny_hour + ny_minute / 60.0

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

# 在网页顶部整齐渲染双时区
st.markdown(f"""
| 📍 观察哨位置 | 📅 实时当前时间 | 🕒 当前盘面状态 |
| :--- | :--- | :--- |
| **北京时间 (CN)** | `{bj_time_str}` | 截单倒计时/隔夜复盘 |
| **纽约时间 (US)** | `{ny_time_str}` | **{market_status}** |
""")
st.divider() # 加一条分割线

# ==================== Tab 1: 核心建仓 (保持原有硬核功能) ====================
with tab1:
    for code, info in FUND_POOL.items():
        data = get_data(code, info['etf'])
        if not data:
            st.error(f"{info['name']} 数据加载失败")
            continue

        drop = (data['high'] - data['nav']) / data['high'] * 100
        total_impact = ((1 + data['reg'] / 100) * (1 + data['ext'] / 100) - 1) * 100
        est_nav = data['nav'] * (1 + total_impact / 100)
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

# ==================== Tab 2: 宏观风向与前瞻雷达 ====================
with tab2:
    st.header("🧠 纳指/标普核心驱动因子")
    with st.expander("展开查看：什么事情会引发美股暴涨或暴跌？", expanded=False):
        st.markdown("""
        * **🦅 美联储利率决议 (FOMC会议)：** 影响最大！现任主席沃什主张“缩表”。如果放出加息/强缩表信号，流动性收紧，**高估值科技股（纳指）会暴跌**；如果放出降息信号，**大盘暴涨**。
        * **🛒 核心通胀数据 (CPI / PCE)：** 如果通胀数据**高于预期**，市场担忧美联储加息，**大盘大跌**；如果通胀降温，**大盘大涨**。
        * **👷 就业数据 (非农 NFP)：** 逻辑较复杂。如果失业率猛增（衰退交易），大盘跌；如果就业火爆（通胀担忧），大盘也可能跌；“金发姑娘”状态（就业适中且通胀低）则大涨。
        * **💻 科技巨头财报 (微软、苹果、英伟达等)：** 纳指100极度依赖头部七大巨头。如果巨头对未来的 AI 盈利指引不及预期，哪怕大盘宏观没问题，**纳指也会遭遇重挫**。
        """)

    st.header("🗓️ 近期重磅宏观事件日历 (未来30天)")
    st.write("在以下日期前后的 1-2 天，美股大概率出现**剧烈震荡**，是执行【逢低加仓】策略的关键节点。")

    # 构建事件日历数据框
    calendar_data = [
        {"日期 (北京时间)": "2026年5月22日 (周五晚)", "重磅事件": "🇺🇸 美国5月制造业/服务业PMI", "预期影响等级": "⭐⭐",
         "多空逻辑预判": "PMI跌破50荣枯线可能引发衰退恐慌，科技股承压。"},
        {"日期 (北京时间)": "2026年5月29日 (周五晚)", "重磅事件": "🛒 美国4月核心PCE物价指数", "预期影响等级": "⭐⭐⭐⭐",
         "多空逻辑预判": "美联储最看重的通胀指标。若反弹，纳指面临杀估值风险；若回落，迎来大反弹。"},
        {"日期 (北京时间)": "2026年6月5日  (周五晚)", "重磅事件": "👷 美国5月非农就业报告 (NFP)", "预期影响等级": "⭐⭐⭐⭐",
         "多空逻辑预判": "关注失业率是否飙升。若数据异常强劲，将粉碎市场降息预期。"},
        {"日期 (北京时间)": "2026年6月11日 (周四晚)", "重磅事件": "📉 美国5月CPI数据", "预期影响等级": "⭐⭐⭐⭐⭐",
         "多空逻辑预判": "直接决定次周美联储会议基调。CPI超预期将直接引发大盘全线抛售。"},
        {"日期 (北京时间)": "2026年6月18日 (凌晨)", "重磅事件": "🦅 美联储FOMC利率决议 + 沃什讲话",
         "预期影响等级": "⭐⭐⭐⭐⭐",
         "多空逻辑预判": "季度重磅大戏！不仅公布利率，还将发布“点阵图”。沃什对缩表的态度将决定标普与纳指的长期拐点，当晚极度剧烈波动！"}
    ]

    df_calendar = pd.DataFrame(calendar_data)
    # 隐藏 DataFrame 的行索引进行展示，显得更清爽
    st.dataframe(df_calendar, hide_index=True, use_container_width=True)

    st.info(
        "💡 **操作心法：** 遇到五星级（⭐⭐⭐⭐⭐）事件的前夕，如果大盘在高位，切忌追高（维持300底仓）；如果事件落地引发暴跌（超过5%），立刻切换到 Tab 1，按系统提示的高额度果断吸纳筹码！")
