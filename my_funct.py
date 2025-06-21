import pandas as pd
import numpy as np
import os
import re

def run_aging_provision_pipeline(
    soh_path,
    first_first_bucket_number_seasons=5,
    damage_percentage=1.0,
    leftover_running_percentage=0.15,
    leftover_closed_percentage=0.5,
    closed_percentage=0.5,
    brand_specific_provision=None,
    unknown_season_in_bucket1=True,
):
    brand_specific_provision = brand_specific_provision or {}
    pd.options.display.float_format = '{:,.2f}'.format
    os.makedirs("Output", exist_ok=True)

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
        if "WA" in season:
            match = re.search(r"WA(\d{2})", season)
            if match:
                return f"AW{match.group(1)}"
        match = re.search(r"(\d{2})", season)
        if match:
            return f"SS{match.group(1)}"
        return "Unknown"

    soh = pd.read_excel(soh_path)
    soh = soh[(soh['GROUP_NAME'] != 'Aleph') & (soh['AR Comments'] == 'Consider')]
    
    mapping = pd.read_excel('mapping.xlsx', sheet_name='Sheet1')
    combinations = combinations = pd.read_excel('combinations.xlsx', sheet_name='Sheet1').groupby(['LOCATION', 'Std Brand']).first().reset_index()

    soh['NETTOTAL_COST'].fillna(0, inplace=True)
    soh['NETTOTAL_COST'] = pd.to_numeric(soh['NETTOTAL_COST'], errors='coerce')
    original_season = 'SEASON_DESC' if 'SEASON_DESC' in soh.columns else 'SEASON DESC'
    soh['GROUP_NAME'] = soh['GROUP_NAME'].str.upper()
    mapping['GROUP_NAME'] = mapping['GROUP_NAME'].str.upper()
    soh = soh.merge(mapping, on='GROUP_NAME', how='left')
    soh = soh[(soh['Closed_status'] != 'Exit')]
    soh['std_season'] = soh[original_season].apply(standardize_season)

    excluded = {'Unknown', 'Continuity', 'Old-', 'AW97'}
    unique_season = [f for f in soh['std_season'].dropna().unique() if f not in excluded]
    sorted_std_season_in_soh = sorted(unique_season, key=season_sort_key, reverse=True)
    if unknown_season_in_bucket1:
        bucket1 = sorted_std_season_in_soh[:first_first_bucket_number_seasons] + ['Unknown', 'Continuity']
        bucket2 = sorted_std_season_in_soh[first_first_bucket_number_seasons:first_first_bucket_number_seasons + 3]
        bucket3 = sorted_std_season_in_soh[first_first_bucket_number_seasons + 3:first_first_bucket_number_seasons + 6]
        bucket4 = sorted_std_season_in_soh[first_first_bucket_number_seasons + 6:] + ['Old-', 'AW97']
    else:
        bucket1 = sorted_std_season_in_soh[:first_first_bucket_number_seasons] + [ 'Continuity']
        bucket2 = sorted_std_season_in_soh[first_first_bucket_number_seasons:first_first_bucket_number_seasons + 3]
        bucket3 = sorted_std_season_in_soh[first_first_bucket_number_seasons + 3:first_first_bucket_number_seasons + 6]
        bucket4 = sorted_std_season_in_soh[first_first_bucket_number_seasons + 6:] + ['Unknown','Old-', 'AW97']

    conditions = [
        soh['std_season'].isin(bucket1),
        soh['std_season'].isin(bucket2),
        soh['std_season'].isin(bucket3)
    ]
    soh['season_bucket'] = np.select(conditions, ['bucket1', 'bucket2', 'bucket3'], default='bucket4')
    soh['Continuity_factor'] = 0.40
    soh['provision_%_policy'] = soh['season_bucket'].map({'bucket1': 0, 'bucket2': 0.15, 'bucket3': 0.50, 'bucket4': 0.75})
    soh.loc[soh['Model'].isin(['Consignment', 'Guaranteed Margin', 'Buying Pull - Mango']),
            ['provision_amount_policy', 'provision_%_policy', 'Continuity_factor']] = 0
    soh['provision_amount_policy'] = soh['NETTOTAL_COST'] * soh['provision_%_policy'] * soh['Continuity_factor']

    soh['location_catergory'] = "Store, Online & WH"
    soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('leftover', na=False), "location_catergory"] = "Leftover"
    soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('damage', na=False), "location_catergory"] = "Damage"
    soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('sulay', na=False), "location_catergory"] = "Leftover"

    soh['additional_provision'] = 0
    soh.loc[soh['location_catergory'] == "Damage", 'additional_provision'] = (
        soh["NETTOTAL_COST"] * damage_percentage - soh['provision_amount_policy'])

    condition = (soh['Closed_status'] == "Closed") & (soh['location_catergory'] == "Leftover")
    soh.loc[condition, 'additional_provision'] = (
        soh["NETTOTAL_COST"] * leftover_closed_percentage - soh['provision_amount_policy'])

    condition = (soh['Closed_status'] != "Closed") & (soh['location_catergory'] == "Leftover")
    soh.loc[condition, 'additional_provision'] = (
        soh["NETTOTAL_COST"] * leftover_running_percentage - soh['provision_amount_policy'])

    condition = (soh['Closed_status'] == "Closed") & (~soh['location_catergory'].isin(["Leftover", "Damage"]))
    soh.loc[condition, 'additional_provision'] = (
        soh["NETTOTAL_COST"] * closed_percentage - soh['provision_amount_policy'])

    if brand_specific_provision:
        soh['additional_provision'] = np.where(
            soh['Std Brand'].isin(brand_specific_provision.keys()),
            soh['NETTOTAL_COST'] * soh['Std Brand'].map(brand_specific_provision) - soh['provision_amount_policy'],
            soh['additional_provision']
        )

    soh.loc[soh['Model'].isin(['Consignment', 'Guaranteed Margin', 'Buying Pull - Mango']),
            ['provision_amount_policy', 'provision_%_policy', 'Continuity_factor', 'additional_provision']] = 0

    soh['provision_amount_policy'] = soh['provision_amount_policy'].fillna(0)
    soh['additional_provision'] = soh['additional_provision'].fillna(0)
    soh['Total Provision'] = soh['provision_amount_policy'] + soh['additional_provision']
    soh.to_csv(os.path.join("Output", "aging_provision.csv"), index=False)

    # Generate analysis and checks
    soh_comb = soh.merge(combinations, on=['Std Brand', 'LOCATION'], how='left').fillna(0)
    soh_comb.to_excel(os.path.join("Output", "aging_provision_combinations.xlsx"), index=False)

    summary = soh_comb.groupby(by='Std Brand')[["NETTOTAL_COST", 'provision_amount_policy',
                                                 'additional_provision', 'Total Provision']].sum()
    summary['coverage'] = summary['Total Provision'] / summary['NETTOTAL_COST']



    return {

        "summary": summary,
        "soh_comb": soh_comb,
    }

