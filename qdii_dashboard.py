import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

# ==================== 1. 基础配置与自动刷新 ====================
st.set_page_config(page_title="QDII 智投工作台", layout="wide", initial_sidebar_state="collapsed")

# 自动刷新保持在 60 秒
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

# ==================== 2. 核心算法数据抓取 (缓存 60 秒防卡) ====================
@st.cache_data(ttl=60)
def fetch_all_market_data():
    results = {}
    for code, info in FUND_POOL.items():
        # 1. 抓取基金净值
        try:
            f_url = f"http://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex=1&pageSize=20"
            res = requests.get(f_url, headers=HEADERS, timeout=3).json()
            nav_data = res['Data']['LSJZList']
            latest_nav = float(nav_data[0]['DWJZ'])
            prev_nav = float(nav_data[1]['DWJZ'])
            high_nav = max([float(i['DWJZ']) for i in nav_data])
            daily_gain = (latest_nav - prev_nav) / prev_nav * 100
        except:
            continue

        # 2. 抓取美股 ETF (正盘 + 夜盘)
        try:
            e_url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={info['etf']}&fields=f3,f192"
            e_res = requests.get(e_url, headers=HEADERS, timeout=3).json()
            f3, f192 = e_res['data']['f3'], e_res['data']['f192']
            reg_pct = float(f3) if f3 not in ["-", None] else 0.0
            ext_pct = float(f192) if f192 not in ["-", None] else 0.0
            
            if reg_pct == 0:
                k_url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={info['etf']}&fields1=f1&fields2=f59&klt=101&lmt=1"
                k_res = requests.get(k_url, timeout=3).json()
                reg_pct = float(k_res['data']['klines'][0].split(',')[1])
        except:
            reg_pct, ext_pct = 0.0, 0.0

        results[code] = {
            "nav": latest_nav, "high": high_nav, "daily": daily_gain, 
            "reg": reg_pct, "ext": ext_pct
        }
    return results

# ==================== 3. 动态宏观事件抓取引擎 (核心新增) ====================
@st.cache_data(ttl=3600) # 宏观事件不需要一分钟一刷，设置 1 小时缓存即可，大幅加快速度
def fetch_live_macro_calendar():
    """全自动穿透抓取未来7天美国重磅金融事件"""
    event_list = []
    today = datetime.now(ZoneInfo("Asia/Shanghai"))
    
    # 获取未来 7 天的日期序列
    for i in range(7):
        target_date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        url = f"https://rili.jin10.com/api/day/{target_date}/economic"
        headers = {"x-app-id": "rili", "user-agent": "Mozilla/5.0"}
        
        try:
            res = requests.get(url, headers=headers, timeout=4).json()
            for item in res.get('data', []):
                # 策略强过滤：国家必须是美国(US)，且重要性星级必须 >= 3星
                if item.get('country') == '美国' and int(item.get('star', 0)) >= 3:
                    stars = "⭐" * int(item.get('star', 0))
                    pub_time = item.get('pub_time', '')
                    time_short = pub_time.split(" ")[1] if " " in pub_time else pub_time
                    
                    event_list.append({
                        "日期": item.get('date', target_date),
                        "发布时间 (BJ)": time_short,
                        "指标/重磅事件": item.get('title', ''),
                        "重要等级": stars,
                        "前值": item.get('previous', '-'),
                        "预测值": item.get('consensus', '-')
                    })
        except:
            pass
            
    if not event_list:
        return pd.DataFrame([{"提示": "暂无未来一星期的美国重大事件数据，请稍后刷新重试"}])
        
    df = pd.DataFrame(event_list)
    return df.sort_values(by=["日期", "发布时间 (BJ)"])

