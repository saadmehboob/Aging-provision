import streamlit as st
import pandas as pd
from my_funct import run_aging_provision_pipeline, get_GL_entry, get_analysis
import io
import os
#from dotenv import load_dotenv

try:
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env
except Exception as e:
    pass



st.set_page_config(page_title="Inventory Aging Provision Dashboard", layout="wide")


st.title("📦 Inventory Aging Provision Dashboard")
PASSWORD = os.getenv("APP_PASSWORD")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

def check_password():
    if st.session_state["password_input"] == PASSWORD:
        st.session_state["authenticated"] = True
    else:
        st.session_state["authenticated"] = False
        st.session_state["password_error"] = True

# Show login if not authenticated
if not st.session_state["authenticated"]:
    st.title("🔐 Login Required")

    # Input field and bind to session_state
    st.text_input("Enter password:", type="password", key="password_input", on_change=check_password)

    # Optional: show error on bad attempt
    if st.session_state.get("password_error"):
        st.error("❌ Incorrect password")
    st.stop()

# 🔓 Logged in — app continues here
st.success("✅ Logged in successfully!")

os.makedirs("Output", exist_ok=True)
brand_specific_provision = {}

tab1, tab2, tab3 = st.tabs(["🧾 Provision Summary", "📊 Analysis", "📄 GL Entries"])

with tab1:
    st.markdown("""
    Upload the required **SOH file** to compute the provision:
    - **SOH file** (Stock On Hand)
    *Mapping and Combinations files are loaded from default internal paths.*
    """)

    soh_file = st.file_uploader("Upload SOH File", type=["xlsx"], key="soh")
    
    skip_upload = st.checkbox("🔁 Skip mapping & combination upload and use default files")

    if skip_upload:
        mapping_file = "mapping.xlsx"
        combinations_file = "combinations.xlsx"

        with open("mapping.xlsx", "rb") as f:
            st.download_button("⬇️ Download Mapping File", f, file_name="mapping.xlsx")

        with open("combinations.xlsx", "rb") as f:
            st.download_button("⬇️ Download Combinations File", f, file_name="combinations.xlsx")

    else:
        combinations_file = st.file_uploader("Upload Combinations File", type=["xlsx"], key="combinations")
        mapping_file = st.file_uploader("Upload Mapping File", type=["xlsx"], key="mapping")


    unique_brands = []  

    if soh_file:
        try:
            df_preview = pd.read_excel('mapping.xlsx', nrows=55)
            if 'Std Brand' in df_preview.columns:
                unique_brands = sorted(df_preview['Std Brand'].dropna().unique().astype(str).tolist())
        except Exception as e:
            st.warning(f"Could not read brand list from combinations: {e}")

    with st.sidebar:
        
        st.subheader("⚙️ Provision Parameters")
        damage_percentage = st.slider("Damage Provision %", 0.0, 1.0, 1.0)
        leftover_running_percentage = st.slider("Leftover - Running Brand %", 0.0, 1.0, 0.15)
        leftover_closed_percentage = st.slider("Leftover - Closed Brand %", 0.0, 1.0, 0.50)
        closed_percentage = st.slider("Closed Brand (Other) %", 0.0, 1.0, 0.50)
        st.markdown("---")
        st.subheader("⚙️ Bucket Parameters")
        first_first_bucket_number_seasons = st.number_input("Number of Seasons in Bucket 1", min_value=1, max_value=10, value=5)
        unknown_season_in_bucket1 = st.checkbox("Include Unknown Season in Bucket 1", value=True)
        st.markdown("---")
        
        st.subheader("🔧 Brand-Specific Provision Override")
        if unique_brands:
            selected_brands = st.multiselect("Select brands to override", options=unique_brands)
            for brand in selected_brands:
                override_val = st.slider(f"{brand} Provision %", min_value=0.0, max_value=1.0, step=0.05, value=0.5)
                brand_specific_provision[brand] = override_val
            
        else:
            st.caption("Upload SOH file to enable brand override.")
        
    if soh_file and combinations_file and mapping_file:
        with st.spinner("Running provision logic. Please wait..."):
            results = run_aging_provision_pipeline(
                soh_path=soh_file,
                mapping=mapping_file,
                combinations=combinations_file,
                first_first_bucket_number_seasons=first_first_bucket_number_seasons,
                damage_percentage=damage_percentage,
                leftover_running_percentage=leftover_running_percentage,
                leftover_closed_percentage=leftover_closed_percentage,
                closed_percentage=closed_percentage,
                brand_specific_provision=brand_specific_provision,
                unknown_season_in_bucket1=unknown_season_in_bucket1
            )
            st.session_state["soh_comb"] = results["soh_comb"]
            st.session_state["mapping_data"] = results["mapping"]

        st.success("Provisioning complete!")

        
        
        summary_df = results["summary"].copy()
        format_dict = {col: "{:,.0f}" for col in summary_df.columns if col != "coverage"}
        format_dict["coverage"] = "{:.2%}"
        st.subheader("Summary by Std Brand")
        st.dataframe(summary_df.style.format(format_dict))



        st.markdown("### \U0001F4CA Grand Totals")
        total_cost = results["summary"]["NETTOTAL_COST"].sum()
        provision_amount_policy = results["summary"]['provision_amount_policy'].sum()
        additional_provision = results["summary"]['additional_provision'].sum()

        total_provision = results["summary"]["Total Provision"].sum()
        avg_coverage = (results["summary"]["coverage"].mean()) * 100
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Net SOH Cost", f"{total_cost:,.0f}")
        col2.metric("Provision as per Policy", f"{provision_amount_policy:,.0f}")
        col3.metric("Additional provision", f"{additional_provision:,.0f}")
        col4.metric("Total Provision", f"{total_provision:,.0f}")
        col5.metric("Avg Coverage %", f"{avg_coverage:.2f}%")

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            results["soh_comb"].to_excel(writer, index=False)
        st.download_button("Download Combinations Output", data=buffer.getvalue(),
                        file_name="aging_provision_combinations.xlsx")