def get_GL_entry(soh_with_combinations: pd.DataFrame, 
                 existing_balances: pd.DataFrame):
    
    entry = soh_with_combinations.groupby(["s1","s2","s3","s4"])['Total Provision'].sum().reset_index().fillna(0)
    entry['s5'] = 63002
    entry['Total Provision'].sum()
    entry2 = entry.copy()
    entry2['Total Provision'] = entry2['Total Provision'] * -1
    entry2['s5'] = 23993
    completed_entry = pd.concat([entry, entry2], ignore_index=True)
    completed_entry.rename(columns={'Total Provision': 'Dr/(CR)'}, inplace=True)
    completed_entry = completed_entry[completed_entry['Dr/(CR)'] != 0]
    completed_entry = completed_entry[['s1', 's2', 's3', 's4', 's5','Dr/(CR)']]
    completed_entry.to_csv(os.path.join("Output","completed_entry.csv"), index=False)

    diff_table = soh_with_combinations.groupby(["s1","s2","s3","s4"])['Total Provision'].sum().reset_index().fillna(0).merge(existing_balances, on=['s1','s2','s3','s4'], how='outer').fillna(0)
    diff_table['Dr/(CR)'] = (diff_table['Total Provision'] + diff_table['Closing balance'])*-1
    diff_table.drop(['Closing balance','Total Provision'], inplace=True,axis=1)
    diff_table['s5'] = 23993
    diff_table2 = diff_table.copy()
    diff_table2['Dr/(CR)'] = diff_table2['Dr/(CR)'] * -1
    diff_table2['s5'] = 63002
    diff_entry = pd.concat([diff_table, diff_table2], ignore_index=True)
    #diff_entry.rename(columns={'Total Provision': 'Dr/(CR)'}, inplace=True)
    diff_entry = diff_entry[diff_entry['Dr/(CR)'] != 0]
    diff_entry = diff_entry[['s1', 's2', 's3', 's4', 's5','Dr/(CR)']]
    diff_entry.to_csv(os.path.join("Output","diff_entry.csv"), index=False)

    return completed_entry, diff_entry, existing_balances

