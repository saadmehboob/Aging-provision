import streamlit as st
import pandas as pd
import numpy as np
import re
from io import BytesIO

st.set_page_config(page_title="Aging Provision App", layout="wide")
st.title("📊 Aging Provision Calculator")

# -------------------------------
# Constants and Helpers
# -------------------------------
DAMAGE_PCT = 1.0
LEFTOVER_PCT = 0.15
CLOSED_PCT = 0.5
FIRST_BUCKET_SIZE = 5

@st.cache_data
def load_excel(file):
    return pd.read_excel(file)

def standardize_season(raw_season):
    if not isinstance(raw_season, str) or raw_season.strip() == "":
        return "Unknown"
    season = raw_season.strip().upper()
    if "CONTINUITY" in season or "BASICS" in season:
        return "Continuity"
    if "OLD" in season:
        return "Old-"
    match = re.search(r"(20\d{2})", season)
    if match:
        yr = match.group(1)[2:]
        if any(tag in season for tag in ["SPRING", "SUMMER", "SS"]):
            return f"SS{yr}"
        elif any(tag in season for tag in ["AUTUMN", "WINTER", "AW"]):
            return f"AW{yr}"
    match = re.search(r"(SS|AW)(\d{2})", season)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    if "WA" in season:
        match = re.search(r"WA(\d{2})", season)
        if match:
            return f"AW{match.group(1)}"
    match = re.search(r"(\d{2})", season)
    return f"SS{match.group(1)}" if match else "Unknown"

def season_sort_key(season):
    if not isinstance(season, str) or len(season) < 4:
        return (0, 0)
    season_type = season[:2]
    year = int(season[-2:])
    season_rank = 1 if season_type == "AW" else 0
    return (year, season_rank)

# -------------------------------
# File Upload Section
# -------------------------------
soh_file = st.file_uploader("Upload SOH Excel File", type=["xlsx"])
mapping_file = st.file_uploader("Upload Brand Mapping File", type=["xlsx"])
combo_file = st.file_uploader("Upload Combinations File", type=["xlsx"])