def get_strategy(drop_pct, baseline, limit):
    if drop_pct >= 15: buy, tag = baseline + 8000, "🔴 15% 深度回撤"
    elif drop_pct >= 10: buy, tag = baseline + 5000, "🟠 10% 中度回撤"
    elif drop_pct >= 5: buy, tag = baseline + 3000, "🟡 5% 常规回撤"
    elif drop_pct >= 2: buy, tag = baseline + 1000, "🔹 小幅回调"
    else: buy, tag = baseline, "🟢 正常震荡"
    
    final_buy = min(buy, limit)
    is_max = " (触顶!)" if buy >= limit else ""
    return final_buy, f"{tag}{is_max}"

# ==================== 4. 网页布局与双时区对齐 ====================
st.title("📈 美股 QDII 智投工作台")

now_bj = datetime.now(ZoneInfo("Asia/Shanghai"))
now_ny = datetime.now(ZoneInfo("America/New_York"))

bj_time_str = now_bj.strftime('%Y-%m-%d %H:%M:%S')
ny_time_str = now_ny.strftime('%Y-%m-%d %H:%M:%S')

ny_time_float = now_ny.hour + now_ny.minute / 60.0
if now_ny.weekday() >= 6: market_status = " 💤 周末休市中"
elif now_ny.weekday() == 5: market_status = " 💤 周末休市中"
elif 4.0 <= ny_time_float < 9.5: market_status = " 🌅 美股盘前交易 (Pre-market)"
elif 9.5 <= ny_time_float < 16.0: market_status = " 🟢 美股正盘交易 (Regular Session)"
elif 16.0 <= ny_time_float < 20.0: market_status = " 🌆 美股盘后交易 (After-hours)"
else: market_status = " 🌙 美股夜盘/停盘时段"

st.markdown(f"""
| 📍 观察哨位置 | 📅 实时当前时间 | 🕒 当前盘面状态 |
| :--- | :--- | :--- |
| **北京时间 (CN)** | `{bj_time_str}` | 截单倒计时/隔夜复盘 |
| **纽约时间 (US)** | `{ny_time_str}` | **{market_status}** |
""")
st.divider() 

# 统一读取数据流
all_data = fetch_all_market_data()

# 创建双标签页
tab1, tab2 = st.tabs(["💰 核心建仓与预测", "📅 实时动态宏观雷达"])

# ==================== Tab 1: 核心建仓 ====================
with tab1:
    for code, info in FUND_POOL.items():
        if code not in all_data:
            st.error(f"{info['name']} 数据加载失败")
            continue
        
        data = all_data[code]
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

    st.success("提示：15:00 前申购按当晚美股收盘价结算。")

# ==================== Tab 2: 动态宏观日历 (全新注入) ====================
with tab2:
    st.header("🧠 纳指/标普核心驱动因子")
    with st.expander("展开复习：什么事情会引发美股暴涨或暴跌？", expanded=False):
        st.markdown("""
        * **🦅 美联储利率决议 (FOMC)：** 现任主席沃什主张缩表。释放流动性紧缩信号则科技股暴跌，反之大涨。
        * **🛒 核心通胀数据 (CPI / PCE)：** 通胀超预期则市场担忧加息，大盘大跌；通胀降温则杀估值警报解除，科技股大涨。
        * **👷 就业数据 (非农 NFP / 失业率)：** 失业率过高引发衰退交易（大跌）；就业过分火爆引发通胀死灰复燃（大跌）。
        """)

    st.header("🗓️ 实时追踪：未来7天美股重磅事件")
    st.write("以下数据由系统自动抓取，包含当前时间向后推移7天内的**所有美国3星级以上核心经济数据**：")
    
    # 动态调取金十实时日历数据
    with st.spinner("正在穿透公网拉取最新宏观日历..."):
        df_live_calendar = fetch_live_macro_calendar()
        
    st.dataframe(df_live_calendar, hide_index=True, use_container_width=True)
    st.info("💡 **实战雷达提示：** 如果表格中出现了 4 星（⭐⭐⭐⭐）或 5 星（⭐⭐⭐⭐⭐）的数据（如核心 CPI、PCE、非农、利率决议），在其发布当日下午 14:45，大盘往往极度敏感。如果伴随盘前大幅下杀，可根据 Tab 1 的策略提示执行防御性加仓。")
