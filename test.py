import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import io

# Page config
st.set_page_config(page_title="Aging Provision Dashboard", layout="wide")

# Title
st.title("📊 Aging Provision Policy Dashboard")
st.markdown("""
This dashboard summarizes the financial provision policy applied to inventory buckets based on location and brand status.

### Provision Calculation Logic:
- **Damage**: 100% of net cost
- **Leftover - Closed Brands**: 50%
- **Leftover - Running Brands**: 15%
- **Closed Brands (Other)**: 50%
- **Exclusions**: Consignment / Guaranteed Margin / Buying Pull - Mango → 0%
""")

# Load brand list for override UI
#@st.cache_data
def get_brand_list():
    df = pd.read_excel("Output/aging_provision_combinations.xlsx")
    return sorted(df['Std Brand'].dropna().unique().tolist())

brand_list = get_brand_list()

# Sidebar - Category-level provision sliders
st.sidebar.header("Provision Parameters")
damage_percentage = st.sidebar.slider("Damage %", 0.0, 1.0, 1.0)
leftover_closed_percentage = st.sidebar.slider("Leftover (Closed Brand) %", 0.0, 1.0, 0.5)
leftover_running_percentage = st.sidebar.slider("Leftover (Running Brand) %", 0.0, 1.0, 0.15)
closed_brand_percentage = st.sidebar.slider("Closed Brand (Other Locations) %", 0.0, 1.0, 0.5)

# Sidebar - Brand-level override UI
st.sidebar.header("Brand-Level Overrides")
selected_brands = st.sidebar.multiselect("Select Brands to Override", brand_list)
brand_override = {}
for brand in selected_brands:
    pct = st.sidebar.slider(f"{brand} Override %", 0.0, 1.0, 0.5, key=brand)
    brand_override[brand] = pct

# Load and process data
#@st.cache_data
def load_data(damage_pct, leftover_closed_pct, leftover_running_pct, closed_brand_pct, brand_override=None):
    df = pd.read_excel("Output/aging_provision_combinations.xlsx")
    df['provision_amount_policy'] = df['provision_amount_policy'].fillna(0)
    df['additional_provision'] = 0
    df['Total Provision'] = df['Total Provision'].fillna(0)

    # Damage
    damage = df['location_catergory'] == 'Damage'
    df.loc[damage, 'additional_provision'] = (df.loc[damage, 'NETTOTAL_COST'] * damage_pct) - df.loc[damage, 'provision_amount_policy']

    # Leftover
    leftover_closed = (df['Closed_status'].fillna('') == 'Closed') & (df['location_catergory'] == 'Leftover')
    df.loc[leftover_closed, 'additional_provision'] = (df.loc[leftover_closed, 'NETTOTAL_COST'] * leftover_closed_pct) - df.loc[leftover_closed, 'provision_amount_policy']

    leftover_running = (df['Closed_status'].fillna('') != 'Closed') & (df['location_catergory'] == 'Leftover')
    df.loc[leftover_running, 'additional_provision'] = (df.loc[leftover_running, 'NETTOTAL_COST'] * leftover_running_pct) - df.loc[leftover_running, 'provision_amount_policy']

    # Closed brands other
    closed_other = (df['Closed_status'].fillna('') == 'Closed') & (~df['location_catergory'].isin(['Leftover', 'Damage']))
    df.loc[closed_other, 'additional_provision'] = (df.loc[closed_other, 'NETTOTAL_COST'] * closed_brand_pct) - df.loc[closed_other, 'provision_amount_policy']

    # Exclusions
    df.loc[df['Model'].isin(['Consignment', 'Guaranteed Margin', 'Buying Pull - Mango']),
           ['provision_amount_policy', 'additional_provision']] = 0

    # Apply brand-level override
    if brand_override:
        for brand, override_pct in brand_override.items():
            mask = df['Std Brand'] == brand
            df.loc[mask, 'additional_provision'] = (df.loc[mask, 'NETTOTAL_COST'] * override_pct) - df.loc[mask, 'provision_amount_policy']

    df['Total Provision'] = df['provision_amount_policy'] + df['additional_provision']
    return df

