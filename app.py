import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
import re
from pathlib import Path
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="Google Pay Full Takeout Analytics Dashboard",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (Google Pay Branding & Modern UX)
st.markdown("""
<style>
    /* Global Styles */
    .main {
        background-color: #0E1117;
        font-family: 'Inter', sans-serif;
    }
    
    /* Title Badge */
    .main-header {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }
    .main-title {
        color: #F8FAFC;
        font-size: 2.2rem;
        font-weight: 700;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .main-subtitle {
        color: #94A3B8;
        font-size: 1.05rem;
        margin-top: 6px;
    }
    
    /* KPI Cards */
    .kpi-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 15px rgba(66, 133, 244, 0.15);
    }
    .kpi-label {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94A3B8;
        font-weight: 600;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 1.8rem;
        font-weight: 800;
        color: #F8FAFC;
    }
    .kpi-subtext {
        font-size: 0.8rem;
        color: #38BDF8;
        margin-top: 4px;
    }

    /* Insight Banner */
    .insight-card {
        background: rgba(30, 41, 59, 0.8);
        border-left: 4px solid #4285F4;
        border-radius: 0 8px 8px 0;
        padding: 14px 18px;
        margin-bottom: 12px;
        color: #E2E8F0;
    }

    /* Tab Header Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1E293B;
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        color: #94A3B8;
    }
    .stTabs [aria-selected="true"] {
        background-color: #4285F4 !important;
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)


# Clean Status and Transaction ID Helper
def clean_txn_id_and_status(row):
    st_val = str(row.get('Status', '')).strip()
    raw_id = str(row.get('Transaction_ID', '')).strip()
    if raw_id.lower() == 'nan':
        raw_id = ''
    if st_val.lower() == 'nan':
        st_val = ''

    m = re.search(r'\s+(Completed|Failed|Pending|Cancelled|Refunded|Declined|Success)$', raw_id, re.IGNORECASE)
    if m:
        extracted_status = m.group(1).capitalize()
        clean_id = raw_id[:m.start()].strip()
        if not st_val or st_val == 'Blank/Unspecified':
            st_val = extracted_status
    else:
        clean_id = raw_id

    if not st_val:
        st_val = 'Completed' if clean_id else 'Blank/Unspecified'

    return pd.Series([clean_id, st_val])


# Function to Load Primary Activity CSV
@st.cache_data
def load_activity_data(filepath_or_buffer):
    df = pd.read_csv(filepath_or_buffer)
    df.columns = df.columns.str.strip()
    
    if 'Transaction_ID' in df.columns:
        df[['Transaction_ID', 'Status']] = df.apply(clean_txn_id_and_status, axis=1)

    df['Parsed_Timestamp'] = pd.to_datetime(df['Parsed_Timestamp'], errors='coerce')
    df['Year'] = df['Parsed_Timestamp'].dt.year
    df['Month'] = df['Parsed_Timestamp'].dt.month
    df['Month_Name'] = df['Parsed_Timestamp'].dt.strftime('%b')
    df['Year_Month'] = df['Parsed_Timestamp'].dt.to_period('M').astype(str)
    df['Day_of_Week'] = df['Parsed_Timestamp'].dt.day_name()
    df['Hour'] = df['Parsed_Timestamp'].dt.hour
    df['Date'] = df['Parsed_Timestamp'].dt.date

    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
    df['Recipient_or_Sender'] = df['Recipient_or_Sender'].fillna('Direct Transfer / Unspecified').replace('', 'Direct Transfer / Unspecified')
    df['Status'] = df['Status'].fillna('Blank/Unspecified').replace('', 'Blank/Unspecified')
    df['Payment_Method'] = df['Payment_Method'].fillna('Unspecified Account').replace('', 'Unspecified Account')

    return df


# Loader: Rewards Cashback CSV
@st.cache_data
def load_cashback_rewards():
    path = Path("Rewards earned/Cashback Rewards.csv")
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Reward Amount'] = pd.to_numeric(df['Reward Amount'], errors='coerce').fillna(0.0)
    df['Year'] = df['Date'].dt.year
    df['Year_Month'] = df['Date'].dt.to_period('M').astype(str)
    return df


# Loader: Voucher Rewards JSON
@st.cache_data
def load_voucher_rewards():
    path = Path("Rewards earned/Voucher Rewards.json")
    if not path.exists():
        return pd.DataFrame()
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    if text.startswith(")]}'"):
        text = text[4:].strip()
    try:
        data = json.loads(text)
        records = data.get("couponRewardExportRecord", [])
        df = pd.DataFrame(records)
        if not df.empty and 'expiryTimestamp' in df.columns:
            df['Expiry'] = pd.to_datetime(df['expiryTimestamp'], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()


# Loader: Group Expenses JSON
@st.cache_data
def load_group_expenses():
    path = Path("Group expenses/Group expenses.json")
    if not path.exists():
        return [], pd.DataFrame()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        groups = data.get("Group_expenses", [])
        
        flat_items = []
        for g in groups:
            created_at = g.get("creation_time")
            group_name = g.get("group_name", "General Group")
            total_amt_raw = g.get("total_amount", "0").replace('₹', '').replace(',', '').strip()
            try:
                total_amt = float(total_amt_raw)
            except ValueError:
                total_amt = 0.0
                
            title = g.get("title", "Expense")
            state = g.get("state", "COMPLETED")
            creator = g.get("creator", "Unknown")

            for item in g.get("items", []):
                item_amt_raw = item.get("amount", "0").replace('₹', '').replace(',', '').strip()
                try:
                    item_amt = float(item_amt_raw)
                except ValueError:
                    item_amt = 0.0
                
                flat_items.append({
                    "Group_Name": group_name,
                    "Expense_Title": title if title else "Expense Item",
                    "Total_Expense_Amount": total_amt,
                    "Group_State": state,
                    "Creator": creator,
                    "Creation_Time": pd.to_datetime(created_at, errors='coerce'),
                    "Payer": item.get("payer"),
                    "Share_Amount": item_amt,
                    "Payment_State": item.get("state")
                })
                
        df_items = pd.DataFrame(flat_items)
        return groups, df_items
    except Exception:
        return [], pd.DataFrame()


# Loader: Google Transactions (Play Purchases)
@st.cache_data
def load_google_transactions():
    folder = Path("Google transactions")
    if not folder.exists():
        return pd.DataFrame()
    dfs = []
    for p in folder.glob("*.csv"):
        if p.stat().st_size > 100:
            df = pd.read_csv(p)
            df.columns = df.columns.str.strip()
            if not df.empty:
                dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    df_all = pd.concat(dfs, ignore_index=True)
    df_all['Time'] = pd.to_datetime(df_all['Time'], errors='coerce')
    df_all['Raw_Amount'] = df_all['Amount'].str.replace('INR', '').str.replace('\xa0', '').str.replace(',', '').str.strip()
    df_all['Numeric_Amount'] = pd.to_numeric(df_all['Raw_Amount'], errors='coerce').fillna(0.0)
    return df_all


# Find default CSV path
def get_default_csv():
    candidates = [
        "My_Activity/My_Activity2.csv",
        "My_Activity/My_Activity.csv",
        "My_Activity.csv",
        "My Activity.csv"
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


# Header Title
st.markdown("""
<div class="main-header">
    <div class="main-title">
        <span>🌐 Google Pay Full Takeout Intelligence & YoY Dashboard</span>
    </div>
    <div class="main-subtitle">
        Multi-Source Analytics: Activity Transactions, Group Bill Splits, Cashback Rewards, Vouchers, and Play Store Subscriptions.
    </div>
</div>
""", unsafe_allow_html=True)


# Sidebar Data Loader & Global Filters
st.sidebar.header("📁 Data Source & Filters")

default_csv = get_default_csv()
uploaded_file = st.sidebar.file_uploader("Upload Google Pay Activity CSV", type=["csv"])

if uploaded_file is not None:
    df_raw = load_activity_data(uploaded_file)
elif default_csv is not None:
    st.sidebar.success(f"Loaded Activity Data: `{default_csv}`")
    df_raw = load_activity_data(default_csv)
else:
    st.error("No CSV file found! Please convert `My Activity.html` using `convert_activity_to_csv.py` or upload your CSV.")
    st.stop()

# Load Auxiliary Datasets
df_cashback = load_cashback_rewards()
df_vouchers = load_voucher_rewards()
groups_raw, df_group_items = load_group_expenses()
df_play_txns = load_google_transactions()

# Sidebar Notification for Discovered Files
st.sidebar.markdown("---")
st.sidebar.subheader("📦 Discovered Takeout Files")
st.sidebar.text(f"• Cashback Rewards: {'✅' if not df_cashback.empty else '❌'}")
st.sidebar.text(f"• Voucher Coupons: {'✅' if not df_vouchers.empty else '❌'}")
st.sidebar.text(f"• Group Expenses: {'✅' if not df_group_items.empty else '❌'}")
st.sidebar.text(f"• Play Transactions: {'✅' if not df_play_txns.empty else '❌'}")

# Ensure we have valid timestamps in primary activity
df_valid = df_raw.dropna(subset=['Parsed_Timestamp']).copy()

if df_valid.empty:
    st.error("No valid timestamped records found in dataset.")
    st.stop()

# Sidebar Option: Exclude Pending & Failed Transactions from Financial Totals
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Outflow Settings")
exclude_non_completed = st.sidebar.checkbox(
    "Remove Pending & Failed from Outflow",
    value=True,
    help="When enabled, Pending and Failed transactions are strictly excluded from Total Outflow, Received, and Net Cashflow calculation."
)

# Available Filters
all_years = sorted([int(y) for y in df_valid['Year'].dropna().unique()], reverse=True)
selected_years = st.sidebar.multiselect("Filter by Year(s)", options=all_years, default=all_years)

all_actions = sorted(df_valid['Action'].dropna().unique())
selected_actions = st.sidebar.multiselect("Filter by Action Type", options=all_actions, default=all_actions)

all_statuses = sorted(df_valid['Status'].dropna().unique())
selected_statuses = st.sidebar.multiselect("Filter by Status", options=all_statuses, default=all_statuses)

# Filter Dataset based on sidebar selections
df_filtered = df_valid[
    (df_valid['Year'].isin(selected_years)) &
    (df_valid['Action'].isin(selected_actions)) &
    (df_valid['Status'].isin(selected_statuses))
].copy()

if df_filtered.empty:
    st.warning("No records match the selected filters. Please adjust the sidebar filters.")
    st.stop()

# Dataset for Financial Calculations (excluding Failed & Pending if enabled)
NON_FINANCIAL_STATUSES = ['Failed', 'Pending', 'Cancelled', 'Declined']

if exclude_non_completed:
    df_fin = df_filtered[~df_filtered['Status'].isin(NON_FINANCIAL_STATUSES)].copy()
else:
    df_fin = df_filtered.copy()


# Main Dashboard Tabs
tab_overview, tab_yoy, tab_merchants, tab_rewards, tab_groups, tab_play, tab_banks, tab_temporal, tab_raw = st.tabs([
    "📊 Executive Summary",
    "📈 YoY Insights",
    "🏪 Merchants",
    "🎁 Rewards & Cashbacks",
    "👥 Group Expenses",
    "🛍️ Play & Subscriptions",
    "💳 Payment Methods",
    "⏰ Temporal Trends",
    "🔍 Raw Explorer"
])


# ==========================================
# TAB 1: EXECUTIVE SUMMARY & KPIS
# ==========================================
with tab_overview:
    st.subheader("📌 Overall Financial Snapshot")
    if exclude_non_completed:
        st.info("ℹ️ **Outflow & Financial Totals exclude Pending and Failed transactions** to reflect actual settled funds.")

    # Compute Metrics on Financial Dataset
    paid_df = df_fin[df_fin['Action'] == 'Paid']
    sent_df = df_fin[df_fin['Action'] == 'Sent']
    received_df = df_fin[df_fin['Action'] == 'Received']
    
    total_spent = paid_df['Amount'].sum()
    total_sent = sent_df['Amount'].sum()
    total_outflow = total_spent + total_sent
    total_received = received_df['Amount'].sum()
    net_flow = total_received - total_outflow
    total_txns = len(df_filtered)

    total_cashback = df_cashback['Reward Amount'].sum() if not df_cashback.empty else 0.0
    
    completed_txns = len(df_filtered[df_filtered['Status'] == 'Completed'])
    failed_txns = len(df_filtered[df_filtered['Status'] == 'Failed'])
    pending_txns = len(df_filtered[df_filtered['Status'] == 'Pending'])
    
    avg_txn_size = paid_df['Amount'].mean() if not paid_df.empty else 0.0
    max_txn_val = df_fin['Amount'].max() if not df_fin.empty else 0.0

    # Display KPI Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Settled Outflow</div>
            <div class="kpi-value">₹{total_outflow:,.2f}</div>
            <div class="kpi-subtext">Paid: ₹{total_spent:,.0f} | Sent: ₹{total_sent:,.0f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Total Received</div>
            <div class="kpi-value" style="color:#34A853;">₹{total_received:,.2f}</div>
            <div class="kpi-subtext">{len(received_df):,} Settled Credits</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        net_color = "#34A853" if net_flow >= 0 else "#EA4335"
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Net Cashflow</div>
            <div class="kpi-value" style="color:{net_color};">₹{net_flow:,.2f}</div>
            <div class="kpi-subtext">Received minus Outflow</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Total Transactions</div>
            <div class="kpi-value">{total_txns:,}</div>
            <div class="kpi-subtext">Failed: {failed_txns} | Pending: {pending_txns}</div>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Cashback Rewards Earned</div>
            <div class="kpi-value" style="color:#FBBC05;">₹{total_cashback:,.2f}</div>
            <div class="kpi-subtext">{len(df_vouchers)} Vouchers Earned</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Charts Row 1
    chart_col1, chart_col2 = st.columns([2, 1])

    with chart_col1:
        st.markdown("#### 📉 Cumulative & Monthly Outflow Trend (Settled Transactions)")
        df_monthly = df_fin[df_fin['Action'].isin(['Paid', 'Sent'])].groupby('Year_Month')['Amount'].sum().reset_index()
        df_monthly['Cumulative'] = df_monthly['Amount'].cumsum()

        fig_trend = go.Figure()
        fig_trend.add_trace(go.Bar(
            x=df_monthly['Year_Month'],
            y=df_monthly['Amount'],
            name="Monthly Outflow",
            marker_color="#4285F4",
            opacity=0.75
        ))
        fig_trend.add_trace(go.Scatter(
            x=df_monthly['Year_Month'],
            y=df_monthly['Cumulative'],
            name="Cumulative Outflow",
            line=dict(color="#FBBC05", width=3)
        ))
        fig_trend.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=30, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_trend, use_container_width=True)

    with chart_col2:
        st.markdown("#### 🎯 Settled Action Breakdown")
        df_action_summary = df_fin.groupby('Action')['Amount'].agg(['sum', 'count']).reset_index()
        
        fig_action = px.pie(
            df_action_summary,
            names='Action',
            values='sum',
            hole=0.55,
            color_discrete_sequence=['#EA4335', '#FBBC05', '#34A853', '#4285F4', '#9333EA']
        )
        fig_action.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=30, b=20)
        )
        st.plotly_chart(fig_action, use_container_width=True)


# ==========================================
# TAB 2: YEAR-ON-YEAR (YoY) INSIGHTS
# ==========================================
with tab_yoy:
    st.subheader("📈 Year-on-Year (YoY) Performance & Structural Changes")

    df_yoy_base = df_valid[~df_valid['Status'].isin(NON_FINANCIAL_STATUSES)] if exclude_non_completed else df_valid

    df_yoy_paid = df_yoy_base[df_yoy_base['Action'] == 'Paid'].groupby('Year')['Amount'].agg(Total_Paid='sum', Paid_Count='count').reset_index()
    df_yoy_sent = df_yoy_base[df_yoy_base['Action'] == 'Sent'].groupby('Year')['Amount'].agg(Total_Sent='sum', Sent_Count='count').reset_index()
    df_yoy_received = df_yoy_base[df_yoy_base['Action'] == 'Received'].groupby('Year')['Amount'].agg(Total_Received='sum', Received_Count='count').reset_index()
    df_yoy_total = df_yoy_base.groupby('Year')['Amount'].agg(Total_Volume='sum', Total_Txns='count').reset_index()

    yoy_summary = df_yoy_total.merge(df_yoy_paid, on='Year', how='left')
    yoy_summary = yoy_summary.merge(df_yoy_sent, on='Year', how='left')
    yoy_summary = yoy_summary.merge(df_yoy_received, on='Year', how='left').fillna(0)

    yoy_summary['Total_Outflow'] = yoy_summary['Total_Paid'] + yoy_summary['Total_Sent']
    yoy_summary['Net_Flow'] = yoy_summary['Total_Received'] - yoy_summary['Total_Outflow']
    
    yoy_summary['YoY_Outflow_Growth_%'] = yoy_summary['Total_Outflow'].pct_change() * 100
    yoy_summary['YoY_Txn_Growth_%'] = yoy_summary['Total_Txns'].pct_change() * 100

    if len(yoy_summary) >= 2:
        max_spend_row = yoy_summary.loc[yoy_summary['Total_Outflow'].idxmax()]
        max_growth_row = yoy_summary.loc[yoy_summary['YoY_Outflow_Growth_%'].idxmax()] if not yoy_summary['YoY_Outflow_Growth_%'].isna().all() else None

        st.markdown(f"""
        <div class="insight-card">
            💡 <b>Peak Spending Year:</b> <b>{int(max_spend_row['Year'])}</b> reached the highest overall outflow of <b>₹{max_spend_row['Total_Outflow']:,.2f}</b> across {int(max_spend_row['Total_Txns']):,} settled transactions.
        </div>
        """, unsafe_allow_html=True)

        if max_growth_row is not None and not np.isnan(max_growth_row['YoY_Outflow_Growth_%']):
            st.markdown(f"""
            <div class="insight-card">
                🚀 <b>Highest YoY Expansion:</b> Year <b>{int(max_growth_row['Year'])}</b> saw a <b>+{max_growth_row['YoY_Outflow_Growth_%']:.1f}% YoY growth</b> in annual Google Pay spending.
            </div>
            """, unsafe_allow_html=True)

    st.markdown("#### 📋 Annual YoY Metrics Summary Table (Settled Funds)")
    
    yoy_display = yoy_summary[['Year', 'Total_Outflow', 'YoY_Outflow_Growth_%', 'Total_Received', 'Net_Flow', 'Total_Txns', 'YoY_Txn_Growth_%']].copy()
    yoy_display['Year'] = yoy_display['Year'].astype(str)
    yoy_display['Total_Outflow'] = yoy_display['Total_Outflow'].map('₹{:,.2f}'.format)
    yoy_display['Total_Received'] = yoy_display['Total_Received'].map('₹{:,.2f}'.format)
    yoy_display['Net_Flow'] = yoy_display['Net_Flow'].map('₹{:,.2f}'.format)
    yoy_display['YoY_Outflow_Growth_%'] = yoy_display['YoY_Outflow_Growth_%'].map('{:+.1f}%'.format).replace('+nan%', '-')
    yoy_display['YoY_Txn_Growth_%'] = yoy_display['YoY_Txn_Growth_%'].map('{:+.1f}%'.format).replace('+nan%', '-')
    
    st.dataframe(yoy_display, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col_y1, col_y2 = st.columns(2)

    with col_y1:
        st.markdown("#### 📊 Annual Spending vs Receiving Volume")
        fig_yoy_bar = go.Figure()
        fig_yoy_bar.add_trace(go.Bar(
            x=yoy_summary['Year'].astype(str),
            y=yoy_summary['Total_Outflow'],
            name="Total Outflow (Paid + Sent)",
            marker_color="#EA4335"
        ))
        fig_yoy_bar.add_trace(go.Bar(
            x=yoy_summary['Year'].astype(str),
            y=yoy_summary['Total_Received'],
            name="Total Received",
            marker_color="#34A853"
        ))
        fig_yoy_bar.update_layout(
            barmode='group',
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=30, b=20)
        )
        st.plotly_chart(fig_yoy_bar, use_container_width=True)

    with col_y2:
        st.markdown("#### 📆 Monthly Spend Trajectory across Years")
        df_month_yoy = df_yoy_base[df_yoy_base['Action'].isin(['Paid', 'Sent'])].groupby(['Year', 'Month', 'Month_Name'])['Amount'].sum().reset_index()
        df_month_yoy['Month_Name'] = pd.to_datetime(df_month_yoy['Month'], format='%m').dt.strftime('%b')
        df_month_yoy = df_month_yoy.sort_values('Month')

        fig_month_line = px.line(
            df_month_yoy,
            x='Month_Name',
            y='Amount',
            color=df_month_yoy['Year'].astype(str),
            markers=True,
            labels={'Month_Name': 'Month', 'Amount': 'Total Outflow (₹)', 'color': 'Year'}
        )
        fig_month_line.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=30, b=20)
        )
        st.plotly_chart(fig_month_line, use_container_width=True)


# ==========================================
# TAB 3: MERCHANT INTELLIGENCE
# ==========================================
with tab_merchants:
    st.subheader("🏪 Merchant & Recipient Spending Intelligence")

    col_m1, col_m2 = st.columns(2)
    df_paid_only = df_fin[df_fin['Action'] == 'Paid']

    with col_m1:
        st.markdown("#### 💰 Top 10 Payees by Total Amount")
        top_spend_merchants = df_paid_only.groupby('Recipient_or_Sender')['Amount'].sum().nlargest(10).reset_index()

        fig_top_spend = px.bar(
            top_spend_merchants,
            x='Amount',
            y='Recipient_or_Sender',
            orientation='h',
            color_discrete_sequence=['#4285F4'],
            text_auto=':,.0f'
        )
        fig_top_spend.update_layout(
            yaxis=dict(autorange="reversed"),
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=20, b=20)
        )
        st.plotly_chart(fig_top_spend, use_container_width=True)

    with col_m2:
        st.markdown("#### 🔄 Top 10 Payees by Transaction Frequency")
        top_freq_merchants = df_paid_only.groupby('Recipient_or_Sender')['ID'].count().nlargest(10).reset_index()
        top_freq_merchants.columns = ['Recipient_or_Sender', 'Txn_Count']

        fig_top_freq = px.bar(
            top_freq_merchants,
            x='Txn_Count',
            y='Recipient_or_Sender',
            orientation='h',
            color_discrete_sequence=['#FBBC05'],
            text_auto=':'
        )
        fig_top_freq.update_layout(
            yaxis=dict(autorange="reversed"),
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=20, b=20)
        )
        st.plotly_chart(fig_top_freq, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 🔍 Individual Merchant Deep Dive")

    all_merchants_list = sorted(df_paid_only['Recipient_or_Sender'].unique())
    if all_merchants_list:
        selected_merchant = st.selectbox("Select Merchant / Payee to Analyze:", options=all_merchants_list)
        
        m_df = df_paid_only[df_paid_only['Recipient_or_Sender'] == selected_merchant]
        
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Total Spent", f"₹{m_df['Amount'].sum():,.2f}")
        mc2.metric("Transaction Count", f"{len(m_df):,}")
        mc3.metric("Average Purchase", f"₹{m_df['Amount'].mean():,.2f}")
        mc4.metric("First Transaction", str(m_df['Parsed_Timestamp'].min().date()))

        fig_m_timeline = px.scatter(
            m_df,
            x='Parsed_Timestamp',
            y='Amount',
            size='Amount',
            color='Status',
            title=f"Transaction History: {selected_merchant}",
            hover_data=['Raw_Description', 'Payment_Method']
        )
        fig_m_timeline.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_m_timeline, use_container_width=True)


# ==========================================
# TAB 4: REWARDS & CASHBACKS (NEW)
# ==========================================
with tab_rewards:
    st.subheader("🎁 Google Pay Rewards & Cashback Analytics")

    col_r1, col_r2 = st.columns(2)

    with col_r1:
        st.markdown("#### 💰 Cashback Rewards History")
        if not df_cashback.empty:
            total_cashback_amt = df_cashback['Reward Amount'].sum()
            avg_reward = df_cashback['Reward Amount'].mean()
            st.metric("Total Cashback Won", f"₹{total_cashback_amt:,.2f}", delta=f"{len(df_cashback)} Rewards Won")
            
            df_cb_monthly = df_cashback.groupby('Year_Month')['Reward Amount'].sum().reset_index()
            fig_cb = px.bar(
                df_cb_monthly,
                x='Year_Month',
                y='Reward Amount',
                title="Monthly Cashback Rewards Earned (₹)",
                color_discrete_sequence=['#FBBC05']
            )
            fig_cb.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_cb, use_container_width=True)
        else:
            st.info("No Cashback Rewards CSV data found.")

    with col_r2:
        st.markdown("#### 🎟️ Scratch Card Vouchers & Coupons")
        if not df_vouchers.empty:
            st.metric("Total Vouchers Earned", f"{len(df_vouchers):,} Coupons")
            st.dataframe(df_vouchers[['summary', 'details', 'code', 'Expiry']].dropna(how='all'), use_container_width=True, height=350)
        else:
            st.info("No Voucher Rewards JSON data found.")


# ==========================================
# TAB 5: GROUP EXPENSES & BILL SPLITS (NEW)
# ==========================================
with tab_groups:
    st.subheader("👥 Group Expenses & Shared Trip Splits")

    if not df_group_items.empty:
        g_names = sorted(df_group_items['Group_Name'].unique())
        selected_g = st.selectbox("Select Group / Trip to Inspect:", options=g_names)
        
        g_df = df_group_items[df_group_items['Group_Name'] == selected_g]
        
        gc1, gc2, gc3 = st.columns(3)
        total_g_spend = g_df.groupby('Expense_Title')['Total_Expense_Amount'].first().sum()
        gc1.metric("Group Name", selected_g)
        gc2.metric("Total Group Spend", f"₹{total_g_spend:,.2f}")
        gc3.metric("Unique Expense Items", f"{g_df['Expense_Title'].nunique():,}")
        
        st.markdown("#### 📊 Individual Share & Settlement Summary")
        payer_summary = g_df.groupby(['Payer', 'Payment_State'])['Share_Amount'].sum().reset_index()
        
        fig_g_payer = px.bar(
            payer_summary,
            x='Payer',
            y='Share_Amount',
            color='Payment_State',
            title=f"Individual Shares & Payment Status: {selected_g}",
            barmode='stack',
            color_discrete_map={'PAID_RECEIVED': '#34A853', 'UNPAID': '#EA4335', 'MARK_AS_PAID': '#FBBC05'}
        )
        fig_g_payer.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_g_payer, use_container_width=True)

        st.markdown("#### 📋 Detailed Group Items Breakdown")
        st.dataframe(g_df[['Expense_Title', 'Creator', 'Total_Expense_Amount', 'Payer', 'Share_Amount', 'Payment_State', 'Creation_Time']], use_container_width=True)
    else:
        st.info("No Group Expenses data found.")


# ==========================================
# TAB 6: GOOGLE PLAY & SUBSCRIPTIONS (NEW)
# ==========================================
with tab_play:
    st.subheader("🛍️ Google Play Store Purchases & Digital Subscriptions")

    if not df_play_txns.empty:
        pc1, pc2, pc3 = st.columns(3)
        total_play_amt = df_play_txns['Numeric_Amount'].sum()
        pc1.metric("Total Digital Spend", f"₹{total_play_amt:,.2f}")
        pc2.metric("Total Digital Purchases", f"{len(df_play_txns):,}")
        pc3.metric("Products Purchased", f"{df_play_txns['Product'].nunique():,}")

        col_p1, col_p2 = st.columns(2)

        with col_p1:
            st.markdown("#### 📱 Spend by Product / Category")
            prod_summary = df_play_txns.groupby('Product')['Numeric_Amount'].sum().reset_index()
            fig_play_prod = px.pie(
                prod_summary,
                names='Product',
                values='Numeric_Amount',
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Bold
            )
            fig_play_prod.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_play_prod, use_container_width=True)

        with col_p2:
            st.markdown("#### 📜 Digital Purchases Table")
            st.dataframe(df_play_txns[['Time', 'Description', 'Product', 'Amount', 'Status', 'Payment method']], use_container_width=True, height=300)
    else:
        st.info("No Google Play Transactions CSV data found.")


# ==========================================
# TAB 7: BANK & PAYMENT METHODS
# ==========================================
with tab_banks:
    st.subheader("💳 Bank Accounts & Transaction Status Analysis")

    col_b1, col_b2 = st.columns(2)

    with col_b1:
        st.markdown("#### 🏦 Settled Spending Breakdown by Payment Method / Bank")
        bank_summary = df_fin[df_fin['Action'].isin(['Paid', 'Sent'])].groupby('Payment_Method')['Amount'].sum().reset_index()
        
        fig_bank_donut = px.pie(
            bank_summary,
            names='Payment_Method',
            values='Amount',
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_bank_donut.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_bank_donut, use_container_width=True)

    with col_b2:
        st.markdown("#### ⚠️ Transaction Status Breakdown (Extracted Statuses)")
        status_summary = df_filtered.groupby('Status')['ID'].count().reset_index()
        status_summary.columns = ['Status', 'Count']

        fig_status_bar = px.bar(
            status_summary,
            x='Status',
            y='Count',
            color='Status',
            color_discrete_map={'Completed': '#34A853', 'Failed': '#EA4335', 'Pending': '#FBBC05', 'Blank/Unspecified': '#94A3B8'},
            text_auto=True
        )
        fig_status_bar.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_status_bar, use_container_width=True)


# ==========================================
# TAB 8: TEMPORAL & BEHAVIORAL TRENDS
# ==========================================
with tab_temporal:
    st.subheader("⏰ Spending Timing & Behavioral Heatmaps")

    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.markdown("#### 📅 Outflow by Day of Week (Settled Funds)")
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        df_dow = df_fin[df_fin['Action'].isin(['Paid', 'Sent'])].groupby('Day_of_Week')['Amount'].agg(['sum', 'count']).reindex(day_order).reset_index()

        fig_dow = px.bar(
            df_dow,
            x='Day_of_Week',
            y='sum',
            title="Total Spend per Day of Week",
            color_discrete_sequence=['#34A853'],
            text_auto='.2s'
        )
        fig_dow.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_dow, use_container_width=True)

    with col_t2:
        st.markdown("#### 🕐 Peak Spending Hours (0-23)")
        df_hour = df_fin[df_fin['Action'].isin(['Paid', 'Sent'])].groupby('Hour')['Amount'].sum().reset_index()

        fig_hour = px.line(
            df_hour,
            x='Hour',
            y='Amount',
            markers=True,
            title="Hourly Spending Distribution (24-Hour Clock)",
            line_shape='spline'
        )
        fig_hour.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(tickmode='linear', tick0=0, dtick=2)
        )
        st.plotly_chart(fig_hour, use_container_width=True)

    st.markdown("#### 🗺️ Day of Week vs Hour Spending Heatmap")
    df_heatmap = df_fin[df_fin['Action'].isin(['Paid', 'Sent'])].groupby(['Day_of_Week', 'Hour'])['Amount'].sum().unstack(fill_value=0).reindex(day_order)

    fig_heat = px.imshow(
        df_heatmap,
        labels=dict(x="Hour of Day", y="Day of Week", color="Total Spend (₹)"),
        color_continuous_scale="Viridis",
        aspect="auto"
    )
    fig_heat.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig_heat, use_container_width=True)


# ==========================================
# TAB 9: RAW DATA & EXPORT
# ==========================================
with tab_raw:
    st.subheader("🔍 Explore & Download Extracted Transactions")

    st.markdown("Search or filter records below and export to CSV:")

    search_query = st.text_input("🔍 Search Description, Merchant, or Transaction ID:", "")
    
    if search_query:
        df_display = df_filtered[
            df_filtered['Raw_Description'].str.contains(search_query, case=False, na=False) |
            df_filtered['Recipient_or_Sender'].str.contains(search_query, case=False, na=False) |
            df_filtered['Transaction_ID'].str.contains(search_query, case=False, na=False)
        ]
    else:
        df_display = df_filtered

    st.dataframe(df_display, use_container_width=True, height=450)

    # Download Button
    csv_bytes = df_display.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Cleaned CSV Dataset",
        data=csv_bytes,
        file_name="Google_Pay_Cleaned_Activity.csv",
        mime="text/csv"
    )
