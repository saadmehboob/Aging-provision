import streamlit as st
import pandas as pd
import numpy as np
import re

st.set_page_config(page_title="Aging Provision Dashboard", layout="wide")
st.title("📦 Aging Provision Streamlit App")

st.sidebar.header("📌 Parameters")
first_first_bucket_number_seasons = st.sidebar.slider("Seasons in Bucket 1", 1, 10, 5)
damage_percentage = st.sidebar.slider("Damage Provision %", 0.0, 1.0, 1.0)
leftover_running_percentage = st.sidebar.slider("Leftover Running Brand %", 0.0, 1.0, 0.15)
leftover_closed_percentage = st.sidebar.slider("Leftover Closed Brand %", 0.0, 1.0, 0.50)
closed_percentage = st.sidebar.slider("Closed Brands %", 0.0, 1.0, 0.50)

brand_input = st.sidebar.text_area("Brand Specific Provision\nFormat: BRAND=0.5,BRAND2=0.2")
brand_specific_provision = {}
if brand_input:
    try:
        for item in brand_input.split(','):
            k, v = item.split('=')
            brand_specific_provision[k.strip().upper()] = float(v)
    except:
        st.sidebar.warning("Invalid brand override format.")


tabs = st.tabs(["Brand Summary", "Checks", "Category Analysis", "Diff Entry"])

# ---- File Upload ----
with tabs[0]:
    st.header("Upload SOH File")
    soh_file = st.file_uploader("Upload SOH Report", type=["xlsx"])