with tab2:
    #st.write("Debug - keys in session_state:", list(st.session_state.keys()))
    if ("soh_comb" in st.session_state) and ('mapping_data' in st.session_state):
        analysis = get_analysis(st.session_state["soh_comb"],st.session_state["mapping_data"])

        def render_summary_with_metrics(title, df):
            st.subheader(title)

            total_cost = df["NETTOTAL_COST"].sum()
            total_provision = df["Total Provision"].sum()
            avg_coverage = (df["coverage"].mean()) * 100

            format_dict = {"NETTOTAL_COST": "{:,.0f}", "Total Provision": "{:,.0f}", "coverage": "{:.2%}"}

            col_table, col_metrics = st.columns([1, 1])
            with col_table:
                st.dataframe(df.style.format(format_dict), use_container_width=True)

            with col_metrics:
                st.metric("Total Net SOH Cost", f"{total_cost:,.0f}")
                st.metric("Total Provision", f"{total_provision:,.0f}")
                st.metric("Avg Coverage %", f"{avg_coverage:.2f}%")

            
            

        # Display each summary with totals
        render_summary_with_metrics("Damage Stock Summary", analysis["damage_summary"])
        render_summary_with_metrics("Leftover Stock Summary", analysis["leftover_summary"])
        render_summary_with_metrics("Closed Brand Summary", analysis["closed_summary"])
        render_summary_with_metrics("Unknown Season Summary", analysis["no_seasons"])

        
        col1, col2, col3= st.columns([1, 1,1])
        with col1:
            st.subheader("Bucket-to-Season Mapping")
            st.dataframe(analysis["check_buckets"].reset_index(drop=True))

        with col2:
            st.subheader("Original vs Standard Season")
            st.dataframe(analysis["check_season"].reset_index(drop=True))
        with col3:
            st.subheader("Brands not in the working file")
            st.dataframe(pd.DataFrame(analysis["missing_std_brands_in_soh"]))

        st.subheader("")
        st.metric("Total SOH cost with missing standard Brand", f"{analysis['missing_in_std_brand']:,.0f}")

        st.subheader("")
        st.metric("Duplicates in mapping file",value=f"{analysis['duplicates_mapping']:,.0f}")




        st.subheader("")
        st.metric( "Total SOH cost with missing combinations",value=f"{analysis['missing_comb_rows']:,.2f}")      


    else:
        st.warning("Run the provision logic in Tab 1 to view analysis.")

with tab3:
    st.markdown("Upload the existing balance file for reconciliation:")
    balance_file = st.file_uploader("Upload Existing Balance File", type=["xlsx"], key="balance")

    if "soh_comb" in st.session_state and balance_file:
        with st.spinner("Generating GL entries..."):
            completed_entry, diff_entry ,existing_balances= get_GL_entry(
                st.session_state["soh_comb"],
                pd.read_excel(balance_file)
            )
        st.metric("Total Provision amount(dr/(CR))", f"{completed_entry[completed_entry['s5']==23993]['Dr/(CR)'].sum():,.2f}")
        st.metric("Current balance the System (dr/(CR))", f"{existing_balances.iloc[:,-1].sum():,.2f}")
        st.metric("Diff entry(dr/(CR))", f"{diff_entry[diff_entry['s5']==23993]['Dr/(CR)'].sum():,.2f}")

        st.subheader("GL Entry Completed")
        #st.dataframe(completed_entry)
        st.download_button("Download Completed Entry", data=completed_entry.to_csv(index=False).encode(),
                        file_name="completed_entry.csv")

        st.subheader("GL Entry: Diff (Reconciliation)")
        #st.dataframe(diff_entry)
        st.download_button("Download Diff Entry", data=diff_entry.to_csv(index=False).encode(),
                        file_name="diff_entry.csv")
        
    elif "soh_comb" not in st.session_state:
        st.warning("Run the provision logic in Tab 1 first.")
    elif not balance_file:
        st.info("Please upload a balance file to generate GL entries.")