# Load data
soh = load_data(
    damage_pct=damage_percentage,
    leftover_closed_pct=leftover_closed_percentage,
    leftover_running_pct=leftover_running_percentage,
    closed_brand_pct=closed_brand_percentage,
    brand_override=brand_override
)

# Summary table
summary = soh.groupby("Std Brand")[['NETTOTAL_COST', 'provision_amount_policy', 'additional_provision', 'Total Provision']].sum()
summary['coverage'] = summary['Total Provision'] / summary['NETTOTAL_COST']
summary = summary.fillna(0)

def format_summary(df):
    df = df.copy()
    for col in ['NETTOTAL_COST', 'provision_amount_policy', 'additional_provision', 'Total Provision']:
        if col not in df.columns:
            df[col] = 0
    if 'coverage' not in df.columns:
        df['coverage'] = 0
    df[['NETTOTAL_COST', 'provision_amount_policy', 'additional_provision', 'Total Provision']] = df[
        ['NETTOTAL_COST', 'provision_amount_policy', 'additional_provision', 'Total Provision']
    ].fillna(0).round(0).astype(int)
    df['coverage'] = df['coverage'].fillna(0).apply(lambda x: f"{x:.0%}" if pd.notnull(x) else "0%")
    return df

# Tabs
tab1, tab2, tab3 = st.tabs(["Summary", "Category Analysis", "Graphs"])

with tab1:
    st.subheader("Total Summary by Brand")
    st.dataframe(format_summary(summary))

    # Grand Totals
    grand = summary[['NETTOTAL_COST', 'provision_amount_policy', 'additional_provision', 'Total Provision']].sum()
    grand['coverage'] = f"{(grand['Total Provision'] / grand['NETTOTAL_COST']):.0%}" if grand['NETTOTAL_COST'] else "0%"
    st.markdown("**Grand Totals:**")
    st.write(grand.to_frame().T)

    # Export button
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        soh.to_excel(writer, index=False, sheet_name='Base Table')
        summary.to_excel(writer, sheet_name='Summary')

    # 🔥 This line is essential
    buffer.seek(0)

    st.download_button(
        label="📥 Download Provision Data",
        data=buffer,
        file_name="provision_analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


with tab2:
    st.subheader("Category-Based Summary")
    col1, col2, col3 = st.columns(3)

    with col1:
        dmg = soh[soh['location_catergory'] == 'Damage'].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
        dmg['coverage'] = dmg['Total Provision'] / dmg['NETTOTAL_COST']
        st.metric("Damage Avg Coverage", f"{dmg['coverage'].mean():.0%}")
        st.dataframe(format_summary(dmg))

    with col2:
        lft = soh[soh['location_catergory'] == 'Leftover'].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
        lft['coverage'] = lft['Total Provision'] / lft['NETTOTAL_COST']
        st.metric("Leftover Avg Coverage", f"{lft['coverage'].mean():.0%}")
        st.dataframe(format_summary(lft))

    with col3:
        cls = soh[soh['Closed_status'].fillna('') == 'Closed'].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
        cls['coverage'] = cls['Total Provision'] / cls['NETTOTAL_COST']
        st.metric("Closed Brand Avg Coverage", f"{cls['coverage'].mean():.0%}")
        st.dataframe(format_summary(cls))

with tab3:
    st.subheader("Graphs")
    fig, ax = plt.subplots(figsize=(12, 5))
    top = summary.sort_values('Total Provision', ascending=False).head(10)
    ax.bar(top.index, top['NETTOTAL_COST'], label='Net Cost', alpha=0.6)
    ax.bar(top.index, top['Total Provision'], label='Total Provision', alpha=0.9)
    ax.set_title("Top 10 Brands by Provision")
    ax.set_ylabel("SAR")
    ax.legend()
    plt.xticks(rotation=45)
    st.pyplot(fig)

    st.subheader("Coverage Ratio Distribution")
    fig2, ax2 = plt.subplots()
    sns.histplot(summary['coverage'].astype(float), bins=10, kde=True, ax=ax2)
    ax2.set_title("Coverage Distribution")
    ax2.set_xlabel("Coverage Ratio")
    st.pyplot(fig2)
