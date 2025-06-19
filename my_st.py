import streamlit as st
import pandas as pd
from my_funct import run_aging_provision_pipeline
import io

st.set_page_config(page_title="Aging Provision Dashboard", layout="wide")
st.title("📦 Inventory Aging Provision Dashboard")

st.markdown("""
Upload the required input files to compute the provision:
- **SOH file** (Stock On Hand)
- **Existing balance file** (for reconciliation)
*Mapping and Combinations files are loaded from default internal paths.*
""")

brand_specific_provision = {}

soh_file = st.file_uploader("Upload SOH File", type=["xlsx"])
balance_file = st.file_uploader("Upload Existing Balance File", type=["xlsx"], key="balance")

DEFAULT_MAPPING_PATH = "Mapping & Combinations/mapping.xlsx"
DEFAULT_COMBINATIONS_PATH = "Mapping & Combinations/combinations.xlsx"

unique_brands = []
if soh_file:
    try:
        df_preview = pd.read_excel(soh_file)
        if 'GROUP_NAME' in df_preview.columns:
            unique_brands = sorted(df_preview['GROUP_NAME'].dropna().str.upper().unique().astype(str).tolist())
    except Exception as e:
        st.warning(f"Could not read brand list from SOH: {e}")

with st.sidebar:
    first_first_bucket_number_seasons = st.number_input("# of Seasons in Bucket 1", min_value=1, max_value=10, value=5)
    damage_percentage = st.slider("Damage Provision %", 0.0, 1.0, 1.0)
    leftover_running_percentage = st.slider("Leftover - Running Brand %", 0.0, 1.0, 0.15)
    leftover_closed_percentage = st.slider("Leftover - Closed Brand %", 0.0, 1.0, 0.50)
    closed_percentage = st.slider("Closed Brand (Other) %", 0.0, 1.0, 0.50)

    st.markdown("---")
    st.subheader("🔧 Brand-Specific Provision Override")
    if unique_brands:
        selected_brands = st.multiselect("Select brands to override", options=unique_brands)
        for brand in selected_brands:
            override_val = st.slider(f"{brand} Provision %", min_value=0.0, max_value=5.0, step=0.05, value=0.5)
            brand_specific_provision[brand.upper()] = override_val
    else:
        st.caption("Upload SOH file to enable brand override.")

if soh_file and balance_file:
    with st.spinner("Running provision logic. Please wait..."):
        results = run_aging_provision_pipeline(
            soh_path=soh_file,
            mapping_path=DEFAULT_MAPPING_PATH,
            combinations_path=DEFAULT_COMBINATIONS_PATH,
            balance_path=balance_file,
            first_first_bucket_number_seasons=first_first_bucket_number_seasons,
            damage_percentage=damage_percentage,
            leftover_running_percentage=leftover_running_percentage,
            leftover_closed_percentage=leftover_closed_percentage,
            closed_percentage=closed_percentage,
            brand_specific_provision=brand_specific_provision
        )

    st.success("Provisioning complete!")

    st.subheader("Summary by Std Brand")
    st.dataframe(results["summary"].style.format("{:.2f}"))

    st.markdown("### \U0001F4CA Grand Totals")
    total_cost = results["summary"]["NETTOTAL_COST"].sum()
    total_provision = results["summary"]["Total Provision"].sum()
    avg_coverage = (results["summary"]["coverage"].mean()) * 100
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Net Cost", f"{total_cost:,.2f}")
    col2.metric("Total Provision", f"{total_provision:,.2f}")
    col3.metric("Avg Coverage %", f"{avg_coverage:.2f}%")

    st.download_button("Download Aging Provision CSV", data=results["soh"].to_csv(index=False).encode(),
                       file_name="aging_provision.csv")
    st.download_button("Download Completed Entry", data=results["completed_entry"].to_csv(index=False).encode(),
                       file_name="completed_entry.csv")
    st.download_button("Download Diff Entry", data=results["diff_entry"].to_csv(index=False).encode(),
                       file_name="diff_entry.csv")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        results["soh_comb"].to_excel(writer, index=False)
    st.download_button("Download Combinations Output", data=buffer.getvalue(),
                       file_name="aging_provision_combinations.xlsx")