# Aging Provision Streamlit App
import streamlit as st
import pandas as pd
import numpy as np
import io
import re

from process_soh_file import process_soh_file  # function containing all logic

st.set_page_config(page_title="Aging Provision Dashboard", layout="wide")
st.title("📊 Aging Provision Policy Dashboard")

# Sidebar - Parameters
st.sidebar.header("Provision Parameters")
first_bucket_seasons = st.sidebar.slider("# of Seasons in Bucket 1", min_value=1, max_value=12, value=5)
damage_pct = st.sidebar.slider("Damage Provision %", min_value=0.0, max_value=1.0, value=1.0)
leftover_closed_pct = st.sidebar.slider("Leftover - Closed Brand %", 0.0, 1.0, 0.5)
leftover_running_pct = st.sidebar.slider("Leftover - Running Brand %", 0.0, 1.0, 0.15)
closed_brand_pct = st.sidebar.slider("Closed Brand Other %", 0.0, 1.0, 0.5)

# Brand-specific override
brand_override = {}
st.sidebar.subheader("Brand Specific Provision Overrides")
with st.sidebar.expander("Add Override"):
    override_brand = st.text_input("Brand Name")
    override_pct = st.number_input("Provision %", 0.0, 1.0, 0.0)
    if st.button("Add Override") and override_brand:
        brand_override[override_brand.upper()] = override_pct

# Upload SOH file
st.sidebar.header("Upload Reports")
soh_file = st.sidebar.file_uploader("Upload SOH Report", type=[".xlsx"])
current_balance_file = st.sidebar.file_uploader("Upload Current Balances", type=[".xlsx"])

if soh_file:
    result = process_soh_file(
        soh_file,
        first_bucket_seasons,
        damage_pct,
        leftover_running_pct,
        leftover_closed_pct,
        closed_brand_pct,
        brand_override,
        current_balance_file
    )

    tab1, tab2, tab3, tab4 = st.tabs(["Summary", "Checks", "Category Analysis", "Diff Entry"])

    with tab1:
        st.subheader("Brand-wise Provision Summary")
        st.dataframe(result["summary"])
        st.download_button("📥 Download Provision Details", result["provision_csv"], file_name="aging_provision.csv")

    with tab2:
        st.subheader("Validation Checks")
        st.write("Bucket Validation")
        st.dataframe(result["checks"]["check_buckets"])
        st.write("Season Mapping")
        st.dataframe(result["checks"]["check_season"])
        st.write("Missing Combinations")
        st.dataframe(result["checks"]["missing_combinations"])

    with tab3:
        st.subheader("Category Coverage Ratios")
        st.write("**Damage Inventory**")
        st.dataframe(result["damage_summary"])
        st.write("**Leftover Inventory**")
        st.dataframe(result["leftover_summary"])
        st.write("**Closed Brands**")
        st.dataframe(result["closed_summary"])

    with tab4:
        st.subheader("Difference Entry Based on Current Balances")
        st.dataframe(result["diff_entry"])
        st.download_button("📥 Download Diff Entry", result["diff_csv"], file_name="diff_entry.csv")
else:
    st.info("Please upload the SOH file to begin analysis.")