def get_analysis(soh_with_combinations: pd.DataFrame):
    original_season = 'SEASON_DESC' if 'SEASON_DESC' in soh_with_combinations.columns else 'SEASON DESC'
    mapping = pd.read_excel("Mapping.xlsx", sheet_name='Sheet1')
    
    damage_summary = soh_with_combinations[soh_with_combinations['location_catergory'] == 'Damage'].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
    damage_summary['coverage'] = damage_summary['Total Provision'] / damage_summary['NETTOTAL_COST']
    damage_summary

    leftover_summary = soh_with_combinations[soh_with_combinations['location_catergory'] == 'Leftover'].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
    leftover_summary['coverage'] = leftover_summary['Total Provision'] / leftover_summary['NETTOTAL_COST']
    leftover_summary

    closed_summary = soh_with_combinations[soh_with_combinations['Closed_status'] == 'Closed'].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
    closed_summary['coverage'] = closed_summary['Total Provision'] / closed_summary['NETTOTAL_COST']
    closed_summary

    check_buckets = soh_with_combinations[['season_bucket','std_season' ]].drop_duplicates().sort_values(by='season_bucket', ascending=True)
    check_season = soh_with_combinations[['std_season', original_season]].drop_duplicates().sort_values(by='std_season', ascending=True)

    #missing combinations in output
    missing_combinations = soh_with_combinations[(soh_with_combinations['NETTOTAL_COST'] != 0)&(soh_with_combinations['s1'].isna())] 
    # Check for missing values in key columns
    missing_in_std_brand = soh_with_combinations[soh_with_combinations['Std Brand'].isnull()]['NETTOTAL_COST'].sum()
    #print("Net cost of missing std_brand :", missing_in_std_brand['NETTOTAL_COST'].sum())
    # Check for duplicates in mapping [original brand name]
    duplicates_mapping = mapping[mapping.duplicated(subset=['GROUP_NAME'], keep=False)].shape[0]
    #print("Duplicate original brand names in mapping:", mapping[duplicates_mapping].shape[0])
    missing_std_brands_in_soh = set(mapping['Std Brand']) - set(soh_with_combinations['Std Brand'])
    #print("Std Brands in mapping missing in SOH:", missing_std_brands_in_soh)
    # Check for garbage/unknown seasons in std_season
    no_seasons = soh_with_combinations[(soh_with_combinations['std_season'] == "Unknown")&(~soh_with_combinations['Model'].isin([
            'Consignment',
            'Guaranteed Margin',
            'Buying Pull - Mango'
        ]))].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
    no_seasons['coverage'] = no_seasons['Total Provision'] / no_seasons['NETTOTAL_COST']
    #print("Cost of unknown std_season:", f"{garbage_seasons['NETTOTAL_COST'].sum():,.2f}")
    # Check for missing in combinations merge
    missing_comb_rows = soh_with_combinations[soh_with_combinations['s4'] == 0]['NETTOTAL_COST'].sum()
    #print("Cost with combination mapping:", f"{missing_comb_rows['NETTOTAL_COST'].sum():,.2f}")

    missing_seasons_details = soh_with_combinations[soh_with_combinations[original_season].isna() | (soh_with_combinations[original_season] == '')].groupby('Std Brand')['NETTOTAL_COST'].sum()
    return {
    "damage_summary": damage_summary,
    "leftover_summary": leftover_summary,
    "closed_summary": closed_summary,
    "check_buckets": check_buckets,
    "check_season": check_season,
    "no_seasons": no_seasons,
    "missing_combinations": missing_combinations,
    "missing_in_std_brand": missing_in_std_brand,
    "duplicates_mapping": duplicates_mapping,
    "missing_std_brands_in_soh": missing_std_brands_in_soh,
    "missing_comb_rows": missing_comb_rows

}