if soh_file:
    # --- Load Files ---
    soh = pd.read_excel(soh_file, sheet_name='Sheet1')
    soh = soh[(soh['GROUP_NAME'] != 'Aleph') & (soh['AR Comments'] == 'Consider')]
    soh['NETTOTAL_COST'].fillna(0, inplace=True)
    soh['NETTOTAL_COST'] = pd.to_numeric(soh['NETTOTAL_COST'], errors='coerce')

    original_season = 'SEASON_DESC' if 'SEASON_DESC' in soh.columns else 'SEASON DESC'

    def season_sort_key(season):
        if not isinstance(season, str) or len(season) < 4:
            return (0, 0)
        season_type = season[:2]
        year = int(season[-2:])
        season_rank = 1 if season_type == "AW" else 0
        return (year, season_rank)

    def standardize_season(raw_season):
        if not isinstance(raw_season, str) or raw_season.strip() == "":
            return "Unknown"
        season = raw_season.strip().upper()
        if "CONTINUITY" in season or "BASICS" in season:
            return "Continuity"
        elif "OLD" in season:
            return "Old-"
        year_match = re.search(r"(20\d{2})", season)
        if year_match:
            year = year_match.group(1)[2:]
            if any(tag in season for tag in ["SPRING", "SUMMER", "SS"]):
                return f"SS{year}"
            elif any(tag in season for tag in ["AUTUMN", "WINTER", "AW"]):
                return f"AW{year}"
        match = re.search(r"(SS|AW)(\d{2})", season)
        if match:
            return f"{match.group(1)}{match.group(2)}"
        match = re.search(r"WA(\d{2})", season)
        if match:
            return f"AW{match.group(1)}"
        match = re.search(r"(\d{2})", season)
        if match:
            return f"SS{match.group(1)}"
        return "Unknown"

    soh['std_season'] = soh[original_season].apply(standardize_season)
    excluded = {'Unknown', 'Continuity', 'Old-', 'AW97'}
    unique_season = [f for f in soh['std_season'].dropna().unique() if f not in excluded]
    sorted_std_season = sorted(unique_season, key=season_sort_key, reverse=True)

    bucket1 = sorted_std_season[:first_first_bucket_number_seasons] + ['Unknown', 'Continuity']
    bucket2 = sorted_std_season[first_first_bucket_number_seasons:first_first_bucket_number_seasons + 3]
    bucket3 = sorted_std_season[first_first_bucket_number_seasons + 3:first_first_bucket_number_seasons + 6]
    bucket4 = sorted_std_season[first_first_bucket_number_seasons + 6:] + ['Old-', 'AW97']

    soh['season_bucket'] = np.select(
        [soh['std_season'].isin(bucket1), soh['std_season'].isin(bucket2), soh['std_season'].isin(bucket3)],
        ['bucket1', 'bucket2', 'bucket3'],
        default='bucket4')

    soh['Continuity_factor'] = 0.40
    soh['provision_%_policy'] = soh['season_bucket'].map({
        'bucket1': 0,
        'bucket2': leftover_running_percentage,
        'bucket3': leftover_closed_percentage,
        'bucket4': closed_percentage
    })

    soh.loc[soh['Model'].isin(['Consignment', 'Guaranteed Margin', 'Buying Pull - Mango']),
            ['provision_amount_policy', 'provision_%_policy', 'Continuity_factor']] = 0
    soh['provision_amount_policy'] = soh['NETTOTAL_COST'] * soh['provision_%_policy'] * soh['Continuity_factor']

    soh['location_catergory'] = "Store, Online & WH"
    soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('leftover', na=False), "location_catergory"] = "Leftover"
    soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('damage', na=False), "location_catergory"] = "Damage"
    soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('sulay', na=False), "location_catergory"] = "Leftover"

    soh['additional_provision'] = 0.0
    soh.loc[soh['location_catergory'] == "Damage", 'additional_provision'] = soh["NETTOTAL_COST"] * damage_percentage - soh['provision_amount_policy']

    soh.loc[(soh['Closed_status'] == "Closed") & (soh['location_catergory'] == "Leftover"),
            'additional_provision'] = soh["NETTOTAL_COST"] * leftover_closed_percentage - soh['provision_amount_policy']

    soh.loc[(soh['Closed_status'] != "Closed") & (soh['location_catergory'] == "Leftover"),
            'additional_provision'] = soh["NETTOTAL_COST"] * leftover_running_percentage - soh['provision_amount_policy']

    soh.loc[(soh['Closed_status'] == "Closed") & (~soh['location_catergory'].isin(["Leftover", "Damage"])),
            'additional_provision'] = soh["NETTOTAL_COST"] * closed_percentage - soh['provision_amount_policy']

    if brand_specific_provision:
        soh['additional_provision'] = np.where(
            soh['Std Brand'].isin(brand_specific_provision.keys()),
            soh['NETTOTAL_COST'] * soh['Std Brand'].map(brand_specific_provision) - soh['provision_amount_policy'],
            soh['additional_provision']
        )

    soh['provision_amount_policy'].fillna(0, inplace=True)
    soh['additional_provision'].fillna(0, inplace=True)
    soh['Total Provision'] = soh['provision_amount_policy'] + soh['additional_provision']

    with tabs[0]:
        st.header("📊 Brand Summary")
        summary = soh.groupby('Std Brand')[['NETTOTAL_COST', 'provision_amount_policy', 'additional_provision', 'Total Provision']].sum()
        summary['coverage'] = summary['Total Provision'] / summary['NETTOTAL_COST']
        st.dataframe(summary)

        st.download_button("Download Detailed Provision", soh.to_csv(index=False).encode(), "provision_detail.csv")

    with tabs[1]:
        st.header("🔍 Checks")
        st.subheader("Buckets Preview")
        st.write(pd.DataFrame({'bucket1': bucket1, 'bucket2': bucket2, 'bucket3': bucket3, 'bucket4': bucket4}))

        st.subheader("Seasons Preview")
        st.write(soh[[original_season, 'std_season']].drop_duplicates())

    with tabs[2]:
        st.header("📈 Category-wise Analysis")
        for category in ['Damage', 'Leftover', 'Closed']:
            st.subheader(f"{category} Category")
            if category == 'Closed':
                df = soh[soh['Closed_status'] == 'Closed']
            else:
                df = soh[soh['location_catergory'] == category]
            group = df.groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
            group['coverage'] = group['Total Provision'] / group['NETTOTAL_COST']
            st.dataframe(group)

    with tabs[3]:
        st.header("📥 Upload Current Balances")
        balance_file = st.file_uploader("Upload Balance File", type=['xlsx'])
        if balance_file:
            existing_balances = pd.read_excel(balance_file)
            s1_cols = ['s1', 's2', 's3', 's4']
            soh[s1_cols] = 0  # Add fake combination data here or update based on your logic

            merged = soh.groupby(s1_cols)['Total Provision'].sum().reset_index().merge(
                existing_balances, on=s1_cols, how='outer').fillna(0)
            merged['Dr/(CR)'] = (merged['Total Provision'] + merged['Closing balance']) * -1
            merged['s5'] = 23993

            merged2 = merged.copy()
            merged2['Dr/(CR)'] *= -1
            merged2['s5'] = 63002
            diff_entry = pd.concat([merged, merged2], ignore_index=True)
            st.dataframe(diff_entry)
            st.download_button("Download Diff Entry", diff_entry.to_csv(index=False).encode(), "diff_entry.csv")