if soh_file and mapping_file and combo_file:
    soh = load_excel(soh_file)
    mapping = load_excel(mapping_file)
    combinations = load_excel(combo_file)

    soh.columns = soh.columns.str.strip().str.lower()
    mapping.columns = mapping.columns.str.strip().str.lower()

    soh = soh[(soh['group_name'] != 'Aleph') & (soh['ar comments'] == 'Consider')]
    if 'closed_status' in soh.columns:
        soh = soh[soh['closed_status'] != 'Exit']

    soh['nettotal_cost'] = pd.to_numeric(soh['nettotal_cost'].fillna(0), errors='coerce')
    soh['group_name'] = soh['group_name'].str.upper()
    mapping['group_name'] = mapping['group_name'].str.upper()
    soh = soh.merge(mapping, on='group_name', how='left')

    soh['std_season'] = soh['season_desc'].apply(standardize_season)
    excluded = {'Unknown', 'Continuity', 'Old-', 'AW97'}
    unique_seasons = [s for s in soh['std_season'].dropna().unique() if s not in excluded]
    sorted_seasons = sorted(unique_seasons, key=season_sort_key, reverse=True)

    bucket1 = sorted_seasons[:FIRST_BUCKET_SIZE]
    bucket2 = sorted_seasons[FIRST_BUCKET_SIZE: FIRST_BUCKET_SIZE + 3]
    bucket3 = sorted_seasons[FIRST_BUCKET_SIZE + 3: FIRST_BUCKET_SIZE + 6]
    bucket4 = sorted_seasons[FIRST_BUCKET_SIZE + 6:]

    bucket1 += ['Unknown', 'Continuity']
    bucket4 += ['Old-', 'AW97']

    soh['season_bucket'] = np.select([
        soh['std_season'].isin(bucket1),
        soh['std_season'].isin(bucket2),
        soh['std_season'].isin(bucket3)
    ], ['bucket1', 'bucket2', 'bucket3'], default='bucket4')

    soh['continuity_factor'] = 0.40
    soh['provision_%_policy'] = soh['season_bucket'].map({
        'bucket1': 0,
        'bucket2': 0.15,
        'bucket3': 0.50,
        'bucket4': 0.75
    })

    soh.loc[soh['model'].isin(['Consignment', 'Guaranteed Margin', 'Buying Pull - Mango']),
             ['provision_amount_policy', 'provision_%_policy', 'continuity_factor']] = 0

    soh['provision_amount_policy'] = soh['nettotal_cost'] * soh['provision_%_policy'] * soh['continuity_factor']

    soh['location_catergory'] = 'Other'
    soh.loc[soh['location_name'].astype(str).str.lower().str.contains('leftover|sulay', na=False), 'location_catergory'] = 'Leftover'
    soh.loc[soh['location_name'].astype(str).str.lower().str.contains('damage', na=False), 'location_catergory'] = 'Damage'

    soh['additional_provision'] = 0
    soh.loc[soh['location_catergory'] == 'Damage', 'additional_provision'] = soh['nettotal_cost'] * DAMAGE_PCT - soh['provision_amount_policy']
    soh.loc[soh['location_catergory'] == 'Leftover', 'additional_provision'] = soh['nettotal_cost'] * LEFTOVER_PCT - soh['provision_amount_policy']
    if 'closed_status' in soh.columns:
        soh.loc[soh['closed_status'] == 'Closed', 'additional_provision'] = soh['nettotal_cost'] * CLOSED_PCT - soh['provision_amount_policy']

    soh.loc[soh['model'].isin(['Consignment', 'Guaranteed Margin', 'Buying Pull - Mango']),
             ['provision_amount_policy', 'provision_%_policy', 'continuity_factor', 'additional_provision']] = 0

    soh['provision_amount_policy'] = soh['provision_amount_policy'].fillna(0)
    soh['additional_provision'] = soh['additional_provision'].fillna(0)
    soh['total provision'] = soh['provision_amount_policy'] + soh['additional_provision']

    st.subheader("📈 Provision Summary")
    summary = soh.groupby('std brand')[['nettotal_cost', 'provision_amount_policy', 'additional_provision', 'total provision']].sum()
    summary['coverage'] = summary['total provision'] / summary['nettotal_cost']
    st.dataframe(summary.style.format("{:.2f}"))

    # Additional summaries
    st.subheader("🧾 Damage Stock Coverage by Brand")
    damage_summary = soh[soh['location_catergory'] == 'Damage'].groupby('std brand')[['nettotal_cost', 'total provision']].sum()
    damage_summary['coverage'] = damage_summary['total provision'] / damage_summary['nettotal_cost']
    st.dataframe(damage_summary.style.format("{:.2f}"))

    st.subheader("🧾 Leftover Stock Coverage by Brand")
    leftover_summary = soh[soh['location_catergory'] == 'Leftover'].groupby('std brand')[['nettotal_cost', 'total provision']].sum()
    leftover_summary['coverage'] = leftover_summary['total provision'] / leftover_summary['nettotal_cost']
    st.dataframe(leftover_summary.style.format("{:.2f}"))

    if 'closed_status' in soh.columns:
        st.subheader("🧾 Closed Stock Coverage by Brand")
        closed_summary = soh[soh['closed_status'] == 'Closed'].groupby('std brand')[['nettotal_cost', 'total provision']].sum()
        closed_summary['coverage'] = closed_summary['total provision'] / closed_summary['nettotal_cost']
        st.dataframe(closed_summary.style.format("{:.2f}"))

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        soh.to_excel(writer, index=False, sheet_name='Provision Detail')
        summary.to_excel(writer, sheet_name='Summary')
        damage_summary.to_excel(writer, sheet_name='Damage Summary')
        leftover_summary.to_excel(writer, sheet_name='Leftover Summary')
        if 'closed_status' in soh.columns:
            closed_summary.to_excel(writer, sheet_name='Closed Summary')
        writer.save()
        st.download_button(
            label="📅 Download Provision Report",
            data=output.getvalue(),
            file_name="aging_provision_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
